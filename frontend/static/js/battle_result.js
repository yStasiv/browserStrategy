/* The server supplies all participants, outcomes and reward amounts. */
const BattleResult = (() => {
    const numberFormat = new Intl.NumberFormat('en-US', {maximumFractionDigits: 20});
    const trim = value => typeof value === 'string' ? value.trim() : '';

    function formatRewards(entries = []) {
        if (!Array.isArray(entries)) return [];
        return entries.flatMap(entry => {
            if (!entry) return [];
            const label = trim(entry.label);
            const raw = entry.amount ?? entry.value;
            const value = typeof raw === 'number'
                ? (Number.isFinite(raw) && raw !== 0 ? numberFormat.format(raw) : '')
                : trim(raw);
            if (!label || !value) return [];
            const icon = trim(entry.icon);
            return [{
                label, value, unit: trim(entry.unit), description: trim(entry.description),
                icon: icon.startsWith('/static/') ? icon : '',
                order: Number.isFinite(entry.order) ? entry.order : 1000,
            }];
        }).sort((a, b) => a.order - b.order);
    }

    function sections(result) {
        const sides = Array.isArray(result.sides) ? result.sides : [];
        const winner = result.winner_side;
        return [...sides].sort((a, b) => Number(b.side === winner) - Number(a.side === winner)).map(side => ({
            side: side.side,
            heading: winner == null
                ? `Нічия · Сторона ${side.side + 1}`
                : (side.side === winner ? 'Переможна сторона' : 'Сторона, що програла'),
            participants: (side.participants || []).map(participant => ({
                name: trim(participant.name) || 'Учасник',
                rewards: formatRewards(participant.rewards),
            })),
        }));
    }

    function render(container, result, damage, mySide, unitName) {
        const doc = container.ownerDocument;
        function element(tag, className, text) {
            const node = doc.createElement(tag);
            if (className) node.className = className;
            if (text) node.textContent = text;
            return node;
        }

        const groups = sections(result).map(side => {
            const section = element('section', 'battle-result-side');
            section.dataset.side = side.side;
            section.append(element('h3', '', side.heading + ':'));
            for (const participant of side.participants) {
                const row = element('div', 'battle-result-participant');
                row.append(element('p', 'battle-result-name', participant.name));
                if (participant.rewards.length) {
                    const rewards = element('ul', 'battle-result-rewards');
                    for (const reward of participant.rewards) {
                        const item = element('li');
                        if (reward.icon) {
                            const image = element('img');
                            image.src = reward.icon;
                            image.alt = '';
                            item.append(image);
                        }
                        const amount = [reward.value, reward.unit].filter(Boolean).join(' ');
                        item.append(doc.createTextNode(reward.label + ' · ' + amount));
                        if (reward.description) {
                            item.append(element('span', 'battle-result-reward-note', ' — ' + reward.description));
                        }
                        rewards.append(item);
                    }
                    row.append(rewards);
                }
                section.append(row);
            }
            return section;
        });
        if (damage?.sides?.length) {
            const section = element('section', 'battle-result-damage');
            section.append(element('h3', '', 'Завдана шкода'));
            const columns = element('div', 'battle-result-damage-columns');
            const sides = [...damage.sides].sort((a, b) => Number(b.side === mySide) - Number(a.side === mySide));
            for (const side of sides) {
                const column = element('div', 'battle-result-damage-team');
                const heading = side.side === mySide ? 'Союзники' : 'Вороги';
                const total = side.total + (side.hero_total ?? 0);
                column.append(element('h4', '', heading + ' · ' + numberFormat.format(total)));
                if (side.creatures?.length || Number.isFinite(side.hero_total)) {
                    const list = element('ul');
                    if (Number.isFinite(side.hero_total)) {
                        const row = element('li');
                        row.append(element('span', '', 'Герой'),
                            element('strong', '', numberFormat.format(side.hero_total)));
                        list.append(row);
                    }
                    for (const creature of side.creatures ?? []) {
                        const row = element('li');
                        row.append(element('span', '', unitName(creature.unit)),
                            element('strong', '', numberFormat.format(creature.amount)));
                        list.append(row);
                    }
                    column.append(list);
                }
                columns.append(column);
            }
            section.append(columns);
            if (damage.partial) {
                section.append(element('p', 'battle-result-damage-note', 'Показано шкоду за доступну частину запису.'));
            }
            groups.push(section);
        }
        container.replaceChildren(...groups);
    }

    function create(dialog, {storage, onReplay, onContinue, fallbackFocus, unitName = key => key}) {
        const content = dialog.querySelector('[data-result-content]');
        const replayButton = dialog.querySelector('[data-result-replay]');
        const feedback = dialog.querySelector('[data-result-feedback]');
        const shown = new Set();
        let current;
        let previousFocus;

        function close() {
            if (dialog.open) dialog.close();
        }
        function hasShown(id) {
            if (shown.has(id)) return true;
            try { return storage?.getItem('battle-result:' + id) === '1'; } catch { return false; }
        }
        function present(id, result, damage, mySide, {fromReplay = false} = {}) {
            if (!result || result.status !== 'finished' || String(id) !== String(result.battle_id)) return false;
            const key = String(id);
            if (!fromReplay && hasShown(key)) return false;
            close();
            current = result;
            render(content, result, damage, mySide, unitName);
            replayButton.disabled = result.replay_available !== true;
            feedback.hidden = !replayButton.disabled;
            feedback.textContent = replayButton.disabled ? 'Запис повтору недоступний.' : '';
            previousFocus = dialog.ownerDocument.activeElement;
            dialog.showModal();
            dialog.querySelector('#result-title').focus();
            shown.add(key);
            try { storage?.setItem('battle-result:' + key, '1'); } catch { /* storage is optional */ }
            return true;
        }

        dialog.addEventListener('close', () => {
            const doc = dialog.ownerDocument;
            if (dialog.open || doc.activeElement !== doc.body && !dialog.contains(doc.activeElement)) return;
            const target = previousFocus?.isConnected && !previousFocus.disabled && previousFocus !== doc.body
                ? previousFocus : fallbackFocus();
            target?.focus();
        });
        dialog.querySelector('[data-result-continue]').addEventListener('click', () => {
            if (!dialog.open) return;
            const result = current;
            close();
            if (result) onContinue(result.battle_id);
        });
        replayButton.addEventListener('click', async () => {
            if (!dialog.open || !current?.replay_available || replayButton.disabled) return;
            const result = current;
            replayButton.disabled = true;
            try {
                if (await onReplay(result.battle_id)) {
                    if (current === result) close();
                    return;
                }
            } catch { /* the result stays open for another attempt */ }
            if (current !== result || !dialog.open) return;
            replayButton.disabled = false;
            feedback.hidden = false;
            feedback.textContent = 'Не вдалося відкрити повтор.';
        });
        return {present, close};
    }

    return {create, formatRewards, sections};
})();
