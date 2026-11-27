(() => {
    const root = document.getElementById('admin-events');
    if (!root) return;
    const byId = id => document.getElementById(id);
    const eventId = root.dataset.event;
    const endpoint = eventId ? `/admin/events/${eventId}` : '/admin/events';
    const feedback = byId('event-feedback');
    const draft = byId('event-draft');
    const rewardForm = byId('event-reward-form');
    let busy = false;

    async function request(url, method, payload, upload = false) {
        const response = await fetch(url, {
            method,
            headers: upload ? undefined : {'Content-Type': 'application/json'},
            body: upload ? payload : JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok) {
            const message = Array.isArray(result.detail)
                ? result.detail.map(error => `${error.loc.slice(1).join('.')} · ${error.msg}`).join(' / ')
                : result.detail;
            throw new Error(message || 'Операцію не вдалося виконати.');
        }
        return result;
    }

    async function run(action, button) {
        if (busy) return;
        busy = true;
        if (button) button.disabled = true;
        feedback.textContent = '';
        try { await action(); }
        catch (error) { feedback.textContent = error.message; }
        finally {
            busy = false;
            if (button) button.disabled = false;
        }
    }

    function amounts(container, attribute) {
        return Object.fromEntries([...container.querySelectorAll(`[data-${attribute}]`)]
            .filter(input => input.valueAsNumber > 0)
            .map(input => [input.getAttribute(`data-${attribute}`), input.valueAsNumber]));
    }

    const features = JSON.parse(byId('event-catalog').textContent);

    async function uploadImage(file) {
        if (!file) throw new Error('Обери файл зображення.');
        const data = new FormData();
        data.append('image', file);
        return (await request('/admin/events/image', 'POST', data, true)).image_url;
    }

    function imageValues(container) {
        return Object.fromEntries([...container.querySelectorAll('[data-stage-image]')]
            .map(input => [input.dataset.stageImage, input.value.trim()]));
    }

    function setupArtwork(container, getDefaults) {
        const previews = [];
        for (const row of container.querySelectorAll('[data-stage-row]')) {
            const input = row.querySelector('[data-stage-image]');
            const preview = row.querySelector('[data-stage-preview]');
            function updatePreview() {
                const value = input.value.trim() || getDefaults()[input.dataset.stageImage];
                preview.hidden = !value?.startsWith('/static/images/');
                if (preview.hidden) preview.removeAttribute('src');
                else preview.src = value;
            }
            input.addEventListener('input', updatePreview);
            row.querySelector('[data-stage-upload]').addEventListener('click', event => run(async () => {
                input.value = await uploadImage(row.querySelector('[data-stage-file]').files[0]);
                updatePreview();
            }, event.currentTarget));
            previews.push(updatePreview);
        }
        const update = () => previews.forEach(preview => preview());
        update();
        return update;
    }

    for (const form of root.querySelectorAll('[data-standalone-artwork]')) {
        setupArtwork(form, () => features[form.dataset.mineType].images);
        form.addEventListener('submit', event => {
            event.preventDefault();
            run(async () => {
                await request(`${endpoint}/enterprises/${form.dataset.standaloneArtwork}/images`, 'PATCH',
                    {stage_images: imageValues(form)});
                form.querySelector('[data-artwork-feedback]').textContent = 'Зображення збережено.';
            }, event.submitter);
        });
    }

    if (draft) {
        const projects = byId('event-projects');
        const art = byId('event-artwork-preview');
        function previewImage() {
            const path = draft.elements.image_url.value.trim();
            art.hidden = !path.startsWith('/static/images/');
            if (art.hidden) art.removeAttribute('src');
            else art.src = path;
        }
        draft.elements.image_url.addEventListener('input', previewImage);
        const fields = ['area', 'salary', 'item_price', 'max_workers', 'max_storage', 'balance'];
        function addProject(data = {}) {
            const node = byId('event-project-template').content.firstElementChild.cloneNode(true);
            const adopt = node.querySelector('[name="adopt_placeholder"]');
            const type = node.querySelector('[name="enterprise_type"]');
            if (data.enterprise_type) type.value = data.enterprise_type;
            adopt.checked = Boolean(data.adopt_placeholder);
            node.querySelector('[name="name"]').value = data.name ?? '';
            for (const input of node.querySelectorAll('[data-stage-image]')) {
                input.value = data.stage_images?.[input.dataset.stageImage] ?? '';
            }
            const updateArtwork = setupArtwork(node, () => features[type.value].images);
            type.addEventListener('change', updateArtwork);
            function toggleAdoption() {
                adopt.disabled = draft.elements.sector.value !== 'Castle' || !features[type.value].placeholder_id;
                if (adopt.disabled) adopt.checked = false;
            }
            type.addEventListener('change', toggleAdoption);
            toggleAdoption();
            for (const field of fields) node.querySelector(`[name="${field}"]`).value = data[field] ?? '';
            for (const input of node.querySelectorAll('[data-requirement]')) {
                input.value = data.requirements?.[input.dataset.requirement] ?? '';
            }
            node.querySelector('[data-remove-project]').addEventListener('click', () => node.remove());
            projects.append(node);
        }
        const saved = JSON.parse(byId('event-configuration').textContent);
        for (const project of saved.length ? saved : [{}]) addProject(project);
        byId('event-add-project').addEventListener('click', () => addProject());
        draft.elements.sector.addEventListener('change', () => {
            for (const item of projects.querySelectorAll('select')) item.dispatchEvent(new Event('change'));
        });
        byId('event-upload').addEventListener('click', event => run(async () => {
            draft.elements.image_url.value = await uploadImage(byId('event-image').files[0]);
            previewImage();
        }, event.currentTarget));
        draft.addEventListener('submit', event => {
            event.preventDefault();
            run(async () => {
                const values = Object.fromEntries(['title', 'summary', 'description', 'rules', 'completion',
                    'reward_description', 'image_url', 'sector'].map(name => [name, draft.elements[name].value]));
                values.base_prices = amounts(draft, 'base-price');
                values.projects = [...projects.children].map(node => ({
                    enterprise_type: node.querySelector('[name="enterprise_type"]').value,
                    name: node.querySelector('[name="name"]').value,
                    stage_images: imageValues(node),
                    adopt_placeholder: node.querySelector('[name="adopt_placeholder"]').checked,
                    requirements: amounts(node, 'requirement'),
                    ...Object.fromEntries(fields.map(field => [field, node.querySelector(`[name="${field}"]`).valueAsNumber])),
                }));
                const result = await request(endpoint, eventId ? 'PATCH' : 'POST', values);
                location.assign(`/admin/events/${result.id}`);
            }, event.submitter);
        });
    }

    for (const button of root.querySelectorAll('[data-event-action]')) {
        button.addEventListener('click', () => {
            if (!window.confirm(`Підтвердити дію «${button.textContent}»?`)) return;
            run(async () => {
                await request(`${endpoint}/${button.dataset.eventAction}`, 'POST', {confirmed: true});
                location.reload();
            }, button);
        });
    }

    if (!rewardForm) return;
    const issue = byId('event-reward-issue');
    const preview = byId('event-reward-preview');
    let plan;
    const addItem = container => container.append(byId('event-reward-item-template').content.cloneNode(true));
    byId('event-add-reward-item').addEventListener('click', () => addItem(byId('event-reward-items')));
    byId('event-add-bonus').addEventListener('click', () => {
        const bonus = byId('event-bonus-template').content.firstElementChild.cloneNode(true);
        bonus.querySelector('[data-remove-bonus]').addEventListener('click', () => bonus.remove());
        bonus.querySelector('[data-add-item]').addEventListener('click', () => addItem(bonus.querySelector('.event-items')));
        byId('event-bonuses').append(bonus);
    });
    function grant(container, items) {
        const itemAmounts = {};
        for (const label of items.children) {
            const key = label.querySelector('select').value;
            if (key) itemAmounts[key] = (itemAmounts[key] || 0) + label.querySelector('input').valueAsNumber;
        }
        return {gold: container.querySelector('[name="gold"]').valueAsNumber,
            resources: amounts(container, 'reward-resource'), items: itemAmounts};
    }
    const hidePreview = () => { plan = null; issue.hidden = true; preview.replaceChildren(); };
    rewardForm.addEventListener('input', hidePreview);
    rewardForm.addEventListener('click', event => {
        if (event.target.type === 'button') hidePreview();
    });
    rewardForm.addEventListener('submit', event => {
        event.preventDefault();
        hidePreview();
        run(async () => {
            const candidate = {multiplier: rewardForm.elements.multiplier.value,
                everyone: grant(rewardForm, byId('event-reward-items')), ranks: {}, individuals: {}};
            candidate.everyone.resources = amounts(rewardForm.querySelector('.event-fields'), 'reward-resource');
            for (const bonus of byId('event-bonuses').children) {
                const scope = bonus.querySelector('select').value;
                const id = bonus.querySelector('[name="recipient"]').valueAsNumber;
                if (candidate[scope][id]) throw new Error('Для кожного місця або гравця вкажи один набір нагород.');
                candidate[scope][id] = grant(bonus, bonus.querySelector('.event-items'));
            }
            const result = await request(`${endpoint}/rewards/preview`, 'POST', candidate);
            const resources = JSON.parse(byId('event-resource-icons').textContent);
            function showReward(container, reward) {
                const quantities = {gold: reward.gold, ...reward.resources};
                for (const [key, value] of Object.entries(quantities)) {
                    if (!value || !resources[key]) continue;
                    const image = document.createElement('img');
                    image.className = 'event-resource-icon';
                    image.src = resources[key].icon;
                    image.alt = image.title = resources[key].name;
                    container.append(image, ` × ${value} `);
                }
                for (const [key, value] of Object.entries(reward.items)) container.append(`Предмет #${key} × ${value} `);
            }
            const table = document.createElement('table');
            const head = table.createTHead().insertRow();
            for (const label of ['Місце', 'Гравець', 'Оцінка внеску', 'Нагорода']) {
                const cell = document.createElement('th');
                cell.textContent = label;
                head.append(cell);
            }
            const body = table.createTBody();
            for (const row of result.participants) {
                const line = body.insertRow();
                for (const value of [row.rank, `${row.name} · ID ${row.player_id}`, row.value]) {
                    line.insertCell().textContent = value;
                }
                showReward(line.insertCell(), row.reward);
            }
            const totals = document.createElement('p');
            totals.textContent = `Коефіцієнт ${result.multiplier} · Разом `;
            showReward(totals, result.totals);
            preview.replaceChildren(totals, table);
            plan = candidate;
            issue.hidden = false;
        }, event.submitter);
    });
    issue.addEventListener('click', () => {
        if (!plan || !window.confirm('Видати нагороди за цим розрахунком?')) return;
        run(async () => {
            await request(`${endpoint}/rewards/issue`, 'POST', {confirmed: true, plan});
            location.reload();
        }, issue);
    });
})();
