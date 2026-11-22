const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const context = vm.createContext({});
vm.runInContext(readFileSync(resolve(__dirname, '../frontend/static/js/battle_result.js'), 'utf8') +
    '\nthis.result = BattleResult;', context);
const BattleResult = context.result;
const plain = value => JSON.parse(JSON.stringify(value));

function result(id = 12, winner = 1, replay = true) {
    return {
        battle_id: id,
        status: 'finished',
        replay_available: replay,
        winner_side: winner,
        sides: [
            {side: 0, participants: [{name: 'Ада'}]},
            {side: 1, participants: [{name: 'Міра', rewards: [{label: 'Досвід героя', amount: 12345}]}, {name: 'Лада'}]},
        ],
    };
}

test('formats optional values, keeps unknown labeled types and sorts rewards', () => {
    const values = plain(BattleResult.formatRewards([
        null, {label: '', amount: 2}, {label: 'Пропуск', value: null}, {label: 'Порожньо', amount: 0},
        {type: 'achievement', label: 'Досягнення', value: 'Перший бій', description: 'Колекція'},
        {type: 'gold', label: 'Золото', amount: 12345, order: 10, unit: 'монет', icon: '/static/gold.png'},
    ]));
    assert.deepEqual(values.map(({label, value}) => [label, value]), [
        ['Золото', '12,345'], ['Досягнення', 'Перший бій'],
    ]);
    assert.equal(values[0].unit, 'монет');
    assert.equal(values[0].icon, '/static/gold.png');
    assert.equal(values[1].description, 'Колекція');
});

test('groups multiple participants, keeps side identity and supports draws', () => {
    const sides = plain(BattleResult.sections(result()));
    assert.deepEqual(sides.map(side => side.side), [1, 0]);
    assert.deepEqual(sides[0].participants.map(participant => participant.name), ['Міра', 'Лада']);
    assert.equal(sides[1].heading, 'Сторона, що програла');
    assert.deepEqual(plain(BattleResult.sections(result(12, null))).map(side => side.heading), [
        'Нічия · Сторона 1', 'Нічия · Сторона 2',
    ]);
});

function fixture(storage, unitName) {
    const doc = {
        createElement(tag) { return makeNode(tag); },
        createTextNode(textContent) { return {textContent}; },
    };
    function makeNode(tag) {
        return {
            tag,
            dataset: {},
            children: [],
            handlers: {},
            ownerDocument: doc,
            isConnected: true,
            append(...children) { this.children.push(...children); },
            replaceChildren(...children) { this.children = children; },
            addEventListener(name, handler) { this.handlers[name] = handler; },
            focus() { doc.activeElement = this; },
        };
    }
    doc.body = makeNode('body');
    doc.activeElement = doc.body;
    const nodes = {
        '[data-result-content]': makeNode('div'),
        '[data-result-replay]': makeNode('button'),
        '[data-result-continue]': makeNode('button'),
        '[data-result-feedback]': makeNode('p'),
        '#result-title': makeNode('h2'),
    };
    const dialog = makeNode('dialog');
    const focus = makeNode('a');
    Object.assign(dialog, {
        openings: 0,
        querySelector(selector) { return nodes[selector]; },
        contains(node) { return Object.values(nodes).includes(node); },
        showModal() { this.open = true; this.openings++; },
        close() { this.open = false; this.handlers.close(); },
    });
    const watched = [];
    const continued = [];
    const controller = BattleResult.create(dialog, {
        storage, unitName, fallbackFocus: () => focus,
        onReplay: id => { watched.push(id); return true; },
        onContinue: id => continued.push(id),
    });
    return {dialog, controller, watched, continued, nodes, focus, doc};
}

test('opens once per confirmed battle, ignores stale results and restores focus', () => {
    const values = new Map();
    const storage = {getItem: key => values.get(key), setItem: (key, value) => values.set(key, value)};
    const {dialog, controller, nodes, focus, doc} = fixture(storage);
    assert.equal(controller.present(99, result()), false);
    assert.equal(controller.present(12, {...result(), status: 'active'}), false);
    assert.equal(controller.present(12, result()), true);
    assert.equal(doc.activeElement, nodes['#result-title']);
    controller.close();
    assert.equal(doc.activeElement, focus);
    assert.equal(controller.present(12, result()), false);
    assert.equal(dialog.openings, 1);
    assert.equal(fixture(storage).controller.present(12, result()), false);
});

test('replays the presented battle and continues independently', async () => {
    const {dialog, controller, nodes, watched, continued} = fixture();
    controller.present(12, result());
    await nodes['[data-result-replay]'].handlers.click();
    assert.deepEqual(watched, [12]);
    assert.equal(dialog.open, false);
    assert.deepEqual(continued, []);
    controller.present(13, result(13, 0, false));
    assert.equal(nodes['[data-result-replay]'].disabled, true);
    assert.equal(nodes['[data-result-feedback]'].hidden, false);
    await nodes['[data-result-replay]'].handlers.click();
    assert.deepEqual(watched, [12]);
    nodes['[data-result-continue]'].handlers.click();
    assert.deepEqual(continued, [13]);
    assert.equal(dialog.open, false);
});

test('can present the same battle again after each replay completion', () => {
    const {dialog, controller} = fixture();
    controller.present(12, result());
    controller.close();
    for (const _ of [1, 2]) {
        assert.equal(controller.present(12, result(), undefined, 0, {fromReplay: true}), true);
        controller.close();
    }
    assert.equal(controller.present(12, result()), false);
    assert.equal(dialog.openings, 3);
});

test('shows a separate damage section with allies first regardless of the winner', () => {
    const {controller, nodes} = fixture(undefined, () => 'Лучник');
    controller.present(12, result(), {
        partial: true, sides: [
            {side: 1, total: 12345, creatures: [{unit: 'archer', amount: 12345}]},
            {side: 0, total: 0, creatures: []},
        ],
    }, 0);
    const damage = nodes['[data-result-content]'].children.at(-1);
    assert.equal(damage.className, 'battle-result-damage');
    const [title, columns, note] = damage.children;
    assert.equal(title.textContent, 'Шкода створінь');
    assert.equal(columns.children[0].children[0].textContent, 'Союзники · 0');
    assert.equal(columns.children[1].children[0].textContent, 'Вороги · 12,345');
    assert.deepEqual(columns.children[1].children[1].children[0].children.map(node => node.textContent),
        ['Лучник', '12,345']);
    assert.equal(note.textContent, 'Показано шкоду за доступну частину запису.');
});
