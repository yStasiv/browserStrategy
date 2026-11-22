import pytest

from engine import (Attack, BattleState, Defend, IllegalAction, Move, Wait,
                    apply, create_battle, forecast, reachable, run_ai, turn_info)
from engine.data import UNITS
from engine.rules import _hurt, cheb, expected_damage
from engine.state import Stack


def two_stacks(unit_a="swordsman", unit_b="swordsman", ca=5, cb=5, seed=1):
    return create_battle([(unit_a, ca)], [(unit_b, cb)], seed)


def put_adjacent(st):
    a, b = st.stacks["s0_0"], st.stacks["s1_0"]
    a.x, a.y, b.x, b.y = 5, 2, 6, 2
    return a, b


def test_height_adapts_to_army_size():
    small = create_battle([("peasant", 5)], [("goblin", 5)], 1, level=4, mode="pve")
    assert (small.width, small.height) == (12, 5)
    army = [("peasant", 1)] * 7
    big = create_battle(army, [("goblin", 1)], 1, level=4, mode="pve")
    assert big.height == 7
    assert len({(s.x, s.y) for s in big.stacks.values()}) == len(big.stacks)


def test_queue_sorted_by_initiative():
    st = create_battle([("knight", 1), ("archer", 1)], [("goblin", 1), ("swordsman", 1)], 1)
    inits = [UNITS[st.stacks[item["id"]].unit].initiative for item in forecast(st, len(st.stacks))]
    assert inits == sorted(inits, reverse=True)


def test_hurt_kills_whole_creatures():
    s = Stack("x", "swordsman", 0, count=5, top_hp=35, x=0, y=0)  # hp 35 на істоту
    assert _hurt(s, 40) == 1 and (s.count, s.top_hp) == (4, 30)
    assert _hurt(s, 1000) == 4 and s.count == 0


def test_move_blocked_cells_and_range():
    st = two_stacks()
    a = st.active()
    reach = reachable(st, a)
    assert all(cheb(a.x, a.y, x, y) <= 4 for x, y in reach)
    with pytest.raises(IllegalAction):
        apply(st, Move(a.x + 9, a.y))


def test_retaliation_is_restored_at_the_next_own_turn():
    st = two_stacks()
    _, target = put_adjacent(st)
    target.ready += 50_000
    st, first = apply(st, Attack(target.id))
    assert [event["type"] for event in first] == ["attack", "retaliation"]
    assert st.stacks[target.id].retaliated
    st, second = apply(st, Attack(target.id))
    assert [event["type"] for event in second] == ["attack"]
    while st.active_id != target.id:
        st, _ = apply(st, Defend())
    assert not st.stacks[target.id].retaliated


def test_ranged_no_retaliation_and_shots_decrease():
    st = two_stacks("archer", "swordsman")
    a = st.stacks["s0_0"]
    st2, ev = apply(st, Attack("s1_0"))
    assert [e["type"] for e in ev] == ["attack"] and ev[0]["ranged"]
    assert st2.stacks["s0_0"].shots_left == a.shots_left - 1


def test_archer_deals_double_damage_within_shooting_range_only_when_shooting():
    st = two_stacks("archer", "swordsman")
    archer, target = st.stacks["s0_0"], st.stacks["s1_0"]
    assert UNITS["archer"].shooting_range == 6
    archer.x, archer.y, target.y = 0, 0, 0
    target.x = 7
    _, far = apply(st, Attack(target.id))
    far_estimate = expected_damage(archer, target, ranged=True)
    target.x = 6
    _, near = apply(st, Attack(target.id))
    assert expected_damage(archer, target, ranged=True) == 2 * far_estimate
    target.x = 1
    _, melee = apply(st, Attack(target.id))
    assert far[0]["ranged"] and near[0]["ranged"] and not melee[0]["ranged"]
    assert near[0]["damage"] == 2 * far[0]["damage"]
    assert melee[0]["damage"] == far[0]["damage"]


def test_wait_only_once_and_delays_by_half_period():
    st = create_battle([("knight", 1), ("archer", 1)], [("goblin", 1)], 1)
    actor = st.active()
    st, _ = apply(st, Wait())
    assert st.stacks[actor.id].ready == actor.ready + actor.ready // 2
    while st.active_id != actor.id:
        st, _ = apply(st, Defend())
    with pytest.raises(IllegalAction):
        apply(st, Wait())


def test_input_state_not_mutated_and_roundtrip():
    st = two_stacks()
    snapshot = st.to_dict()
    apply(st, Defend())
    assert st.to_dict() == snapshot
    assert BattleState.from_dict(snapshot).to_dict() == snapshot


def test_turn_info_lists_targets():
    st = two_stacks()
    a, b = put_adjacent(st)
    info = turn_info(st)
    assert info["active"] == a.id and info["targets"][0]["id"] == b.id


def test_ai_vs_ai_finishes_and_is_deterministic():
    army_a = [("swordsman", 8), ("archer", 12), ("peasant", 30)]
    army_b = [("knight", 3), ("goblin", 25), ("skeleton", 20), ("archer", 8)]
    results = []
    for _ in range(2):
        st = create_battle(army_a, army_b, seed=42)
        st, ev = run_ai(st, ai_sides={0, 1})
        results.append((st.to_dict(), len(ev)))
    assert results[0] == results[1]
    assert results[0][0]["status"] == "finished"


def test_human_turn_stops_ai_loop():
    st = create_battle([("swordsman", 3)], [("goblin", 3)], 7)
    st, _ = run_ai(st, ai_sides={1})
    assert st.status == "active" and st.active().owner == 0


def test_low_level_pve_is_8x8_with_5_slots():
    army = [("peasant", 1)] * 5
    st = create_battle(army, army, 1, level=3, mode="pve")
    assert (st.width, st.height) == (8, 8)
    assert {s.x for s in st.stacks.values()} == {0, 7}
    with pytest.raises(ValueError):
        create_battle([("peasant", 1)] * 6, army, 1, level=3, mode="pve")


def test_pvp_and_level4_allow_8_slots():
    army = [("peasant", 1)] * 8
    pvp = create_battle(army, army, 1, level=1, mode="pvp")
    assert (pvp.width, pvp.height) == (12, 8)
    pve4 = create_battle(army, army, 1, level=4, mode="pve")
    assert (pve4.width, pve4.height) == (12, 8)
    with pytest.raises(ValueError):
        create_battle([("peasant", 1)] * 9, army, 1, level=4, mode="pvp")
