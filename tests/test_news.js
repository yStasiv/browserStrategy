const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

for (const eventId of [null, 3]) {
test(eventId ? 'event notice opens in a sized dialog and waits for its explicit dismissal' :
    'latest unread news opens on load and closes immediately on acknowledgment', async () => {
    const nodes = new Map();
    function byId(id) {
        if (id === 'news-image-input') return null;
        if (!nodes.has(id)) nodes.set(id, {
            open: false, handlers: {},
            classList: new Set(),
            addEventListener(event, fn) { this.handlers[event] = fn; },
            showModal() { this.open = true; }, close() { this.open = false; },
            replaceChildren(...children) { this.children = children; },
        });
        nodes.get(id).classList.remove = name => nodes.get(id).classList.delete(name);
        return nodes.get(id);
    }
    const calls = [];
    let finish;
    const context = vm.createContext({
        document: {
            getElementById: byId, querySelector: () => ({}),
            createTextNode: textContent => ({textContent}),
            createElement: tagName => ({tagName}),
        },
        fetch: (url, options) => {
            calls.push([url, options]);
            if (url === '/api/news/latest') return Promise.resolve({ok: true, json: async () => ({news: {
                id: 7, event_id: eventId, title: 'Оновлення', text: '<strong>Текст</strong>', published_at: '27.11.2026 12:00',
                image_url: '/static/images/news/example.png', link_url: 'https://example.com/news',
                text_parts: [{text: '<strong>Текст</strong>'}, {text: 'Правила', url: 'https://example.com/rules'}],
            }})});
            return new Promise(resolve => { finish = resolve; });
        },
    });
    vm.runInContext(fs.readFileSync('frontend/static/js/news.js', 'utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(byId('news-popup').open, true);
    assert.equal(byId('news-popup').classList.has('news-popup-event'), Boolean(eventId));
    assert.equal(byId('news-acknowledge').textContent, eventId ? 'Закрити' : 'Ознайомився');
    if (eventId) {
        const stylesheet = fs.readFileSync('frontend/static/css/news.css', 'utf8');
        assert.match(stylesheet, /\.news-popup\.news-popup-event\s*\{[^}]*width: min\(54rem,[^}]*max-height: min\(82dvh,/);
        assert.equal(byId('news-popup-event-link').href, '/events/3');
        let prevented = false;
        byId('news-popup').handlers.cancel({preventDefault() { prevented = true; }});
        assert.equal(prevented, true);
        assert.equal(byId('news-popup').open, true);
        assert.equal(calls.length, 1);
    }
    const [text, link] = byId('news-popup-text').children;
    assert.equal(text.textContent, '<strong>Текст</strong>');
    assert.equal(link.tagName, 'a');
    assert.equal(link.textContent, 'Правила');
    assert.equal(link.href, 'https://example.com/rules');
    assert.equal(byId('news-popup-image').src, '/static/images/news/example.png');
    const acknowledgment = byId('news-acknowledge').handlers.click();
    assert.equal(byId('news-popup').open, false);
    assert.equal(calls[1][0], '/api/news/7/acknowledge');
    assert.equal(calls[1][1].method, 'POST');
    finish({ok: true});
    await acknowledgment;
    assert.equal(byId('news-popup').open, false);
});
}
