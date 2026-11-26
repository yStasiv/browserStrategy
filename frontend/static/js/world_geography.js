/* Coordinate conversion and SVG layers shared by the player map and editor. */
const WorldGeography = (() => {
    const namespace = 'http://www.w3.org/2000/svg';
    const point = (x, y, map) => [x * map.width, y * map.height];
    const points = (location, map) => location.geometry.points.map(([x, y]) => point(x, y, map).join(',')).join(' ');
    const stage = (locations, order) => locations.filter(row => row.unlock_order <= order);
    const normalized = (event, svg, map) => {
        const local = new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
        const clamp = value => Math.min(1, Math.max(0, value));
        return [clamp(local.x / map.width), clamp(local.y / map.height)];
    };

    function svgNode(tag, attrs = {}) {
        const node = document.createElementNS(namespace, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
        return node;
    }

    function setup(svg, map) {
        svg.setAttribute('viewBox', `0 0 ${map.width} ${map.height}`);
    }

    function fog(svg, map, settings, opened, revealing = new Set()) {
        if (!settings.enabled) return;
        const id = svg.id;
        const defs = svgNode('defs');
        const mask = svgNode('mask', {id: id + '-mask', maskUnits: 'userSpaceOnUse',
            x: 0, y: 0, width: map.width, height: map.height});
        const blur = settings.edge_blur;
        const filter = svgNode('filter', {id: id + '-feather', filterUnits: 'userSpaceOnUse',
            x: 0, y: 0, width: map.width, height: map.height});
        filter.append(svgNode('feGaussianBlur', {stdDeviation: blur}));
        const base = {width: map.width, height: map.height};
        if (settings.preserve_ocean_visibility && map.playable_area) {
            mask.append(svgNode('polygon', {points: points({geometry: map.playable_area}, map), fill: 'white'}));
        } else {
            mask.append(svgNode('rect', {...base, fill: 'white'}));
        }
        const edge = svgNode('g', {filter: `url(#${id}-feather)`});
        const openings = svgNode('g');
        for (const location of opened) {
            const attrs = {points: points(location, map), fill: 'black'};
            const cutout = svgNode('polygon', attrs);
            const feather = svgNode('polygon', attrs);
            if (settings.animation_enabled && revealing.has(location.id)) {
                for (const layer of [cutout, feather]) {
                    layer.classList.add('world-fog-reveal');
                    layer.style.animationDuration = settings.reveal_duration_ms + 'ms';
                }
            }
            edge.append(feather);
            openings.append(cutout);
        }
        if (blur > 0) {
            // Clip the feather to the same coast as the opaque mask.
            if (settings.preserve_ocean_visibility && map.playable_area) {
                const clip = svgNode('clipPath', {id: id + '-shore'});
                clip.append(svgNode('polygon', {points: points({geometry: map.playable_area}, map)}));
                defs.append(clip);
                edge.setAttribute('clip-path', `url(#${id}-shore)`);
            }
            mask.append(edge);
        }
        mask.append(openings);
        defs.append(filter, mask);
        const fogLayer = svgNode('g', {mask: `url(#${id}-mask)`, opacity: settings.opacity, 'pointer-events': 'none'});
        fogLayer.append(svgNode('rect', {...base, fill: '#33495e'}));
        const overscan = Math.max(map.width, map.height) * settings.ambient_animation_intensity;
        const texture = svgNode('image', {href: settings.texture, x: -overscan, y: -overscan,
            width: map.width + 2 * overscan, height: map.height + 2 * overscan, preserveAspectRatio: 'xMidYMid slice'});
        if (settings.animation_enabled && overscan > 0) {
            texture.classList.add('world-fog-texture');
            texture.style.animationDuration = settings.ambient_animation_duration_ms + 'ms';
            texture.style.setProperty('--fog-drift', (overscan * .8) + 'px');
        }
        fogLayer.append(texture);
        svg.append(defs, fogLayer);
    }

    function canSelect(state, destination) {
        return Boolean(destination?.unlocked && destination.key !== state.current_sector
            && destination.duration_seconds > 0 && !state.travel && !state.work_blocks_travel);
    }

    function zoom(art, scale) {
        art.style.width = `${100 * scale}%`;
        art.parentElement.classList.toggle('world-map-zoomed', scale > 1);
    }

    const samePoint = ([ax, ay], [bx, by]) => ax === bx && ay === by;
    const edgesOf = vertices => vertices.map((p, i) => [p, vertices[(i + 1) % vertices.length]]);
    const edgeKey = (a, b) => [a.join(','), b.join(',')].sort().join(':');
    const cross = ([ax, ay], [bx, by], [px, py]) => (bx - ax) * (py - ay) - (by - ay) * (px - ax);

    function signedArea(vertices) {
        return edgesOf(vertices).reduce((sum, [[ax, ay], [bx, by]]) => sum + ax * by - bx * ay, 0) / 2;
    }

    function areaStats(locations, map) {
        const pixelScale = map.width * map.height;
        const target = Math.abs(signedArea(map.playable_area.points)) * pixelScale / locations.length;
        return new Map(locations.map(row => {
            const actual = Math.abs(signedArea(row.geometry.points)) * pixelScale;
            const deviation = (actual / target - 1) * 100;
            return [row.id, {actual, target, deviation}];
        }));
    }

    function routeSampler(origin, destination, waypoints, map) {
        const stops = [[origin.x, origin.y], ...waypoints, [destination.x, destination.y]]
            .map(([x, y]) => point(x, y, map));
        const lengths = stops.slice(1).map(([x, y], i) => Math.hypot(x - stops[i][0], y - stops[i][1]));
        const total = lengths.reduce((sum, length) => sum + length, 0);
        return progress => {
            let distance = total * Math.min(1, Math.max(0, progress));
            for (const [i, length] of lengths.entries()) {
                if (length && distance < length) {
                    const t = distance / length;
                    return stops[i].map((value, axis) => value + t * (stops[i + 1][axis] - value));
                }
                distance -= length;
            }
            return stops.at(-1);
        };
    }

    function validateTopology(locations, map) {
        const area = areaStats(locations, map);
        const shore = map.playable_area.points;
        const shoreEdges = edgesOf(shore);
        const onSegment = (p, a, b) => {
            const eps = 1e-8;
            return Math.abs(cross(a, b, p)) < eps
                && p.every((v, i) => Math.min(a[i], b[i]) - eps <= v && v <= Math.max(a[i], b[i]) + eps);
        };
        const rings = new Map();
        const shared = new Map();
        let coverArea = 0;
        for (const row of locations) {
            const vertices = row.geometry.points;
            if (vertices.length < 3 || vertices.some(point => point.length !== 2 ||
                    point.some(v => !Number.isFinite(v) || v < 0 || v > 1))) return `Некоректні вершини «${row.name}».`;
            coverArea += area.get(row.id).actual;
            const ring = signedArea(vertices) >= 0 ? vertices : [...vertices].reverse();
            const ringEdges = new Set();
            for (const [a, b] of edgesOf(ring)) {
                if (samePoint(a, b)) return `Повторена вершина «${row.name}».`;
                const key = edgeKey(a, b);
                if (ringEdges.has(key)) return `Ребро повторюється в «${row.name}».`;
                ringEdges.add(key);
                const list = shared.get(key) ?? [];
                list.push([a, b]);
                shared.set(key, list);
            }
            rings.set(row.id, ringEdges);
        }
        const distinct = [];
        for (const entries of shared.values()) {
            const [[a, b]] = entries;
            distinct.push([a, b]);
            if (entries.length === 2 && samePoint(a, entries[1][1])) continue;
            if (entries.length !== 1 || !shoreEdges.some(([p, q]) => onSegment(a, p, q) && onSegment(b, p, q))) {
                return 'Спільні межі секторів або берегова лінія розходяться.';
            }
        }
        for (const [index, [a, b]] of distinct.entries()) {
            for (let j = index + 1; j < distinct.length; j++) {
                const [c, d] = distinct[j];
                if (cross(a, b, c) * cross(a, b, d) < -1e-16 && cross(c, d, a) * cross(c, d, b) < -1e-16) {
                    return 'Межі секторів перетинаються.';
                }
            }
        }
        if (Math.abs(coverArea / (map.width * map.height) - Math.abs(signedArea(shore))) > 1e-7) {
            return 'Сектори повинні покривати всю визначену ігрову територію.';
        }
        const byId = new Map(locations.map(row => [row.id, row]));
        for (const row of locations) {
            for (const {location_id: id, travel_time_seconds: seconds, waypoints = []} of row.connections) {
                const reverse = byId.get(id)?.connections.find(link => link.location_id === row.id);
                if (!Array.isArray(waypoints) || waypoints.some(point => !Array.isArray(point) || point.length !== 2
                        || point.some(value => !Number.isFinite(value) || value < 0 || value > 1))) {
                    return `Некоректні точки маршруту «${row.name}».`;
                }
                const returnPoints = reverse?.waypoints ?? [];
                if (!reverse || reverse.travel_time_seconds !== seconds
                        || !Array.isArray(returnPoints) || returnPoints.length !== waypoints.length
                        || !waypoints.every((point, i) => Array.isArray(returnPoints.at(-i - 1)) && samePoint(point, returnPoints.at(-i - 1)))
                        || ![...rings.get(row.id)].some(edge => rings.get(id)?.has(edge))) {
                    return `Маршрут «${row.name}» повинен бути двостороннім і перетинати спільну межу.`;
                }
            }
        }
        return '';
    }

    function validateProgression(locations, start) {
        const ordered = [...locations].sort((a, b) => a.unlock_order - b.unlock_order);
        const reached = new Set();
        for (const [index, row] of ordered.entries()) {
            if (row.unlock_order !== index + 1 || (index === 0 && row.id !== start) ||
                    (index > 0 && !row.connections.some(link => reached.has(link.location_id)))) {
                return `Перевір сполучення на етапі ${index + 1}.`;
            }
            const vertices = row.geometry.points;
            const {x, y} = row.marker;
            const inside = vertices.reduce((result, [ax, ay], i) => {
                const [bx, by] = vertices[(i + 1) % vertices.length];
                return (ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax ? !result : result;
            }, false);
            if (vertices.length < 3 || !inside) return `Маркер має бути всередині полігона «${row.name}».`;
            reached.add(row.id);
        }
        return '';
    }

    return {point, points, stage, normalized, svgNode, setup, fog, zoom, canSelect, samePoint, edgesOf, edgeKey, areaStats, routeSampler, validateTopology, validateProgression};
})();
if (typeof module !== 'undefined') module.exports = WorldGeography;
