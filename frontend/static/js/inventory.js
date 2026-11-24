(() => {
    const tooltip = document.getElementById('inventory-tooltip');
    const feedback = document.getElementById('inventory-feedback');
    let pending = false;
    let tooltipTrigger;

    function showTooltip(trigger) {
        const template = trigger.form.querySelector('[data-artifact-tooltip]');
        tooltip.replaceChildren(template.content.cloneNode(true));
        tooltip.hidden = false;
        tooltipTrigger?.removeAttribute('aria-describedby');
        trigger.setAttribute('aria-describedby', tooltip.id);
        tooltipTrigger = trigger;
        const box = trigger.getBoundingClientRect();
        const left = Math.max(8, Math.min(box.left, window.innerWidth - tooltip.offsetWidth - 8));
        const top = box.bottom + tooltip.offsetHeight + 8 <= window.innerHeight
            ? box.bottom + 4 : Math.max(8, box.top - tooltip.offsetHeight - 4);
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    function hideTooltip(trigger) {
        if (tooltipTrigger !== trigger) return;
        tooltip.hidden = true;
        trigger.removeAttribute('aria-describedby');
        tooltipTrigger = undefined;
    }

    for (const trigger of document.querySelectorAll('[data-artifact-trigger]')) {
        trigger.addEventListener('mouseenter', () => showTooltip(trigger));
        trigger.addEventListener('mouseleave', () => {
            if (document.activeElement !== trigger) hideTooltip(trigger);
        });
        trigger.addEventListener('focus', () => showTooltip(trigger));
        trigger.addEventListener('blur', () => {
            trigger.classList.remove('inventory-level-locked');
            if (!trigger.matches(':hover')) hideTooltip(trigger);
        });
        trigger.addEventListener('keydown', event => {
            if (event.key === 'Escape') hideTooltip(trigger);
        });
    }

    for (const form of document.querySelectorAll('[data-inventory-action]')) {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (pending) return;
            const trigger = event.submitter;
            if (!trigger) return;
            trigger.focus();
            feedback.hidden = true;
            pending = true;
            try {
                const data = new URLSearchParams(new FormData(form));
                data.delete('return_to_inventory');
                const response = await fetch(form.action, {method: 'POST', body: data.toString() ? data : null});
                if (response.ok) {
                    window.location.reload();
                    return;
                }
                const {detail} = await response.json();
                feedback.textContent = detail?.message || (typeof detail === 'string' ? detail : 'Не вдалося змінити спорядження.');
                if (detail?.code === 'artifact_level' && document.activeElement === trigger) {
                    trigger.classList.add('inventory-level-locked');
                }
            } catch {
                feedback.textContent = 'Не вдалося змінити спорядження.';
            }
            feedback.hidden = false;
            pending = false;
        });
    }
})();
