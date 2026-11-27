(() => {
    const byId = id => document.getElementById(id);
    const markers = byId('world-markers');
    const fogLayer = byId('world-fog');
    const art = byId('world-art');
    const viewport = byId('world-map-viewport');
    const enterpriseTabs = [...document.querySelectorAll('[data-production-type]')];
    const hunts = byId('world-hunts');
    const huntFeedback = byId('world-hunt-feedback');
    const huntCooldown = byId('world-hunt-cooldown');
    const feedback = byId('world-feedback');
    const refresh = byId('world-refresh');
    const moveSelected = byId('world-travel-selected');
    const number = new Intl.NumberFormat('en-US');
    const enterpriseIcon = '/static/images/buildings/build.png';
    let state;
    let readAt;
    let busy = false;
    let timer;
    let huntTimer;
    let feedbackTimer;
    let selectedLocation;
    let moveAnchor;
    let outlineInnerEdge;
    let fogSignature;
    let fogTimer;
    let travelerMarker;
    let travelerPosition;
    let travelFrame;
    const revealed = new Map();

    function name(key) {
        return state.sectors.find(sector => sector.key === key)?.name ?? key;
    }

    function element(tag, text) {
        const node = document.createElement(tag);
        if (text) node.textContent = text;
        return node;
    }

    function render(next) {
        clearTimeout(timer);
        clearTimeout(huntTimer);
        if (travelFrame !== undefined) cancelAnimationFrame(travelFrame);
        travelFrame = undefined;
        const known = state && new Set(state.sectors.map(row => row.id));
        const changedOrigin = state && state.current_sector !== next.current_sector;
        state = next;
        if (state.travel || changedOrigin) selectedLocation = null;
        if (known) {
            for (const row of state.sectors) {
                if (row.id && !known.has(row.id)) revealed.set(row.id, performance.now());
            }
        }
        readAt = performance.now();
        renderGeography();
        selectSector(state.sectors.find(row => (row.id ?? row.key) === selectedLocation));
        renderEnterprises();
        hunts.replaceChildren(...state.hunts.map(hunt => {
            const item = element('li');
            const heading = element('div');
            heading.className = 'world-hunt-heading';
            const portrait = element('a');
            portrait.className = 'world-hunt-portrait';
            portrait.href = `/unit_info?key=${encodeURIComponent(hunt.key)}`;
            portrait.setAttribute('aria-label', `Про істоту «${hunt.name}», кількість: ${number.format(hunt.count)}`);
            if (hunt.image_url) {
                const icon = element('img');
                icon.alt = '';
                icon.addEventListener('error', () => icon.replaceWith(hunt.icon), {once: true});
                icon.src = hunt.image_url;
                portrait.append(icon);
            } else {
                const icon = element('span', hunt.icon);
                icon.setAttribute('aria-hidden', 'true');
                portrait.append(icon);
            }
            const count = element('span', number.format(hunt.count));
            count.className = 'world-hunt-count';
            portrait.append(count);
            heading.append(portrait, element('strong', hunt.name));
            item.append(
                heading,
                element('p', `Складність ${number.format(hunt.difficulty)} · від рівня ${hunt.min_level}`),
                element('p', `За перемогу ${hunt.gold_min}–${hunt.gold_max} золота й 1 очко Братства ловців`),
            );
            const button = element('button', 'Почати полювання');
            button.type = 'button';
            button.disabled = !hunt.available;
            button.addEventListener('click', () => startHunt(hunt));
            item.append(button);
            return item;
        }));
        huntFeedback.textContent = state.travel ? 'Недоступно під час подорожі.' : '';
        tickHuntCooldown();
        const guildAvailable = !state.travel && state.sectors.some(row => row.key === state.current_sector && row.features?.guilds);
        byId('world-guild-link').hidden = !guildAvailable;
        byId('world-guild-name').hidden = guildAvailable;
        byId('world-travel').hidden = !state.travel;
        if (state.travel) {
            byId('world-travel-label').textContent = `${name(state.travel.origin)} → ${name(state.travel.destination)}`;
            animateTraveler();
            tick();
        }
    }

    function positionMoveIcon() {
        if (!moveAnchor) return;
        const image = art.getBoundingClientRect();
        const bounds = viewport.getBoundingClientRect();
        const x = image.left + moveAnchor.x * image.width - bounds.left;
        const y = image.top + moveAnchor.y * image.height - bounds.top;
        const size = moveSelected.offsetWidth;
        const position = (value, limit) => Math.max(0, Math.min(limit - size, value - size / 2));
        moveSelected.style.left = `${position(x, viewport.clientWidth)}px`;
        moveSelected.style.top = `${position(y, viewport.clientHeight)}px`;
    }

    function selectSector(sector, event) {
        const available = WorldGeography.canSelect(state, sector);
        const id = available ? (sector.id ?? sector.key) : null;
        if (available && Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY)) {
            const image = art.getBoundingClientRect();
            moveAnchor = {x: (event.clientX - image.left) / image.width, y: (event.clientY - image.top) / image.height};
        } else if (!available || id !== selectedLocation) {
            moveAnchor = available ? (sector.marker ?? {x: .5, y: .5}) : null;
        }
        selectedLocation = id;
        moveSelected.hidden = !available;
        moveSelected.disabled = busy;
        if (available) {
            const label = `Переміститися · ${sector.name} (${sector.duration_seconds} с)`;
            moveSelected.title = label;
            moveSelected.setAttribute('aria-label', label);
            positionMoveIcon();
        }
        for (const polygon of markers.querySelectorAll('[data-sector]')) {
            polygon.classList.toggle('is-selected', available && polygon.dataset.sector === sector.key);
        }
    }

    function renderFog() {
        const {map, fog_of_war: settings} = state;
        const mapped = state.sectors.filter(row => row.geometry);
        const signature = mapped.map(row => row.id).join(',');
        if (signature === fogSignature) return;
        fogSignature = signature;
        clearTimeout(fogTimer);
        const animation = new Set([...revealed].filter(([, began]) =>
            performance.now() - began < settings.reveal_duration_ms).map(([id]) => id));
        revealed.clear();
        WorldGeography.setup(fogLayer, map);
        fogLayer.replaceChildren();
        if (settings.enabled || animation.size) {
            WorldGeography.fog(fogLayer, map, {...settings, enabled: true}, mapped, animation);
        }
        if (!settings.enabled && animation.size) {
            fogTimer = setTimeout(() => fogLayer.replaceChildren(), settings.reveal_duration_ms);
        }
    }

    function scaleSectorOutlines() {
        if (!outlineInnerEdge || !art.clientWidth) return;
        const scale = state.map.width / art.clientWidth;
        outlineInnerEdge.setAttribute('radius', 2 * scale);
    }

    function renderGeography() {
        const {map} = state;
        const geo = WorldGeography;
        const mapped = state.sectors.filter(row => row.geometry);
        renderFog();
        geo.setup(markers, map);
        markers.replaceChildren();
        const defs = geo.svgNode('defs');
        const inset = geo.svgNode('filter', {id: 'world-sector-inset', filterUnits: 'userSpaceOnUse',
            x: 0, y: 0, width: map.width, height: map.height});
        outlineInnerEdge = geo.svgNode('feMorphology', {in: 'SourceGraphic', operator: 'erode', result: 'inner'});
        inset.append(outlineInnerEdge, geo.svgNode('feComposite', {in: 'SourceGraphic', in2: 'inner', operator: 'out'}));
        defs.append(inset);
        markers.append(defs);
        scaleSectorOutlines();

        for (const sector of mapped) {
            const polygon = geo.svgNode('polygon', {points: geo.points(sector, map), class: 'world-location'});
            if (geo.canSelect(state, sector)) {
                polygon.setAttribute('tabindex', 0);
                polygon.setAttribute('role', 'button');
                polygon.setAttribute('aria-label', sector.name);
            }
            polygon.dataset.sector = sector.key;
            polygon.classList.toggle('is-current', sector.key === state.current_sector);
            polygon.classList.toggle('is-adjacent', geo.canSelect(state, sector));
            const title = geo.svgNode('title');
            title.textContent = sector.duration_seconds === null ? sector.name : `${sector.name} · ${sector.duration_seconds} с`;
            polygon.append(title);
            polygon.addEventListener('click', event => { event.stopPropagation(); selectSector(sector, event); });
            polygon.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    selectSector(sector);
                    if (!moveSelected.hidden) moveSelected.focus();
                }
            });
            markers.append(polygon);
            if (sector.key === state.current_sector || geo.canSelect(state, sector)) {
                const outline = geo.svgNode('g', {class: 'world-location-outline', 'aria-hidden': 'true'});
                outline.append(geo.svgNode('polygon', {points: geo.points(sector, map),
                    filter: 'url(#world-sector-inset)'}));
                markers.append(outline);
            }
        }

        travelerMarker = geo.svgNode('circle', {r: 11, class: 'world-traveler'});
        markers.append(travelerMarker);
        const origin = state.sectors.find(row => row.key === (state.travel?.origin ?? state.current_sector))?.marker;
        const destination = state.sectors.find(row => row.key === state.travel?.destination)?.marker ?? origin;
        travelerPosition = origin ? geo.routeSampler(origin, destination, state.travel?.waypoints ?? [], map) : null;
        travelerMarker.toggleAttribute('hidden', !travelerPosition);
        placeTraveler(0);
    }

    function placeTraveler(progress) {
        if (!travelerPosition) return;
        const [cx, cy] = travelerPosition(progress);
        travelerMarker.setAttribute('cx', cx);
        travelerMarker.setAttribute('cy', cy);
    }

    function animateTraveler() {
        if (!travelerPosition) return;
        const starts = Date.parse(state.travel.started_at);
        const ends = Date.parse(state.travel.arrives_at);
        const serverTime = Date.parse(state.server_time);
        function frame() {
            const now = serverTime + performance.now() - readAt;
            placeTraveler((now - starts) / (ends - starts));
            travelFrame = now < ends ? requestAnimationFrame(frame) : undefined;
        }
        frame();
    }

    function renderEnterprises() {
        const tab = enterpriseTabs.find(tab => tab.getAttribute('aria-selected') === 'true');
        const panel = byId(tab.getAttribute('aria-controls'));
        const entries = state.enterprises.filter(entry => entry.production_type === tab.dataset.productionType);
        panel.querySelector('[data-enterprise-message]').textContent = state.travel ? 'Недоступні під час подорожі.' :
            entries.length ? '' : 'У цьому секторі немає підприємств цього типу.';
        panel.querySelector("ul").replaceChildren(...entries.map(entry => {
            const item = element('li');
            item.className = 'world-enterprise-row';
            const link = element('a');
            link.href = `/enterprise/${entry.id}`;
            link.title = entry.name;
            const icon = element('img');
            icon.alt = '';
            icon.className = 'world-enterprise-icon';
            if (entry.image_url) icon.addEventListener('error', () => { icon.src = enterpriseIcon; }, {once: true});
            icon.src = entry.image_url || enterpriseIcon;
            link.append(icon, element('span', entry.name));
            if (entry.construction) {
                const phase = entry.construction;
                if (phase.paused) {
                    item.append(link, element('span', phase.stage));
                    return item;
                }
                const percent = phase.started_at
                    ? Math.max(0, Math.min(100, 100 * (Date.parse(state.server_time) - Date.parse(phase.started_at)) /
                        (Date.parse(phase.completion_at) - Date.parse(phase.started_at))))
                    : phase.progress;
                const remaining = phase.completion_at ? Math.max(0, (Date.parse(phase.completion_at) - Date.parse(state.server_time)) / 1000) : 0;
                item.append(link, element('span', phase.stage),
                    element('span', `${Math.floor(percent)}%${remaining ? ` · ${Math.ceil(remaining / 3600)} год` : ''}`));
                return item;
            }
            const stock = element('span', `${number.format(entry.resource_stored)}/${number.format(entry.max_storage)}`);
            stock.title = 'Ресурси на складі / місткість складу';
            const salary = element('span', `${number.format(entry.salary)} зол./год`);
            salary.title = 'Базова зарплата';
            item.append(link, stock, salary);
            return item;
        }));
    }

    function selectEnterpriseTab(selected) {
        for (const tab of enterpriseTabs) {
            const active = tab === selected;
            tab.setAttribute('aria-selected', String(active));
            tab.tabIndex = active ? 0 : -1;
            byId(tab.getAttribute('aria-controls')).hidden = !active;
        }
        renderEnterprises();
    }

    enterpriseTabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectEnterpriseTab(tab));
        tab.addEventListener('keydown', event => {
            const size = enterpriseTabs.length;
            const next = {
                ArrowLeft: (index + size - 1) % size, ArrowRight: (index + 1) % size,
                Home: 0, End: size - 1,
            }[event.key];
            if (next === undefined) return;
            event.preventDefault();
            selectEnterpriseTab(enterpriseTabs[next]);
            enterpriseTabs[next].focus();
        });
    });

    function tick() {
        const ends = Date.parse(state.travel.arrives_at);
        const starts = Date.parse(state.travel.started_at);
        const now = Date.parse(state.server_time) + performance.now() - readAt;
        const remaining = Math.max(0, ends - now);
        const progress = Math.max(0, Math.min(1, (now - starts) / (ends - starts)));
        byId('world-progress').value = progress;
        byId('world-time').textContent = remaining ? `Залишилось ${Math.ceil(remaining / 1000)} с` : 'Перевіряємо прибуття…';
        timer = setTimeout(remaining ? tick : refreshState, remaining ? Math.min(200, remaining + 10) : 50);
    }

    function tickHuntCooldown() {
        const now = Date.parse(state.server_time) + performance.now() - readAt;
        const remaining = state.hunt_ready_at ? Math.max(0, Date.parse(state.hunt_ready_at) - now) : 0;
        const seconds = Math.ceil(remaining / 1000);
        hunts.hidden = seconds > 0;
        huntCooldown.hidden = seconds === 0;
        if (!seconds) return;
        const minutes = Math.floor(seconds / 60);
        byId('world-hunt-countdown').textContent = `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
        huntTimer = setTimeout(tickHuntCooldown, (remaining - (seconds - 1) * 1000) + 5);
    }

    function showArmyRequired() {
        const link = element('a', 'Набрати військо');
        link.href = '/castle?section=army';
        huntFeedback.replaceChildren('Спочатку набери військо в Замку. ', link);
    }

    async function getState(url, options) {
        const response = await fetch(url, {cache: 'no-store', ...options});
        if (response.ok) return response.json();
        const error = await response.json().catch(() => null);
        const detail = error?.detail;
        const failure = new Error(typeof detail === 'string' ? detail : detail?.message ?? 'Не вдалося оновити стан карти.');
        failure.code = detail?.code;
        throw failure;
    }

    function showFeedback(message, duration) {
        clearTimeout(feedbackTimer);
        feedback.textContent = message;
        if (duration) feedbackTimer = setTimeout(() => { feedback.textContent = ''; }, duration);
    }

    async function refreshState() {
        refresh.hidden = true;
        try {
            const previous = state.travel;
            const updated = await getState('/api/world');
            render(updated);
            if (previous && !updated.travel) {
                if (previous.destination === updated.current_sector) {
                    showFeedback(`Прибуття · ${name(updated.current_sector)}`, 2000);
                } else {
                    showFeedback('Подорож скасовано.');
                }
            } else {
                showFeedback('');
            }
        } catch (error) {
            showFeedback(error.message);
            refresh.hidden = false;
        }
    }

    async function startHunt(hunt) {
        if (busy || hunts.hidden) return;
        if (state.hunt_has_army === false) {
            showArmyRequired();
            return;
        }
        busy = true;
        const buttons = [...hunts.querySelectorAll('button:not(:disabled)')];
        buttons.forEach(button => { button.disabled = true; });
        try {
            await getState(`/api/battles/hunt/${encodeURIComponent(hunt.key)}?difficulty=${hunt.difficulty}`, {method: 'POST'});
            location.assign('/battle');
        } catch (error) {
            if (error.code === 'army_required' || error.message === 'Спочатку набери військо в Замку.') {
                showArmyRequired();
            } else {
                huntFeedback.textContent = error.message;
                refresh.hidden = false;
            }
            buttons.forEach(button => { button.disabled = false; });
            busy = false;
        }
    }

    async function requestSector(key) {
        if (busy) return;
        busy = true;
        moveSelected.disabled = true;
        try {
            render(await getState('/move-to-sector', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sector: key}),
            }));
            showFeedback('Подорож розпочато.');
        } catch (error) {
            showFeedback(error.message);
            refresh.hidden = false;
        } finally {
            busy = false;
            moveSelected.disabled = false;
        }
    }

    refresh.addEventListener('click', refreshState);
    art.addEventListener('click', () => selectSector(null));
    viewport.addEventListener('scroll', positionMoveIcon, {passive: true});
    new ResizeObserver(() => {
        positionMoveIcon();
        scaleSectorOutlines();
    }).observe(art);
    moveSelected.addEventListener('click', () => {
        const destination = state.sectors.find(row => (row.id ?? row.key) === selectedLocation);
        if (WorldGeography.canSelect(state, destination)) requestSector(destination.key);
    });
    setInterval(async () => {
        if (busy || document.hidden) return;
        try {
            if (state.enterprises.some(site => site.construction)) {
                await refreshState();
                return;
            }
            const next = await getState('/api/world/progression');
            const known = new Set(state.sectors.map(row => row.key));
            if (!busy && (next.active_construction || next.unlocked.length !== known.size || next.unlocked.some(key => !known.has(key)))) {
                await refreshState();
            }
        } catch { /* manual refresh remains available for an interrupted connection */ }
    }, 5000);
    render(JSON.parse(byId('world-state').textContent));
})();
