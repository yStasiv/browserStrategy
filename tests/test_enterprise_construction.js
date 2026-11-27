const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('construction polls without replacing the entered quantity and submits only once', async () => {
    function node() {
        return {
            children: {},
            handlers: {},
            showModal() { this.open = true; },
            close() { this.open = false; this.handlers.close?.(); },
            addEventListener(event, handler) { this.handlers[event] = handler; },
            querySelector(selector) { return this.children[selector] ||= node(); },
            setAttribute(key, value) { this[key] = value; },
        };
    }
    const panel = node();
    const container = panel.querySelector('#construction-panel');
    const row = container.querySelector('[data-resource="singing_resin"]');
    const form = row.querySelector('form');
    const input = Object.assign(node(), {value: ''});
    Object.defineProperty(input, 'valueAsNumber', {get() { return Number(input.value); }});
    const slider = node();
    form.elements = Object.assign([input, slider, row.querySelector('button')], {quantity: input, quantity_range: slider});
    form.reportValidity = () => Number(input.value) <= input.max;
    form.reset = () => { input.value = ''; };
    row.dataset = {resource: 'singing_resin'};
    container.dataset = {url: '/enterprise/9/construction'};
    container.querySelectorAll = () => [row];
    const resource = {id: 'singing_resin', required: 10, collected: 0, remaining: 10, available: 5, personal: 0};
    const foundation = {
        stage: 'FOUNDATION', stage_name: 'Фундамент', image_url: '/foundation.png',
        server_time: '2026-11-27T00:00:00+00:00', collection_progress: 0, resources: [resource],
    };
    const progress = {...foundation, stage: 'FOUNDATION_WITH_RESOURCES', stage_name: 'Фундамент із ресурсами',
        image_url: '/supplies.png', collection_progress: 20,
        resources: [{...resource, collected: 2, remaining: 8}]};
    const built = {...progress, stage: 'FRAME_CONSTRUCTION', stage_name: 'Каркас', image_url: '/frame.png',
        started_at: foundation.server_time, next_stage_at: '2026-11-30T00:00:00+00:00',
        completion_at: '2026-12-02T00:00:00+00:00', collection_progress: 100,
        resources: [{...resource, collected: 10, remaining: 0, available: 0, personal: 5}]};
    container.querySelector('#construction-state').textContent = JSON.stringify(foundation);
    const timers = [];
    let postCount = 0;
    let resolvePost;
    let getResult = progress;
    const ctx = vm.createContext({
        document: {querySelector: selector => selector === '.enterprise-panel' ? panel : null},
        CSS: {escape: value => value},
        crypto: {randomUUID: () => 'pending-operation'},
        performance: {now: () => 0},
        setInterval: callback => timers.push(callback),
        fetch: (url, options) => {
            if (options.method === 'POST') {
                postCount += 1;
                assert.equal(url, '/enterprise/9/construction/contribute');
                assert.deepEqual(JSON.parse(options.body), {resource: 'singing_resin', quantity: 5, operation_id: 'pending-operation'});
                return new Promise(resolve => { resolvePost = resolve; });
            }
            return Promise.resolve({ok: true, json: async () => getResult});
        },
    });
    vm.runInContext(fs.readFileSync('frontend/static/js/enterprise.js', 'utf8'), ctx);
    assert.equal(slider.max, 5);
    slider.value = '4';
    slider.handlers.input();
    assert.equal(input.value, '4');
    input.value = '3';
    input.handlers.input();
    assert.equal(slider.value, '3');
    await timers[0]();
    assert.equal(input.value, '3');
    assert.equal(container.querySelector('#construction-art').src, '/supplies.png');
    form.querySelector('[data-max]').handlers.click();
    assert.equal(input.value, 5);
    assert.equal(slider.value, "5");
    const event = {preventDefault() {}};
    form.handlers.submit(event);
    assert.equal(postCount, 0);
    const dialog = container.querySelector('#construction-confirm');
    assert.equal(dialog.open, true);
    dialog.close();
    assert.equal(postCount, 0);
    form.handlers.submit(event);
    const confirm = container.querySelector('#construction-confirm-submit');
    const pending = confirm.handlers.click();
    await confirm.handlers.click();
    assert.equal(postCount, 1);
    getResult = built;
    resolvePost({ok: true, json: async () => built});
    await pending;
    assert.equal(container.querySelector('#construction-art').src, '/frame.png');
    assert.equal(form.hidden, true);
    assert.equal(input.disabled, true);
});
