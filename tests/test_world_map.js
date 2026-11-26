const {test} = require('node:test');
const assert = require('node:assert/strict');
const geo = require('../frontend/static/js/world_geography.js');
const config = require('../content/map_location.json');

test('all configured preview stages are independent of persisted unlocks and preserve connectivity', () => {
    assert.equal(geo.validateProgression(config.locations, 1), '');
    for (let stage = 1; stage <= config.map.total_locations; stage++) {
        const opened = geo.stage(config.locations, stage);
        assert.equal(opened.length, stage);
        assert.equal(opened.some(row => row.id === 33), stage === config.map.total_locations);
    }
    assert.equal(config.locations.filter(row => row.unlocked_by_default).length, 1);
});

test('SVG image and geometry share native coordinates under zoom and translation', () => {
    const map = config.map;
    const [x, y] = geo.point(.42, .25, map);
    for (const scale of [.25, 1, 2.5]) {
        global.DOMPoint = class {
            constructor(x, y) { this.x = x; this.y = y; }
            matrixTransform(inverse) { return inverse(this.x, this.y); }
        };
        const svg = {getScreenCTM: () => ({inverse: () => (clientX, clientY) =>
            ({x: (clientX - 45) / scale, y: (clientY - 80) / scale})})};
        const coords = geo.normalized({clientX: x * scale + 45, clientY: y * scale + 80}, svg, map);
        assert.ok(Math.abs(coords[0] - .42) < 1e-10);
        assert.ok(Math.abs(coords[1] - .25) < 1e-10);
    }
});

test('fog mask cuts out only open polygons and marks newly revealed locations', () => {
    class Node {
        constructor(tag) {
            this.tag = tag;
            this.attrs = {};
            this.children = [];
            this.classes = [];
            this.classList = {add: name => this.classes.push(name)};
            this.style = {setProperty: (key, value) => { this.style[key] = value; }};
        }
        append(...entries) { this.children.push(...entries); }
        setAttribute(name, value) { this.attrs[name] = value; }
    }
    global.document = {createElementNS: (_namespace, tag) => new Node(tag)};
    const svg = new Node('svg');
    svg.id = 'test-svg';
    geo.setup(svg, config.map);
    const opened = geo.stage(config.locations, 2);
    geo.fog(svg, config.map, config.fog_of_war, opened, new Set([9]));
    const [defs, fog] = svg.children;
    const mask = defs.children.find(node => node.tag === 'mask');
    assert.equal(mask.children.length, 3);
    assert.equal(mask.children[0].tag, 'polygon');
    assert.equal(mask.children[0].attrs.points, geo.points({geometry: config.map.playable_area}, config.map));
    const visible = mask.children[2].children;
    assert.equal(visible.length, 2);
    assert.equal(visible[1].classes[0], 'world-fog-reveal');
    assert.equal(visible[1].style.animationDuration, '1500ms');
    assert.ok(!visible.some(shape => shape.attrs.points === geo.points(config.locations.find(row => row.id === 33), config.map)));
    assert.equal(fog.attrs['pointer-events'], 'none');
    assert.equal(fog.children[1].attrs.href, config.fog_of_war.texture);
    assert.equal(fog.children[1].style.animationDuration, '60000ms');
    assert.ok(Number(fog.children[1].attrs.width) > config.map.width);
});

test('Configured polygons have exact shared edges, full coverage, and valid routes', () => {
    assert.equal(geo.validateTopology(config.locations, config.map), '');
    const stats = geo.areaStats(config.locations, config.map);
    assert.equal(stats.size, config.map.total_locations);
    assert.ok([...stats.values()].every(row => row.actual > 0));
    const broken = structuredClone(config.locations);
    broken[0].geometry.points[0][0] += .002;
    assert.notEqual(geo.validateTopology(broken, config.map), '');
});

test('only open neighboring destinations can show confirmation', () => {
    const state = {current_sector: 'Castle', travel: null, work_blocks_travel: false};
    const valid = {key: 'Forest', unlocked: true, duration_seconds: 4};
    assert.equal(geo.canSelect(state, valid), true);
    for (const target of [null, {...valid, key: 'Castle'}, {...valid, unlocked: false}, {...valid, duration_seconds: null}]) {
        assert.equal(geo.canSelect(state, target), false);
    }
    assert.equal(geo.canSelect({...state, travel: {}}, valid), false);
    assert.equal(geo.canSelect({...state, work_blocks_travel: true}, valid), false);
});

test('map clicks update only the confirmation until a single departure is confirmed', async () => {
    const fs = require('node:fs');
    const vm = require('node:vm');
    class Element {
        constructor() {
            this.children = [];
            this.handlers = {};
            this.attributes = {};
            this.dataset = {};
            this.hidden = true;
            this.disabled = false;
            this.style = {setProperty: (key, value) => { this.style[key] = value; }};
            this.classList = {add() {}, toggle() {}};
        }
        append(...entries) { this.children.push(...entries); }
        replaceChildren(...entries) { this.children = entries; }
        addEventListener(event, handler) { this.handlers[event] = handler; }
        setAttribute(name, value) { this.attributes[name] = value; }
        getAttribute(name) { return this.attributes[name]; }
        toggleAttribute(name, value) { this.attributes[name] = value; }
        querySelectorAll(query) { return query === '[data-sector]' ? this.children.filter(entry => entry.dataset?.sector) : []; }
        querySelector(query) { return this[query] ??= new Element(); }
        getBoundingClientRect() { return {left: 10, top: 10, width: 500, height: 500}; }
        get offsetWidth() { return 99; }
        get clientWidth() { return 500; }
        get clientHeight() { return 500; }
        fire(name, event = {}) { return this.handlers[name]({stopPropagation() {}, ...event}); }
    }
    const nodes = new Map();
    const el = id => {
        if (!nodes.has(id)) nodes.set(id, Object.assign(new Element(), {id}));
        return nodes.get(id);
    };
    const tab = el('world-tab');
    tab.attributes = {'aria-selected': 'true', 'aria-controls': 'sites'};
    tab.dataset.productionType = 'mine';
    global.document = {
        getElementById: el, querySelectorAll: () => [tab],
        createElement: () => new Element(), createElementNS: () => new Element(),
    };
    const sectors = config.locations.filter(row => [1, 3, 9, 33].includes(row.id)).map(row => ({
        ...row, unlocked: true, duration_seconds: {3: 4, 9: 2}[row.id] ?? null,
    }));
    const initial = {
        map: config.map, fog_of_war: config.fog_of_war, current_sector: 'Castle',
        sectors, work_blocks_travel: false, travel: null, hunts: [], enterprises: [], server_time: '2026-11-26T12:00:00Z',
    };
    el('world-state').textContent = JSON.stringify(initial);
    const requests = [];
    let travelResult;
    const context = vm.createContext({
        document: global.document, WorldGeography: geo, Intl, performance: {now: () => 0},
        setInterval() {}, setTimeout() {}, clearTimeout() {}, requestAnimationFrame() {}, cancelAnimationFrame() {}, ResizeObserver: class { observe() {} },
        fetch: (url, options) => {
            requests.push([url, JSON.parse(options.body)]);
            return new Promise(resolve => { travelResult = resolve; });
        },
    });
    vm.runInContext(fs.readFileSync('frontend/static/js/world_map.js', 'utf8'), context);
    const confirmation = el('world-travel-selected');
    const polygon = key => el('world-markers').children.find(row => row.dataset.sector === key);
    assert.ok(confirmation.hidden);
    const fogChildren = el('world-fog').children;
    polygon('Castle').fire('click');
    assert.ok(confirmation.hidden);
    assert.equal(polygon('waterfall_valley'), undefined);
    polygon('Forest').fire('click', {clientX: 110, clientY: 210});
    assert.equal(confirmation.hidden, false);
    assert.match(confirmation.title, /Золотолісся.*4 с/);
    assert.equal(confirmation.style.left, '50.5px');
    assert.equal(confirmation.style.top, '150.5px');
    polygon('royal_port').fire('click');
    assert.ok(confirmation.hidden);
    polygon('Forest').fire('click');
    el('world-art').fire('click');
    assert.ok(confirmation.hidden);
    polygon('Forest').fire('click');
    polygon('Mountain').fire('click');
    assert.match(confirmation.title, /Зелені передгір’я.*2 с/);
    assert.equal(requests.length, 0);
    assert.equal(el('world-fog').children, fogChildren);
    assert.equal(el('world-art').style.width, undefined);
    const move = el('world-travel-selected');
    move.fire('click');
    move.fire('click');
    assert.equal(requests.length, 1);
    assert.deepEqual(requests[0], ['/move-to-sector', {sector: 'Mountain'}]);
    travelResult({ok: true, json: async () => ({
        ...initial, travel: {origin:'Castle', destination:'Mountain', started_at: initial.server_time,
            arrives_at: '2026-11-26T12:00:02Z'},
    })});
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(confirmation.hidden);
    assert.match(el('world-current').textContent, /Королівська цитадель/);
    const css = fs.readFileSync('frontend/static/css/world_map.css', 'utf8');
    assert.match(css, /\.map-movement-confirmation\s*\{[^}]*position:\s*absolute;/s);
});

test('valid neighboring sectors may have substantially different areas', () => {
    const map = {...config.map, playable_area: {points: [[0, 0], [1, 0], [1, 1], [0, 1]]}};
    const left = {id: 1, geometry: {points: [[0, 0], [.2, 0], [.2, 1], [0, 1]]},
        connections: [{location_id: 2, travel_time_seconds: 2}]};
    const right = {id: 2, geometry: {points: [[.2, 0], [1, 0], [1, 1], [.2, 1]]},
        connections: [{location_id: 1, travel_time_seconds: 2}]};
    assert.equal(geo.validateTopology([left, right], map), '');
    assert.ok(geo.areaStats([left, right], map).get(2).deviation > 50);
});

test('travel follows intermediate points at constant speed in both directions', () => {
    const map = {width: 100, height: 200};
    const a = {x: 0, y: 0};
    const b = {x: 1, y: 1};
    const route = geo.routeSampler(a, b, [[1, 0]], map);
    const reverse = geo.routeSampler(b, a, [[1, 0]], map);
    assert.deepEqual(route(0), [0, 0]);
    assert.deepEqual(route(1 / 3), [100, 0]);
    assert.deepEqual(route(.5), [100, 50]);
    assert.deepEqual(reverse(.5), route(.5));
    assert.deepEqual(route(1), [100, 200]);
    assert.deepEqual(geo.routeSampler(a, b, [], map)(.5), [50, 100]);
});
