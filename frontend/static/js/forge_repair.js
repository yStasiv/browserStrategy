(() => {
    const result = document.getElementById('forge-repair-result');
    if (result) {
        const form = result.querySelector('form');
        form.addEventListener('submit', () => result.close(), { once: true });
        result.addEventListener('cancel', event => {
            event.preventDefault();
            form.requestSubmit();
        });
        result.showModal();
    }

    const timer = document.getElementById('forge-repair-timer');
    if (!timer) return;
    const claim = document.getElementById('forge-repair-claim');
    const deadline = performance.now() + Number(timer.dataset.seconds) * 1000;
    function tick() {
        const remaining = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
        timer.textContent = remaining ? `Залишилось ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}` : 'Результат готовий';
        claim.disabled = remaining > 0;
        if (remaining) setTimeout(tick, 250);
    }
    tick();
})();
