(() => {
    const view = document.querySelector('[data-event-live]');
    if (!view) return;
    const sections = ['[data-event-summary]', '[data-event-enterprises]', '[data-event-ranking]'];
    let updating = false;
    const timer = setInterval(async () => {
        if (document.hidden || updating) return;
        updating = true;
        try {
            const response = await fetch(location.href, {cache: 'no-store'});
            if (!response.ok) return;
            const updated = new DOMParser().parseFromString(await response.text(), 'text/html');
            for (const selector of sections) {
                const current = view.querySelector(selector);
                const replacement = updated.querySelector(selector);
                if (current && replacement && !current.contains(document.activeElement)) {
                    current.replaceWith(replacement);
                }
            }
            if (!updated.querySelector('[data-event-live]')) clearInterval(timer);
        } catch { /* An interrupted connection is retried on the next poll. */ }
        finally { updating = false; }
    }, 15000);
})();
