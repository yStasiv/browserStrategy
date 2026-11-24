(() => {
    const summary = document.querySelector('#guild-summary');
    const feedback = document.querySelector('#guild-feedback');
    const retry = document.querySelector('#guild-retry');
    const cards = document.querySelector('#guild-quests');
    const template = document.querySelector('#guild-quest-card');
    const statuses = {
        available: 'Доступний',
        in_progress: 'У процесі',
        completed: 'Виконано',
    };
    const resources = [
        ['gold', 'золота', 'gold-resource-icon.png'],
        ['singing_resin', 'співочої смоли', 'resources/01_singing_resin.png'],
        ['basalt_bone', 'базальтової кістки', 'resources/02_basalt_bone.png'],
        ['xp', 'XP гільдії'],
    ];

    function render(board) {
        document.querySelector('#guild-rank').textContent = `${board.rank} · рівень ${board.level}`;
        const xpLabel = board.xp > board.next_xp
            ? `${board.next_xp} +-${board.xp - board.next_xp}`
            : `${board.xp} / ${board.next_xp}`;
        document.querySelector('#guild-xp-label').textContent = `Досвід гільдії · ${xpLabel} XP`;
        const xp = document.querySelector('#guild-xp');
        xp.max = board.next_xp;
        xp.value = board.xp;
        document.querySelector('#guild-replacements').textContent =
            `Заміни сьогодні · ${board.replacements_remaining}/${board.replacement_limit} · скидання о 00:00 UTC`;
        summary.hidden = false;

        const nodes = board.quests.map(quest => {
            const node = template.content.firstElementChild.cloneNode(true);
            const completed = quest.status === 'completed';
            node.classList.toggle('is-completed', completed);
            node.querySelector('h2').textContent = quest.title;
            node.querySelector('.guild-card-meta').textContent = `${quest.difficulty} · ${statuses[quest.status]}`;
            node.querySelector('.guild-objective').textContent = `${quest.description} ${quest.progress}/${quest.required}`;
            const progress = node.querySelector('progress');
            progress.max = quest.required;
            progress.value = quest.progress;
            progress.setAttribute('aria-label', `Прогрес квесту «${quest.title}»`);
            const rewards = node.querySelector('.guild-rewards');
            for (const [key, label, icon] of resources) {
                if (!quest[key]) continue;
                const reward = document.createElement('li');
                if (icon) {
                    const image = document.createElement('img');
                    image.src = `/static/images/${icon}`;
                    image.alt = '';
                    reward.append(image);
                }
                reward.append(`${quest[key]} ${label}`);
                rewards.append(reward);
            }
            const button = node.querySelector('button');
            button.textContent = completed ? 'Отримати нагороду' : 'Замінити квест';
            button.disabled = !completed && board.replacements_remaining === 0;
            button.addEventListener('click', () => changeQuest(quest, completed));
            return node;
        });
        cards.replaceChildren(...nodes);
    }

    async function request(path, options) {
        const response = await fetch(`/api/guild${path}`, options);
        if (response.ok) return response.json();
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' ? error.detail : 'Не вдалося оновити дошку.');
    }

    async function loadBoard() {
        retry.hidden = true;
        feedback.textContent = 'Завантаження квестів…';
        try {
            const current = await request('');
            render(current.initialized ? current : await request('/initialize', {method: 'POST'}));
            feedback.textContent = '';
        } catch (error) {
            feedback.textContent = error.message;
            retry.hidden = false;
        }
    }

    async function changeQuest(quest, completed) {
        if (!completed && quest.progress > 0 && !window.confirm('Замінити квест? Поточний прогрес буде втрачено.')) return;
        const buttons = [...cards.querySelectorAll('button:not(:disabled)')];
        buttons.forEach(button => { button.disabled = true; });
        retry.hidden = true;
        try {
            const action = completed ? 'claim' : 'replace';
            const options = {method: 'POST'};
            if (!completed) {
                options.headers = {'Content-Type': 'application/json'};
                options.body = JSON.stringify({confirm_progress_loss: quest.progress > 0});
            }
            render(await request(`/quests/${quest.id}/${action}`, options));
            cards.querySelectorAll('article')[quest.slot - 1].querySelector('button').focus();
            feedback.textContent = completed ? 'Нагороду отримано.' : 'Квест замінено.';
        } catch (error) {
            feedback.textContent = error.message;
            retry.hidden = false;
        } finally {
            buttons.forEach(button => { button.disabled = false; });
        }
    }

    retry.addEventListener('click', loadBoard);
    loadBoard();
})();
