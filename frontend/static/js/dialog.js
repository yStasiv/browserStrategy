for (const dialog of document.querySelectorAll('dialog')) {
    function isBackdrop(event) {
        const {left, right, top, bottom} = dialog.getBoundingClientRect();
        return event.target === dialog && (
            event.clientX < left || event.clientX > right ||
            event.clientY < top || event.clientY > bottom
        );
    }

    let startedOnBackdrop = false;
    dialog.addEventListener('pointerdown', (event) => {
        startedOnBackdrop = isBackdrop(event);
    });
    dialog.addEventListener('click', (event) => {
        if (startedOnBackdrop && isBackdrop(event)) dialog.close();
        startedOnBackdrop = false;
    });
}
