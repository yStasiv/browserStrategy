"""Experience awarded for fighting an opposing army."""
from .squad_effects import total_hp


def army_hp(state, side):
    return sum(total_hp(stack) for stack in state.stacks.values()
               if stack.owner == side and not stack.summoned)


def earned_experience(initial, final, side):
    if final.surrendered == side:
        return 0
    opposing_hp = army_hp(initial, 1 - side)
    if opposing_hp == 0:
        return 0
    starting_hp = max(1, army_hp(initial, side))
    remaining_hp = min(starting_hp, army_hp(final, side))
    outcome_percent = 100 if final.winner == side else 60 if final.winner is None else 25
    # One XP per four enemy HP, scaled by survival (50–100%) and the outcome.
    return max(1, opposing_hp * (starting_hp + remaining_hp) * outcome_percent // (800 * starting_hp))
