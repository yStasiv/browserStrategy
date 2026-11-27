(() => {
    const $ = id => document.getElementById(id);
    const geo = WorldGeography;
    const svg = $('admin-map-layer');
    const next = $('unlock-next');
    const feedback = $('map-admin-feedback');
    const fog = $('hide-fog');
    const borders = $('show-map-borders');
    const format = new Intl.NumberFormat('uk-UA', {maximumFractionDigits: 2});
    let world = JSON.parse($('map-admin-data').textContent);
    let revealing = new Set();
    let busy = false;

    function drawMap() {
        const {locations, map, fog_of_war: settings} = world.config;
        const open = new Set(world.status.filter(row => row.unlocked).map(row => row.id));
        svg.replaceChildren();
        geo.setup(svg, map);
        if (fog.checked && (open.size < locations.length || revealing.size)) {
            geo.fog(svg, map, settings, locations.filter(row => open.has(row.id)), revealing);
        }
        if (!borders.checked) return;
        for (const row of locations) {
            if (fog.checked && !open.has(row.id)) continue;
            const polygon = geo.svgNode('polygon', {points: geo.points(row, map), class: 'editor-boundary'});
            const title = geo.svgNode('title');
            title.textContent = row.name;
            polygon.append(title);
            svg.append(polygon);
        }
    }

    function table() {
        const locations = [...world.config.locations].sort((a, b) => a.unlock_order - b.unlock_order);
        const byKey = new Map(locations.map(row => [row.key, row]));
        const status = new Map(world.status.map(row => [row.id, row]));
        const areas = geo.areaStats(locations, world.config.map);
        const open = world.status.filter(row => row.unlocked).length;
        const openKeys = new Set(world.open_keys);
        $('unlocked-count').textContent = `Відкрито ${open} / ${locations.length}`;
        next.disabled = busy || open === locations.length;
        const body = $('map-admin-locations');
        body.replaceChildren();
        for (const row of locations) {
            const tr = body.insertRow();
            const details = status.get(row.id);
            tr.insertCell().textContent = `${row.unlock_order}. ${row.name}`;
            tr.insertCell().textContent = details?.unlocked ? 'Відкрита' : 'Закрита';
            const neighbors = Object.entries(details?.neighbors ?? {});
            tr.insertCell().textContent = neighbors.map(([key, seconds]) =>
                `${byKey.get(key)?.name ?? key} (${seconds} с)`).join(', ');
            const area = areas.get(row.id);
            const areaCell = tr.insertCell();
            areaCell.textContent = `${format.format(area.actual)} / ${format.format(area.target)} пікс.² · ${format.format(area.deviation)}%`;
            const action = tr.insertCell();
            if (details?.unlocked_at) {
                action.textContent = new Intl.DateTimeFormat('uk-UA', {dateStyle: 'short', timeStyle: 'short',
                    timeZone: 'Europe/Kyiv'}).format(new Date(details.unlocked_at));
            }
            if (details?.unlocked && row.id !== world.config.map.starting_location_id) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = 'Закрити';
                button.disabled = busy;
                button.addEventListener('click', () => {
                    if (window.confirm(`Закрити сектор «${row.name}»?`)) {
                        changeLocation(`/admin/map/locations/${row.id}/close`, true);
                    }
                });
                action.append(' ', button);
            } else if (!details?.unlocked) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = 'Відкрити';
                button.disabled = busy || !neighbors.some(([key]) => openKeys.has(key));
                button.addEventListener('click', () => changeLocation(`/admin/map/locations/${row.id}/unlock`));
                action.append(button);
            }
        }
    }

    async function changeLocation(url, closing = false) {
        if (busy) return;
        busy = true;
        table();
        try {
            const response = await fetch(url, {method: 'POST'});
            const result = await response.json();
            if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Не вдалося змінити доступність локації.');
            const previouslyOpen = new Set(world.status.filter(row => row.unlocked).map(row => row.id));
            world = result;
            revealing = new Set(result.status.filter(row => row.unlocked && !previouslyOpen.has(row.id)).map(row => row.id));
            feedback.textContent = result.changed
                ? (closing ? 'Закрито · ' : 'Відкрито · ') + result.config.locations.find(row => row.id === result.location_id).name
                : (closing ? 'Локація вже закрита.' : 'Локація вже відкрита.');
            drawMap();
            setTimeout(() => { revealing.clear(); drawMap(); }, world.config.fog_of_war.reveal_duration_ms);
        } catch (error) {
            feedback.textContent = error.message;
        } finally {
            busy = false;
            table();
        }
    }

    next.addEventListener('click', () => changeLocation('/admin/map/unlock-next'));
    fog.addEventListener('change', drawMap);
    borders.addEventListener('change', drawMap);
    drawMap();
    table();
})();
