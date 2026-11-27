(() => {
    const $ = id => document.getElementById(id);
    const data = JSON.parse($('map-editor-data').textContent);
    const {map, locations, fog_of_war: fog} = data;
    const originalBoundaries = new Map(locations.map(row => [row.id, row.geometry.points]));
    for (const row of locations) row.geometry.points = [];
    const byId = new Map(locations.map(row => [row.id, row]));
    const geo = WorldGeography;
    const svg = $('map-editor-layer');
    const location = $('editor-location');
    const route = $('editor-neighbor');
    const vertex = $('editor-vertices');
    const preview = $('editor-preview');
    const feedback = $('editor-feedback');
    let position = -1;
    let mode = '';
    let draft = null;
    let dragging = null;
    let routeDraft = null;
    let nextId = Math.max(map.next_location_id ?? 1, Math.max(...byId.keys()) + 1);
    const format = new Intl.NumberFormat('uk-UA', {maximumFractionDigits: 2});

    const selected = () => byId.get(Number(location.value));
    const option = (value, label) => new Option(label, value);
    function updateLocations(selectedId) {
        map.total_locations = locations.length;
        location.replaceChildren(...locations.map(row => option(row.id, `${row.id} · ${row.name}`)));
        location.value = selectedId;
        const stage = $('editor-stage');
        stage.max = locations.length;
        $('editor-stage-value').textContent = stage.value;
        $('editor-order').max = locations.length;
        select();
    }

    function shape(row, active) {
        return geo.svgNode('polygon', {points: geo.points(row, map), class: active ? 'editor-boundary selected' : 'editor-boundary'});
    }

    function selectedRoute() {
        return selected().connections.find(link => link.location_id === Number(route.value));
    }

    function draw() {
        const active = selected();
        const area = geo.areaStats(locations, map).get(active.id);
        const output = $('editor-area');
        output.textContent = `Площа ${format.format(area.actual)} / ${format.format(area.target)} пікс.² · ${format.format(area.deviation)}%`;
        svg.replaceChildren();
        const visible = preview.checked ? geo.stage(locations, Number($('editor-stage').value)) : locations;
        if (preview.checked && visible.length < locations.length) geo.fog(svg, map, fog, visible);
        for (const row of visible) {
            if (row.geometry.points.length > 2) svg.append(shape(row, row === active && !preview.checked));
            const [x, y] = geo.point(row.marker.x, row.marker.y, map);
            const label = geo.svgNode('text', {x, y: y - 16, class: 'editor-map-label'});
            label.textContent = preview.checked ? row.name : `${row.id} · ${row.name}`;
            svg.append(label);
            if (!preview.checked && row === active) {
                const marker = geo.svgNode('circle', {cx: x, cy: y, r: 12, class: 'editor-marker', 'data-edit': 'marker'});
                svg.append(marker);
            }
        }
        if (preview.checked) return;
        const destination = byId.get(Number(route.value));
        const waypoints = routeDraft ?? selectedRoute()?.waypoints;
        if (destination && waypoints) {
            const marks = [[active.marker.x, active.marker.y], ...waypoints, [destination.marker.x, destination.marker.y]];
            svg.append(geo.svgNode('polyline', {
                points: marks.map(([x, y]) => geo.point(x, y, map).join(',')).join(' '),
                class: 'editor-route-line',
            }));
            for (const [x, y] of waypoints) {
                const [cx, cy] = geo.point(x, y, map);
                svg.append(geo.svgNode('circle', {cx, cy, r: 6, class: 'editor-route-point'}));
            }
        }
        const coordinates = draft ?? active.geometry.points;
        if (draft?.length) {
            svg.append(geo.svgNode('polyline', {points: draft.map(([x, y]) => geo.point(x, y, map).join(',')).join(' '),
                class: 'editor-boundary selected', fill: 'none'}));
        }
        coordinates.forEach(([x, y], index) => {
            const [cx, cy] = geo.point(x, y, map);
            svg.append(geo.svgNode('circle', {cx, cy, r: 10, class: index === position ? 'editor-vertex active' : 'editor-vertex',
                'data-edit': String(index)}));
        });
    }

    function vertices() {
        const points = draft ?? selected().geometry.points;
        vertex.replaceChildren(...points.map(([x, y], index) => option(index, `${index + 1}. ${x.toFixed(4)}, ${y.toFixed(4)}`)));
        if (position < 0) vertex.selectedIndex = -1;
        else vertex.value = position;
        $('editor-delete').disabled = position < 0 || (!draft && points.length <= 3);
    }

    function select() {
        routeDraft = null;
        const row = selected();
        mode = row.geometry.points.length ? '' : 'trace';
        draft = null;
        position = -1;
        $('editor-add').setAttribute('aria-pressed', String(Boolean(mode)));
        $('editor-redraw').setAttribute('aria-pressed', 'false');
        $('editor-redraw').textContent = 'Накреслити заново';
        $('editor-name').value = row.name;
        $('editor-order').value = row.unlock_order;
        $('editor-order').disabled = row.id === map.starting_location_id || row.features.port;
        $('editor-delete-sector').disabled = row.id === map.starting_location_id;
        route.replaceChildren(...locations.filter(other => other.id !== row.id).map(other => option(other.id, other.name)));
        updateRoutes();
        vertices();
        draw();
    }

    function updateRoutes() {
        const row = selected();
        $('editor-neighbors').replaceChildren(...row.connections.map(link => {
            const li = document.createElement('li');
            li.textContent = `${byId.get(link.location_id).name} · ${link.travel_time_seconds} с`;
            return li;
        }));
        const link = selectedRoute();
        $('editor-time').value = link?.travel_time_seconds ?? 2;
        $('editor-draw-route').disabled = !route.value;
        $('editor-draw-route').setAttribute('aria-pressed', String(routeDraft !== null));
        $('editor-undo-route').disabled = !routeDraft?.length;
        $('editor-delete-route').disabled = !link;
        $('editor-save-route').disabled = !route.value;
    }

    function changeRoute(seconds) {
        const first = selected();
        const second = byId.get(Number(route.value));
        if (!second) return;
        const waypoints = routeDraft ?? selectedRoute()?.waypoints ?? [];
        for (const [from, to] of [[first, second], [second, first]]) {
            from.connections = from.connections.filter(link => link.location_id !== to.id);
            if (seconds !== null) {
                const link = {location_id: to.id, travel_time_seconds: seconds};
                if (waypoints.length) link.waypoints = from === first ? [...waypoints] : [...waypoints].reverse();
                from.connections.push(link);
            }
            from.connections.sort((a, b) => a.location_id - b.location_id);
        }
        routeDraft = null;
        updateRoutes();
        draw();
    }

    function coordinate(event) {
        return geo.normalized(event, svg, map).map(value => Number(value.toFixed(8)));
    }

    function drawingPoint(event) {
        const coordinates = [map.playable_area.points, ...locations.map(row => row.geometry.points)];
        const matrix = svg.getScreenCTM();
        let best;
        let distance = 8;
        for (const vertices of coordinates) {
            for (const vertex of vertices) {
                const [x, y] = geo.point(...vertex, map);
                const screen = new DOMPoint(x, y).matrixTransform(matrix);
                const gap = Math.hypot(event.clientX - screen.x, event.clientY - screen.y);
                if (gap < distance) {
                    best = vertex;
                    distance = gap;
                }
            }
        }
        return best ?? coordinate(event);
    }

    function insertVertex(points, after, value) {
        if (!draft && mode !== 'trace' && after >= 0) {
            const key = geo.edgeKey(points[after], points[(after + 1) % points.length]);
            for (const row of locations) {
                if (row === selected()) continue;
                const ring = row.geometry.points;
                const index = geo.edgesOf(ring).findIndex(([a, b]) => geo.edgeKey(a, b) === key);
                if (index >= 0) ring.splice(index + 1, 0, value);
            }
        }
        points.splice(after + 1, 0, value);
    }

    function moveSharedVertex(previous, next) {
        for (const row of locations) {
            row.geometry.points = row.geometry.points.map(point => geo.samePoint(point, previous) ? next : point);
        }
    }

    svg.addEventListener('pointerdown', event => {
        if (preview.checked || event.button !== 0) return;
        if (routeDraft !== null) {
            routeDraft.push(coordinate(event));
            $('editor-undo-route').disabled = false;
            draw();
            return;
        }
        const edit = event.target.dataset.edit;
        const points = draft ?? selected().geometry.points;
        if (edit !== undefined) {
            dragging = edit === 'marker' ? edit : Number(edit);
            if (dragging !== 'marker') position = dragging;
            svg.setPointerCapture(event.pointerId);
        } else if (mode) {
            const at = mode === 'redraw' || mode === 'trace' || position < 0 ? points.length : position + 1;
            const point = drawingPoint(event);
            if (points.some(existing => geo.samePoint(existing, point))) return;
            insertVertex(points, at - 1, point);
            position = at;
        }
        vertices();
        draw();
    });
    svg.addEventListener('pointermove', event => {
        if (dragging === null) return;
        const [x, y] = coordinate(event);
        if (dragging === 'marker') selected().marker = {x, y};
        else if (draft) draft[dragging] = [x, y];
        else moveSharedVertex(selected().geometry.points[dragging], [x, y]);
        draw();
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        svg.addEventListener(event, () => { dragging = null; vertices(); });
    }

    $('editor-add').addEventListener('click', event => {
        if (draft || preview.checked) return;
        mode = mode ? '' : 'add';
        event.currentTarget.setAttribute('aria-pressed', String(Boolean(mode)));
    });
    $('editor-delete').addEventListener('click', () => {
        const points = draft ?? selected().geometry.points;
        if (position < 0 || (!draft && points.length <= 3) || preview.checked) return;
        if (draft) points.splice(position, 1);
        else {
            const previous = points[position];
            const affected = locations.filter(row => row.geometry.points.some(point => geo.samePoint(point, previous)));
            if (affected.some(row => row.geometry.points.length <= 3)) return;
            for (const row of affected) {
                row.geometry.points = row.geometry.points.filter(point => !geo.samePoint(point, previous));
            }
        }
        position = Math.min(position, (draft ?? selected().geometry.points).length - 1);
        vertices();
        draw();
    });
    $('editor-redraw').addEventListener('click', event => {
        if (preview.checked) return;
        if (draft && draft.length < 3) {
            feedback.textContent = 'Для завершення потрібні щонайменше три вершини.';
            return;
        }
        if (draft) {
            selected().geometry.points = draft;
            draft = null;
            mode = '';
        } else {
            draft = [];
            position = -1;
            mode = 'redraw';
        }
        event.currentTarget.setAttribute('aria-pressed', String(Boolean(draft)));
        event.currentTarget.textContent = draft ? 'Завершити полігон' : 'Накреслити заново';
        $('editor-add').setAttribute('aria-pressed', 'false');
        vertices();
        draw();
    });

    function renumberStages() {
        const ordered = [...locations].sort((a, b) => a.unlock_order - b.unlock_order);
        ordered.forEach((row, index) => { row.unlock_order = index + 1; });
    }

    $('editor-add-sector').addEventListener('click', () => {
        if (draft) { feedback.textContent = 'Спочатку заверши поточний полігон.'; return; }
        const occupiedKeys = new Set(locations.map(row => row.key));
        while (occupiedKeys.has(`sector_${nextId}`)) nextId++;
        const id = nextId++;
        map.next_location_id = nextId;
        const port = locations.find(row => row.features.port);
        const unlockOrder = port?.unlock_order ?? locations.length + 1;
        if (port) port.unlock_order++;
        const row = {
            id, key: `sector_${id}`, name: `Новий сектор ${id}`, biome: '', description: '',
            unlock_order: unlockOrder, unlocked_by_default: false,
            marker: {x: .5, y: .5}, geometry: {type: 'polygon', points: []},
            connections: [], features: {castle: false, enterprises: true, hunting: true,
                guilds: false, market: false, port: false},
        };
        locations.push(row);
        byId.set(id, row);
        preview.checked = false;
        updateLocations(id);
        $('editor-name').focus();
        feedback.textContent = 'Сектор додано до чернетки.';
    });

    $('editor-delete-sector').addEventListener('click', () => {
        const row = selected();
        if (row.id === map.starting_location_id || !window.confirm(`Видалити «${row.name}» з чернетки?`)) return;
        locations.splice(locations.indexOf(row), 1);
        byId.delete(row.id);
        for (const other of locations) {
            other.connections = other.connections.filter(link => link.location_id !== row.id);
        }
        for (const [key, id] of Object.entries(data.legacy_mapping ?? {})) {
            if (id === row.id) delete data.legacy_mapping[key];
        }
        renumberStages();
        updateLocations(map.starting_location_id);
        feedback.textContent = 'Сектор і його маршрути видалено з чернетки.';
    });

    vertex.addEventListener('change', () => { position = Number(vertex.value); draw(); vertices(); });
    location.addEventListener('change', select);
    route.addEventListener('change', () => {
        routeDraft = null;
        updateRoutes();
        draw();
    });
    $('editor-draw-route').addEventListener('click', event => {
        if (!route.value || preview.checked || draft) return;
        routeDraft = routeDraft === null ? [...(selectedRoute()?.waypoints ?? [])] : null;
        event.currentTarget.setAttribute('aria-pressed', String(routeDraft !== null));
        $('editor-undo-route').disabled = !routeDraft?.length;
        feedback.textContent = routeDraft ? 'Клацай на мапі, щоб додати проміжні точки. Потім збережи маршрут.' : '';
        draw();
    });
    $('editor-undo-route').addEventListener('click', () => {
        if (!routeDraft?.length) return;
        routeDraft.pop();
        $('editor-undo-route').disabled = !routeDraft.length;
        draw();
    });
    $('editor-load-boundaries').addEventListener('click', () => {
        for (const row of locations) {
            if (!row.geometry.points.length && originalBoundaries.has(row.id)) {
                row.geometry.points = originalBoundaries.get(row.id).map(point => [...point]);
            }
        }
        vertices();
        draw();
    });
    $('editor-save-route').addEventListener('click', () => {
        if ($('editor-time').reportValidity()) changeRoute(Number($('editor-time').value));
    });
    $('editor-delete-route').addEventListener('click', () => changeRoute(null));
    $('editor-name').addEventListener('change', event => {
        const name = event.target.value.trim();
        if (!name) { event.target.value = selected().name; return; }
        selected().name = name;
        location.selectedOptions[0].textContent = `${selected().id} · ${name}`;
        draw();
    });
    $('editor-order').addEventListener('change', event => {
        const order = Number(event.target.value);
        const row = selected();
        const other = locations.find(other => other.unlock_order === order);
        if (!other || order === 1 || row.features.port || other.features.port) {
            event.target.value = row.unlock_order;
            return;
        }
        [other.unlock_order, row.unlock_order] = [row.unlock_order, order];
        draw();
    });
    $('editor-stage').addEventListener('input', event => {
        $('editor-stage-value').textContent = event.target.value;
        preview.checked = true;
        draw();
    });
    preview.addEventListener('change', draw);
    $('editor-zoom').addEventListener('input', event => {
        geo.zoom(svg.parentElement, Number(event.target.value));
    });

    function downloadMap(contents, filename) {
        const url = URL.createObjectURL(new Blob([JSON.stringify(contents, null, 2) + '\n'], {type: 'application/json'}));
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    $('editor-save-draft').addEventListener('click', () => {
        const snapshot = structuredClone(data);
        if (draft !== null) {
            snapshot.locations.find(row => row.id === selected().id).geometry.points = draft;
        }
        downloadMap(snapshot, 'map_location.draft.json');
        feedback.textContent = 'Чернетку з усіма поточними вершинами завантажено.';
    });

    $('editor-export').addEventListener('click', () => {
        const error = draft ? 'Заверши редагування полігона.' : routeDraft !== null ? 'Збережи намальований маршрут.' : (geo.validateProgression(locations, map.starting_location_id) || geo.validateTopology(locations, map));
        if (error) { feedback.textContent = error + ' Щоб зберегти поточні межі, натисни «Зберегти чернетку».'; return; }
        downloadMap(data, 'map_location.json');
        feedback.textContent = 'Конфігурацію експортовано.';
    });

    geo.setup(svg, map);
    updateLocations(map.starting_location_id);
})();
