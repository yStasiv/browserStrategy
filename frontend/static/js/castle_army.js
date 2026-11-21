const armyForm = document.querySelector('#choose-units-form');
const sliders = [...armyForm.querySelectorAll('input[type="range"]')];
const limit = Number(armyForm.dataset.slotLimit);
const summary = document.querySelector('#army-count');

function updateArmy() {
    let stacks = 0;
    for (const slider of sliders) {
        slider.parentElement.querySelector('output').value = slider.value;
        if (slider.valueAsNumber > 0) stacks++;
    }
    summary.textContent = `${stacks} / ${limit} загонів`;
    armyForm.querySelector('button[type="submit"]').disabled = stacks === 0 || stacks > limit;
}

armyForm.addEventListener('input', updateArmy);
window.addEventListener('pageshow', updateArmy);
updateArmy();
