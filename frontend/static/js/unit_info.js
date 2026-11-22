for (const link of document.querySelectorAll('[data-unit-dialog]')) {
    const dialog = document.getElementById(link.dataset.unitDialog);
    if (!dialog || typeof dialog.showModal !== 'function') continue;

    link.addEventListener('click', (event) => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        dialog.showModal();
    });
}
