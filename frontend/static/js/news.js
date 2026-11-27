(() => {
    const byId = id => document.getElementById(id);
    const input = byId('news-image-input');
    if (input) {
        const preview = byId('news-image-preview');
        const existing = preview.getAttribute('src');
        let objectUrl;
        input.addEventListener('change', () => {
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            objectUrl = input.files[0] ? URL.createObjectURL(input.files[0]) : null;
            const url = objectUrl || existing;
            if (url) preview.src = url;
            else preview.removeAttribute('src');
            preview.hidden = !url;
        });
    }

    const insertLink = byId('news-insert-link');
    if (insertLink) {
        insertLink.addEventListener('click', () => {
            const text = byId('news-editor-text');
            const message = byId('news-link-error');
            const {selectionStart: start, selectionEnd: end} = text;
            const url = window.prompt('Адреса посилання (HTTP або HTTPS)');
            if (url === null) return;
            try {
                const parsed = new URL(url);
                if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error();
                const href = parsed.href.replaceAll('(', '%28').replaceAll(')', '%29');
                if (href.length > 2048) throw new Error();
                const label = text.value.slice(start, end).trim().replace(/[\[\]\r\n]/g, ' ') || href;
                text.setRangeText(`[${label}](${href})`, start, end, 'end');
                text.focus();
                message.textContent = '';
            } catch {
                message.textContent = 'Вкажи повну адресу HTTP або HTTPS.';
            }
        });
    }

    const dialog = byId('news-popup');
    if (!dialog || !document.querySelector('.main-nav')) return;
    const button = byId('news-acknowledge');
    const feedback = byId('news-popup-feedback');

    let checking = false;
    let acknowledge;
    async function showLatest() {
        if (checking || dialog.open || button.disabled || document.hidden) return;
        checking = true;
        try { await checkLatest(); }
        finally { checking = false; }
    }

    async function checkLatest() {
        const response = await fetch('/api/news/latest', {cache: 'no-store'});
        if (!response.ok) return;
        const {news} = await response.json();
        if (!news) return;
        byId('news-popup-title').textContent = news.title;
        byId('news-popup-date').textContent = news.published_at;
        const text = byId('news-popup-text');
        if (news.text_parts) {
            text.replaceChildren(...news.text_parts.map(part => {
                if (!part.url) return document.createTextNode(part.text);
                const anchor = document.createElement('a');
                anchor.href = part.url;
                anchor.target = '_blank';
                anchor.rel = 'noopener noreferrer';
                anchor.textContent = part.text;
                return anchor;
            }));
        } else {
            text.textContent = news.text;
        }
        const image = byId('news-popup-image');
        if (news.image_url) image.src = news.image_url;
        image.hidden = !news.image_url;
        const link = byId('news-popup-link');
        if (news.link_url) link.href = news.link_url;
        link.hidden = !news.link_url;
        const eventLink = byId('news-popup-event-link');
        if (news.event_id) {
            dialog.classList.add('news-popup-event');
            eventLink.href = `/events/${news.event_id}`;
            eventLink.hidden = false;
            button.textContent = 'Закрити';
        } else {
            if (dialog.classList) dialog.classList.remove('news-popup-event');
            if (eventLink) eventLink.hidden = true;
            button.textContent = 'Ознайомився';
        }
        feedback.textContent = '';
        if (acknowledge && button.removeEventListener) button.removeEventListener('click', acknowledge);
        acknowledge = async () => {
            button.disabled = true;
            dialog.close();
            try {
                const result = await fetch(`/api/news/${news.id}/acknowledge`, {method: 'POST', keepalive: true});
                if (!result.ok && result.status !== 404) throw new Error();
            } catch {
                feedback.textContent = 'Не вдалося зберегти підтвердження. Спробуй ще раз.';
                dialog.showModal();
            } finally {
                button.disabled = false;
            }
        };
        button.addEventListener('click', acknowledge);
        dialog.showModal();
    }

    dialog.addEventListener('cancel', event => event.preventDefault());
    const poll = () => showLatest().catch(() => {});
    poll();
    if (typeof window !== 'undefined') window.setInterval(poll, 30000);
})();
