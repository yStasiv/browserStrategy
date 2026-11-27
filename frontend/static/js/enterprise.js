(() => {
function standardPage(panel) {
    let ws = null;

    function connectWebSocket() {
        if (panel.dataset.playerId) {
            const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${scheme}//${window.location.host}/ws/${panel.dataset.playerId}`);

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                if (data.type === "work_finished") {
                    // Показуємо повідомлення про закінчення роботи
                    const notification = document.createElement('div');
                    notification.className = 'enterprise-notification';
                    notification.setAttribute('role', 'status');
                    notification.textContent = `Ви закінчили роботу на підприємстві ${data.enterprise_name}. Зароблено ${data.earned} золота.`;
                    document.body.appendChild(notification);

                    // Оновлюємо сторінку через 3 секунди
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                }
            };

            ws.onclose = function() {
                // Спробуємо переконектитись через 5 секунд
                setTimeout(connectWebSocket, 5000);
            };
        }
    }

    // Підключаємось до WebSocket при завантаженні сторінки
    connectWebSocket();

    const shiftEnd = panel.querySelector('[data-shift-end]');
    if (shiftEnd) {
        const end = Date.parse(shiftEnd.dateTime);
        const serverTime = Date.parse(shiftEnd.dataset.serverTime);
        const pageTime = performance.now();
        const remaining = panel.querySelector('[data-shift-remaining]');
        for (const time of [panel.querySelector('[data-shift-start]'), shiftEnd]) {
            time.textContent = new Date(time.dateTime).toLocaleTimeString('uk-UA', {hour: '2-digit', minute: '2-digit'});
        }
        function updateShiftTimer() {
            const seconds = Math.max(0, Math.ceil((end - serverTime - (performance.now() - pageTime)) / 1000));
            remaining.textContent = seconds
                ? `${Math.floor(seconds / 60)} хв ${seconds % 60} с`
                : 'Зміна завершилась. Оновлення…';
            if (seconds > 0) setTimeout(updateShiftTimer, 1000);
            else window.location.reload();
        }
        updateShiftTimer();
    }

    for (const form of panel.querySelectorAll('[data-quote-form]')) {
        const amount = form.elements.amount;
        const price = BigInt(form.elements.expected_price.value);
        const percent = BigInt(panel.dataset.commission);
        function updateTotal() {
            const count = amount.validity.valid && amount.value ? BigInt(amount.valueAsNumber) : 0n;
            const subtotal = count * price;
            const fee = (subtotal * percent + 99n) / 100n;
            const total = subtotal + fee;
            form.querySelector('[data-fee]').value = fee.toLocaleString('en-US');
            form.querySelector('[data-total]').value = total.toLocaleString('en-US');
            form.elements.expected_total.value = total.toString();
        }
        amount.addEventListener('input', updateTotal);
        updateTotal();
    }

    const workersDialog = panel.querySelector('#enterprise-workers');
    panel.querySelector('[data-show-workers]')?.addEventListener('click', () => workersDialog.showModal());
}

function constructionPage(container, panel) {
    const endpoint = container.dataset.url;
    const feedback = container.querySelector('#construction-feedback');
    const number = new Intl.NumberFormat('uk-UA');
    let state;
    let time;
    let busy = false;
    let polling = false;
    let retry;
    let finished = false;

    function remaining(value, now) {
        const seconds = Math.max(0, Math.ceil((Date.parse(value) - now) / 1000));
        return `${Math.floor(seconds / 3600)} год ${Math.floor(seconds / 60) % 60} хв ${seconds % 60} с`;
    }

    function updateTimer() {
        const progress = container.querySelector('#construction-progress');
        const timing = container.querySelector('#construction-timing');
        timing.hidden = state.paused || !state.started_at;
        const now = Date.parse(state.server_time) + performance.now() - time;
        const fraction = state.paused && state.started_at ? state.construction_progress / 100 : state.started_at
            ? (now - Date.parse(state.started_at)) / (Date.parse(state.completion_at) - Date.parse(state.started_at))
            : state.collection_progress / 100;
        progress.value = Math.max(0, Math.min(100, fraction * 100));
        container.querySelector('#construction-progress-label').textContent =
            `${state.started_at ? 'Будівництво' : 'Збір ресурсів'} · ${progress.value.toFixed(1)}%`;
        if (state.started_at && !state.paused) {
            timing.textContent = `До наступної стадії ${remaining(state.next_stage_at, now)}. До завершення ${remaining(state.completion_at, now)}. Орієнтовна дата: ${new Date(state.completion_at).toLocaleString('uk-UA')}.`;
        }
    }

    function syncRange(form) {
        const {quantity, quantity_range: slider} = form.elements;
        slider.value = String(Math.min(Number(slider.max), Math.max(1, quantity.valueAsNumber || 1)));
    }

    function render(next) {
        state = next;
        time = performance.now();
        container.querySelector('#construction-art').setAttribute('src', state.image_url);
        container.querySelector('#construction-phase').textContent = state.stage_name;
        for (const resource of state.resources) {
            const row = container.querySelector(`[data-resource="${CSS.escape(resource.id)}"]`);
            const form = row.querySelector('form');
            form.hidden = state.paused || !!state.started_at;
            const cap = Math.min(resource.available, resource.remaining);
            row.querySelector('progress').value = resource.collected;
            row.querySelector('[data-amounts]').textContent = `Зібрано ${number.format(resource.collected)} з ${number.format(resource.required)} · бракує ${number.format(resource.remaining)} · у тебе ${number.format(resource.available)} · твій внесок ${number.format(resource.personal)}`;
            form.elements.quantity.max = cap;
            form.elements.quantity_range.max = Math.max(1, cap);
            syncRange(form);
            for (const element of form.elements) element.disabled = busy || cap < 1;
        }
        updateTimer();
    }

    async function refresh() {
        if (busy || polling || finished || document.hidden) return;
        polling = true;
        try {
            const response = await fetch(endpoint, {cache: 'no-store'});
            if (!response.ok || busy) return;
            const next = await response.json();
            if (busy) return;
            render(next);
            if (next.stage !== 'OPERATIONAL') return;
            const page = await fetch(location.href, {headers: {'Accept': 'text/html'}, cache: 'no-store'});
            if (!page.ok) return;
            const result = new DOMParser().parseFromString(await page.text(), 'text/html');
            const replacement = result.querySelector('.enterprise-panel');
            if (!replacement || replacement.querySelector('#construction-panel')) return;
            finished = true;
            clearInterval(poll);
            clearInterval(clock);
            panel.replaceWith(replacement);
            standardPage(replacement);
        } catch { /* The next poll retries. */ }
        finally { polling = false; }
    }

    const confirmation = container.querySelector('#construction-confirm');
    let selection;
    confirmation.addEventListener('close', () => { if (!confirmation.open) selection = null; });
    container.querySelector('#construction-confirm-submit').addEventListener('click', () => {
        if (busy || state.paused || !selection) return;
        const {form, resource, quantity} = selection;
        selection = null;
        confirmation.close();
        return contribute(form, resource, quantity);
    });

    async function contribute(form, resource, quantity) {
        retry ||= {resource, quantity, operation_id: crypto.randomUUID()};
        busy = true;
        render(state);
        try {
            const response = await fetch(`${endpoint}/contribute`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(retry),
            });
            const result = await response.json();
            retry = null;
            if (!response.ok) {
                if (result.construction) state = result.construction;
                feedback.textContent = typeof result.detail === 'string' ? result.detail : 'Перевір кількість ресурсу.';
                return;
            }
            state = result;
            form.reset();
            feedback.textContent = 'Ресурси зараховано.';
            const info = result.resources.find(item => item.id === resource);
            const wallet = document.querySelector(`.player-resources [data-resource-id="${CSS.escape(resource)}"]`);
            if (wallet) {
                for (const node of [...wallet.childNodes]) if (node.nodeType === Node.TEXT_NODE) node.remove();
                wallet.append(document.createTextNode(` ${number.format(info.available)}`));
                wallet.title = `${info.name} · ${info.available}`;
                wallet.setAttribute('aria-label', wallet.title);
            }
        } catch {
            feedback.textContent = 'Відповідь не надійшла. Повторно підтвердь той самий внесок.';
        } finally {
            busy = false;
            render(state);
            refresh();
        }
    }

    for (const row of container.querySelectorAll('[data-resource]')) {
        const form = row.querySelector('form');
        const {quantity, quantity_range: slider} = form.elements;
        quantity.addEventListener('input', () => syncRange(form));
        slider.addEventListener('input', () => { quantity.value = slider.value; });
        form.querySelector('[data-max]').addEventListener('click', () => {
            quantity.value = quantity.max;
            syncRange(form);
        });
        form.addEventListener('submit', event => {
            event.preventDefault();
            if (busy || confirmation.open || !form.reportValidity()) return;
            const resource = row.dataset.resource;
            const quantity = form.elements.quantity.valueAsNumber;
            if (retry && (retry.resource !== resource || retry.quantity !== quantity)) {
                feedback.textContent = 'Ще раз підтвердь попередній внесок, щоб перевірити його стан.';
                return;
            }
            const info = state.resources.find(item => item.id === resource);
            const icon = container.querySelector('#construction-confirm-icon');
            icon.src = info.icon;
            icon.alt = info.name;
            container.querySelector('#construction-confirm-amount').textContent = number.format(quantity);
            selection = {form, resource, quantity};
            confirmation.showModal();
        });
    }
    render(JSON.parse(container.querySelector('#construction-state').textContent));
    const poll = setInterval(refresh, 5000);
    const clock = setInterval(updateTimer, 1000);
}

const panel = document.querySelector('.enterprise-panel');
const construction = panel?.querySelector('#construction-panel');
if (construction) constructionPage(construction, panel);
else if (panel) standardPage(panel);
})();
