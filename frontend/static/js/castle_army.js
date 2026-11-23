const armyForm = document.querySelector('#choose-units-form');
const sliders = [...armyForm.querySelectorAll('input[type="range"]')];
const limit = Number(armyForm.dataset.slotLimit);
const retainedSquads = Number(armyForm.dataset.retainedSquads);
const unitCards = [...armyForm.querySelectorAll('[data-army-unit]')];
const unitPreviews = [...document.querySelectorAll('[data-unit-preview]')];

for (const trigger of document.querySelectorAll('[data-castle-dialog]')) {
    trigger.addEventListener('click', () => {
        document.getElementById(trigger.dataset.castleDialog).showModal();
    });
}
function showUnit(card, form = card.querySelector('[data-army-form]:checked')) {
    const key = form?.value ?? card.dataset.armyUnit;
    if (form) {
        for (const portrait of card.querySelectorAll('[data-army-portrait]')) {
            portrait.hidden = portrait.dataset.armyPortrait !== key;
        }
        card.querySelector('[data-army-name]').textContent = form.dataset.name;
    }
    for (const item of unitCards) item.toggleAttribute('data-unit-active', item === card);
    for (const preview of unitPreviews) preview.hidden = preview.dataset.unitPreview !== key;
}

function showFocusedUnit(event) {
    const card = event.target.closest('[data-army-unit]');
    if (card) showUnit(card);
}

function updateArmy() {
    let stacks = retainedSquads;
    for (const slider of sliders) {
        slider.parentElement.querySelector('output').value = slider.value;
        if (slider.valueAsNumber > 0 && !slider.closest('[data-replaces-retained]')) stacks++;
    }
    armyForm.querySelector('button[type="submit"]').disabled = sliders.length === 0 || stacks === 0 || stacks > limit;
}

armyForm.addEventListener('input', updateArmy);
armyForm.addEventListener('focusin', showFocusedUnit);
armyForm.addEventListener('click', showFocusedUnit);
for (const card of unitCards) {
    for (const form of card.querySelectorAll('[data-army-form]')) {
        form.addEventListener('change', () => {
            if (form.checked) showUnit(card, form);
        });
    }
}
window.addEventListener('pageshow', () => {
    const active = armyForm.querySelector('[data-unit-active]');
    if (active) showUnit(active);
    updateArmy();
});
document.querySelector('.castle-dialog[data-open-on-load]')?.showModal();
updateArmy();
