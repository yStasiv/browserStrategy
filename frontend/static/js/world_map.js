(() => {
    const byId = id => document.getElementById(id);
    const current = byId('world-current');
    const markers = byId('world-markers');
    const sectors = byId('world-sectors');
    const enterpriseTabs = [...document.querySelectorAll('[data-production-type]')];
    const hunts = byId('world-hunts');
    const huntFeedback = byId('world-hunt-feedback');
    const huntCooldown = byId('world-hunt-cooldown');
    const feedback = byId('world-feedback');
    const refresh = byId('world-refresh');
    const number = new Intl.NumberFormat('en-US');
    const enterpriseIcon = '/static/images/buildings/build.png';
    let state;
    let readAt;
    let busy = false;
    let timer;
    let huntTimer;

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
        const guildAvailable = !state.travel && state.current_sector === 'Castle';
        byId('world-guild-link').hidden = !guildAvailable;
        byId('world-guild-name').hidden = guildAvailable;
        byId('world-travel').hidden = !state.travel;
        if (state.travel) {
            byId('world-travel-label').textContent = `${name(state.travel.origin)} → ${name(state.travel.destination)}`;
            tick();
        }
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
        byId('world-progress').value = Math.max(0, Math.min(1, (now - starts) / (ends - starts)));
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
