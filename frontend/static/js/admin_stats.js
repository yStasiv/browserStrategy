(() => {
    const format = new Intl.NumberFormat('uk-UA', {maximumFractionDigits: 2});
    const dateTime = new Intl.DateTimeFormat('uk-UA', {
        dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Kyiv',
    });
    const outcome = {win: 'Перемоги', loss: 'Поразки', draw: 'Нічиї', surrender: 'Капітуляції'};
    const outcomeColors = ['#496649', '#963f33', '#9a691c', '#60517a'];
    const status = document.getElementById('stats-status');
    const grid = document.getElementById('stats-grid');
    const controls = [...document.querySelectorAll('[data-period]')];
    const charts = [];
    let period = '7d';
    let request;
    let displayedSeries;

    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text != null) node.textContent = text;
        if (className) node.className = className;
        return node;
    }

    function section(key) {
        const node = document.getElementById('stats-' + key);
        node.replaceChildren();
        return node;
    }

    function table(parent, headings, rows) {
        if (!rows.length) {
            parent.append(element('p', 'Даних за період немає.', 'stats-note'));
            return;
        }
        const wrapper = element('div', null, 'stats-table-wrap');
        const node = element('table');
        const header = node.createTHead().insertRow();
        headings.forEach(heading => {
            const cell = element('th', heading);
            cell.scope = 'col';
            header.append(cell);
        });
        const body = node.createTBody();
        rows.forEach(row => {
            const tr = body.insertRow();
            row.forEach(value => {
                const cell = tr.insertCell();
                if (value instanceof Node) cell.append(value);
                else cell.textContent = typeof value === 'number' ? format.format(value) : value ?? '—';
            });
        });
        wrapper.append(node);
        parent.append(wrapper);
    }

    function metrics(parent, rows) {
        table(parent, ['Показник', 'Значення'], rows);
    }

    function subheading(node, title) {
        node.append(element('h3', title));
    }

    function percent(value) {
        return format.format(value) + '%';
    }

    function shopRows(node, data, categories) {
        table(node, ['Артефакт', 'Категорія', 'Рівень', 'Покупки'],
            data.map(row => [row.name, categories[row.item_type] ?? row.item_type, row.level, row.count]));
    }

    function renderCards(data) {
        const {combat, hunting, effects, shop, economy, players, integrity, labels, replays} = data;
        const battle = section('combat');
        metrics(battle, [['Завершені бої', combat.total], ['Середня кількість дій', combat.avg_actions],
            ['Нічиї за лімітом у 600 дій', combat.draw_cap]]);
        table(battle, ['Результат', 'Бої', 'Частка'], Object.entries(combat.outcomes).map(
            ([key, row]) => [outcome[key], row.count, percent(row.percent)]));
        battle.append(element('p', 'Перемоги й поразки визначаються для першої сторони з гравцем. Капітуляції рахуються окремо.', 'stats-note'));

        table(section('hunting'), ['Ціль', 'Полювання', 'Складність × кількість', 'Золото в середньому', 'Досвід у середньому'],
            hunting.map(row => [row.target, row.battles, Object.entries(row.difficulty).map(
                ([level, count]) => level + ' × ' + format.format(count)).join(', '), row.avg_gold, row.avg_xp]));

        const rolls = section('effects');
        const stats = {luck: 'Удача', morale: 'Мораль'};
        table(rolls, ['Характеристика', 'Знак', 'Перевірки', 'Спрацювання', 'Частка', 'Середній множник'],
            effects.rolls.map(row => [stats[row.stat], row.sign === 'positive' ? '+' : '−',
                row.checks, row.procs, percent(row.rate), row.avg_streak]));
        subheading(rolls, 'Виклик за рівнем Школи магії');
        table(rolls, ['Рівень Школи', 'Виклики'], Object.entries(effects.summons));

        const offers = section('shop');
        metrics(offers, [['Усього покупок', shop.total]]);
        subheading(offers, 'Найчастіше купували');
        shopRows(offers, shop.top, labels.categories);
        subheading(offers, 'Найрідше купували');
        shopRows(offers, shop.bottom, labels.categories);
        subheading(offers, 'Покупки за категорією');
        table(offers, ['Категорія', 'Покупки'], Object.entries(shop.categories).map(
            ([key, count]) => [labels.categories[key] ?? key, count]));
        subheading(offers, 'Покупки за рівнем артефакту');
        table(offers, ['Рівень', 'Покупки'], Object.entries(shop.levels));

        const currency = section('economy');
        const flow = economy.resources;
        table(currency, ['Ресурс', 'Нагороди', 'Магазин', 'Кузня', 'Усього витрачено', 'Повернено'],
            Object.entries(labels.resources).map(([key, label]) => [
                label, flow.earned[key], flow.shop[key], flow.repairs[key], flow.spent[key], flow.refunded[key],
            ]));
        subheading(currency, 'Кузня та Гільдія металознавців');
        const repair = economy.repairs;
        metrics(currency, [['Спроби ремонту', repair.attempts], ['Невдалі спроби', repair.failures],
            ['Частка невдач', percent(repair.failure_rate)], ['Повернено 50% вартості, золото', flow.refunded.gold],
            ['Предмети, що втратили останню одиницю міцності', repair.items_broken],
            ['Середні очки гільдії', repair.avg_guild_points], ['Максимальні очки гільдії', repair.max_guild_points]]);
        currency.append(element('p', 'Очки гільдії показано станом на зараз.', 'stats-note'));

        const heroes = section('players');
        metrics(heroes, [['Зареєстровані гравці', players.registered], ['Активні за період', players.active],
            ['Бої тривають', players.sessions.active], ['Триває розстановка', players.sessions.deployment]]);
        table(heroes, ['Рівень героя', 'Гравці'], Object.entries(players.levels));
        heroes.append(element('p', 'Рівні героїв і незавершені бої показано станом на зараз.', 'stats-note'));

        const catalog = section('integrity');
        catalog.append(element('p', integrity.ok ? 'Перевірку пройдено' : 'Є помилки',
            'stats-badge' + (integrity.ok ? ' is-ok' : '')));
        catalog.append(element('p', 'Перевірено записів: ' + format.format(integrity.checked)));
        if (integrity.issues.length) {
            table(catalog, ['Артефакт', 'Шлях зображення', 'Помилки'], integrity.issues.map(
                row => [row.name, row.image_url, row.errors.join(' ')]));
        }

        table(section('replays'), ['№', 'Завершено, Київ', 'Учасники / ціль', 'Результат', 'Дії', 'Повтор'],
            replays.map(row => {
                const link = row.replay_url ? element('a', 'Переглянути') : 'Недоступний';
                if (row.replay_url) {
                    link.href = row.replay_url;
                    link.target = '_blank';
                    link.rel = 'noopener';
                    link.setAttribute('aria-label', 'Переглянути повтор бою ' + row.id);
                }
                return [row.id, dateTime.format(new Date(row.at)), [...row.participants, row.target].filter(Boolean).join(' · '),
                    outcome[row.outcome], row.hit_cap ? format.format(row.actions) + ' (ліміт)' : row.actions, link];
            }));
    }

    function chart(parent, config, fallback) {
        const detail = element('details');
        detail.append(element('summary', 'Дані графіка'));
        parent.append(detail);
        fallback(detail);
        if (!window.Chart) {
            detail.open = true;
            return;
        }
        const frame = element('div', null, 'stats-chart');
        const canvas = element('canvas');
        canvas.setAttribute('aria-hidden', 'true');
        frame.append(canvas);
        parent.prepend(frame);
        try {
            charts.push(new window.Chart(canvas, {
                ...config, options: {responsive: true, maintainAspectRatio: false, ...config.options},
            }));
        } catch (error) {
            window.Chart.getChart?.(canvas)?.destroy();
            frame.remove();
            detail.open = true;
        }
    }

    function renderCharts(series) {
        charts.splice(0).forEach(instance => instance.destroy());
        const hourly = series.granularity === 'hourly';
        const tick = new Intl.DateTimeFormat('uk-UA', hourly
            ? {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC'}
            : {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
        const battles = series.battles;
        const money = series.economy;
        const keys = Object.keys(outcome);
        const stack = {x: {stacked: true}, y: {stacked: true, beginAtZero: true}};
        const battleChart = section('battle-trend');
        battleChart.append(element('p', 'Періоди графіків згруповано за UTC.', 'stats-note'));
        chart(battleChart, {type: 'bar', options: {scales: stack}, data: {
            labels: battles.map(row => tick.format(new Date(row.bucket))),
            datasets: keys.map((key, index) => ({
                label: outcome[key], data: battles.map(row => row[key]), backgroundColor: outcomeColors[index],
            })),
        }}, node => table(node, ['Період (UTC)', ...Object.values(outcome), 'Усього'], battles.map(
            row => [tick.format(new Date(row.bucket)), ...keys.map(key => row[key]), row.total])));

        chart(section('economy-trend'), {type: 'line', options: {scales: {y: {beginAtZero: true}}}, data: {
            labels: money.map(row => tick.format(new Date(row.bucket))),
            datasets: [['earned', 'Золото з нагород', '#496649'], ['spent', 'Витрачено золота', '#963f33']]
                .map(([key, label, color]) => ({
                    label, data: money.map(row => row[key].gold), borderColor: color,
                    pointRadius: money.length > 31 ? 0 : 2,
                })),
        }}, node => table(node, ['Період (UTC)', 'Нагороди', 'Магазин', 'Кузня', 'Витрачено', 'Повернено'],
            money.map(row => [tick.format(new Date(row.bucket)), row.earned.gold, row.shop.gold,
                row.repairs.gold, row.spent.gold, row.refunded.gold])));

        const items = section('item-trend');
        const pair = element('div', null, 'stats-chart-pair');
        items.append(pair);
        const {top_items: topItems, categories} = series.breakdowns;
        const popular = element('div');
        const shares = element('div');
        pair.append(popular, shares);
        for (const [node, title, rows, type, options, colors] of [
            [popular, 'Найпопулярніші', topItems, 'bar',
                {indexAxis: 'y', scales: {x: {beginAtZero: true}}, plugins: {legend: {display: false}}}, '#496649'],
            [shares, 'Частки категорій', categories.filter(row => row.value > 0), 'doughnut',
                {plugins: {legend: {position: 'bottom'}}},
                [...outcomeColors, '#765134', '#537878', '#6c7737', '#ab5a32', '#87576b', '#535965']],
        ]) {
            subheading(node, title);
            if (!rows.length) {
                node.append(element('p', 'Покупок за період немає.', 'stats-note'));
                continue;
            }
            chart(node, {type, options, data: {labels: rows.map(row => row.label),
                datasets: [{label: 'Покупки', data: rows.map(row => row.value), backgroundColor: colors}]}},
            target => table(target, ['Назва', 'Покупки'], rows.map(row => [row.label, row.value])));
        }
    }

    async function load() {
        request?.abort();
        const controller = new AbortController();
        request = controller;
        status.textContent = 'Завантаження статистики…';
        grid.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch('/admin/api/stats?period=' + encodeURIComponent(period), {
                signal: controller.signal, cache: 'no-store',
            });
            if (!response.ok) throw new Error(String(response.status));
            const data = await response.json();
            if (request !== controller) return;
            renderCards(data);
            displayedSeries = data.series;
            renderCharts(displayedSeries);
            controls.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.period === data.period)));
            const coverage = data.tracking_started_at
                ? ' Перший запис нових показників економіки: ' + dateTime.format(new Date(data.tracking_started_at)) + '.'
                : ' Журнал покупок, ремонтів і поломок поки порожній.';
            status.textContent = 'Оновлено ' + dateTime.format(new Date(data.generated_at)) + ' за Києвом.' + coverage;
        } catch (error) {
            if (request === controller) status.textContent = 'Не вдалося завантажити статистику. Натисни «Оновити».';
        } finally {
            if (request === controller) grid.setAttribute('aria-busy', 'false');
        }
    }

    controls.forEach(button => button.addEventListener('click', () => {
        period = button.dataset.period;
        load();
    }));
    document.getElementById('stats-refresh').addEventListener('click', load);
    document.getElementById('stats-chart-library').addEventListener('load', () => {
        if (displayedSeries && charts.length === 0) renderCharts(displayedSeries);
    });
    load();
})();
