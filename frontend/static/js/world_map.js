(() => {
    const byId = id => document.getElementById(id);
    const current = byId('world-current');
    const markers = byId('world-markers');
    const sectors = byId('world-sectors');
    const enterprises = byId('world-enterprises');
    const hunts = byId('world-hunts');
    const feedback = byId('world-feedback');
    const refresh = byId('world-refresh');
    const icons = {singing_resin: 'sawmill-icon.png', basalt_bone: 'mine-icon.png', gold: 'gold-mine-icon.png'};
    let state;
    let readAt;
    let busy = false;
    let timer;

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
        state = next;
        readAt = performance.now();
        current.textContent = `Поточний сектор · ${name(state.current_sector)}`;
        byId('world-work-notice').hidden = !state.work_blocks_travel;
        markers.replaceChildren();
        sectors.replaceChildren();
        const canTravel = !state.travel && !state.work_blocks_travel;
        for (const sector of state.sectors) {
            const here = sector.key === state.current_sector;
            const adjacent = sector.unlocked && sector.duration_seconds !== null;
            const card = element('li');
            card.classList.toggle('is-current', here);
            card.classList.toggle('is-adjacent', adjacent && canTravel);
            const detail = here ? 'Поточний сектор' : !sector.unlocked ? 'Заблокований' :
                adjacent ? `У дорозі ${sector.duration_seconds} с` : 'Поза прямим маршрутом';
            card.append(element('strong', sector.name), element('p', detail));
            if (adjacent) {
                const button = element('button', 'Вирушити');
                button.type = 'button';
                button.disabled = !canTravel;
                button.addEventListener('click', () => requestSector(sector.key));
                card.append(button);
            }
            sectors.append(card);

            if (sector.map_x === null || sector.map_y === null) continue;
            const interactive = adjacent && canTravel;
            const marker = element(interactive ? 'button' : 'span');
            marker.className = 'world-marker';
            marker.classList.toggle('is-current', here);
            marker.classList.toggle('is-adjacent', interactive);
            marker.classList.toggle('is-locked', !sector.unlocked);
            marker.classList.toggle('is-destination', sector.key === state.travel?.destination);
            marker.style.left = `${sector.map_x}%`;
            marker.style.top = `${sector.map_y}%`;
            marker.title = sector.name;
            if (interactive) {
                marker.type = 'button';
                marker.setAttribute('aria-label', `Вирушити до сектора «${sector.name}», ${sector.duration_seconds} с`);
                marker.addEventListener('click', () => requestSector(sector.key));
            } else {
                marker.setAttribute('aria-hidden', 'true');
            }
            markers.append(marker);
        }

        enterprises.replaceChildren(...state.enterprises.map(entry => {
            const item = element('li');
            const link = element('a', entry.name);
            link.href = `/enterprise/${entry.id}`;
            if (icons[entry.resource_type]) {
                const icon = element('img');
                icon.src = `/static/images/${icons[entry.resource_type]}`;
                icon.alt = '';
                icon.className = 'world-enterprise-icon';
                link.prepend(icon);
            }
            item.append(link,
                element('p', `Працівники ${entry.workers_count}/${entry.max_workers} · Склад ${entry.resource_stored}/${entry.max_storage}`),
                element('p', `Площа ${entry.area} · Зарплата ${entry.salary} золота/год`));
            return item;
        }));
        hunts.replaceChildren(...state.hunts.map(hunt => {
            const item = element('li');
            item.append(
                element('strong', `${hunt.icon} ${hunt.name} ×${hunt.count}`),
                element('p', `${hunt.difficulty} · від рівня ${hunt.min_level}`),
                element('p', `За перемогу ${hunt.gold_min}–${hunt.gold_max} золота та ${hunt.xp} XP`),
            );
            const button = element('button', 'Почати полювання');
            button.type = 'button';
            button.disabled = !hunt.available;
            button.addEventListener('click', () => startHunt(hunt.key));
            item.append(button);
            return item;
        }));
        byId('world-hunt-feedback').textContent = state.travel ? 'Недоступно під час подорожі.' : '';
        byId('world-enterprise-message').textContent = state.travel ? 'Недоступні під час подорожі.' :
            state.enterprises.length ? '' : 'У цьому секторі немає підприємств.';
        byId('world-castle-links').hidden = Boolean(state.travel) || state.current_sector !== 'Castle';
        byId('world-travel').hidden = !state.travel;
        if (state.travel) {
            byId('world-travel-label').textContent = `${name(state.travel.origin)} → ${name(state.travel.destination)}`;
            tick();
        }
    }

    function tick() {
        const ends = Date.parse(state.travel.arrives_at);
        const starts = Date.parse(state.travel.started_at);
        const now = Date.parse(state.server_time) + performance.now() - readAt;
        const remaining = Math.max(0, ends - now);
        byId('world-progress').value = Math.max(0, Math.min(1, (now - starts) / (ends - starts)));
        byId('world-time').textContent = remaining ? `Залишилось ${Math.ceil(remaining / 1000)} с` : 'Перевіряємо прибуття…';
        timer = setTimeout(remaining ? tick : refreshState, remaining ? Math.min(200, remaining + 10) : 50);
    }

    async function getState(url, options) {
        const response = await fetch(url, {cache: 'no-store', ...options});
        if (response.ok) return response.json();
        const error = await response.json().catch(() => null);
        throw new Error(typeof error?.detail === 'string' ? error.detail : 'Не вдалося оновити стан карти.');
    }

    async function refreshState() {
        refresh.hidden = true;
        try {
            const previous = state.travel;
            const updated = await getState('/api/world');
            render(updated);
            feedback.textContent = previous && !updated.travel ? `Прибуття · ${name(updated.current_sector)}` : '';
        } catch (error) {
            feedback.textContent = error.message;
            refresh.hidden = false;
        }
    }

    async function startHunt(key) {
        if (busy) return;
        busy = true;
        const buttons = [...hunts.querySelectorAll('button:not(:disabled)')];
        buttons.forEach(button => { button.disabled = true; });
        try {
            await getState('/api/battles/hunt/' + encodeURIComponent(key), {method: 'POST'});
            location.assign('/battle');
        } catch (error) {
            byId('world-hunt-feedback').textContent = error.message;
            buttons.forEach(button => { button.disabled = false; });
            busy = false;
        }
    }

    async function requestSector(key) {
        if (busy) return;
        busy = true;
        const buttons = [...sectors.querySelectorAll('button'), ...markers.querySelectorAll('button')];
        buttons.forEach(button => { button.disabled = true; });
        try {
            render(await getState('/move-to-sector', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sector: key}),
            }));
            feedback.textContent = 'Подорож розпочато.';
        } catch (error) {
            feedback.textContent = error.message;
            refresh.hidden = false;
            buttons.forEach(button => { button.disabled = false; });
        } finally {
            busy = false;
        }
    }

    refresh.addEventListener('click', refreshState);
    render(JSON.parse(byId('world-state').textContent));
})();
