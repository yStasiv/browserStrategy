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
document.querySelector('.castle-dialog[data-open-on-load]')?.showModal();

function showFocusedUnit(event) {
    const card = event.target.closest('[data-army-unit]');
    if (!card) return;
    for (const item of unitCards) item.toggleAttribute('data-unit-active', item === card);
    for (const preview of unitPreviews) preview.hidden = preview.dataset.unitPreview !== card.dataset.armyUnit;
}

function updateArmy() {
    let stacks = retainedSquads;
    for (const slider of sliders) {
        slider.parentElement.querySelector('output').value = slider.value;
        if (slider.valueAsNumber > 0) stacks++;
    }
    armyForm.querySelector('button[type="submit"]').disabled = sliders.length === 0 || stacks === 0 || stacks > limit;
}

armyForm.addEventListener('input', updateArmy);
armyForm.addEventListener('focusin', showFocusedUnit);
armyForm.addEventListener('click', showFocusedUnit);
window.addEventListener('pageshow', updateArmy);
updateArmy();
