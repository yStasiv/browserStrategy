import pytest

from engine import (Attack, BattleState, Defend, IllegalAction, Move, Wait,
                    apply, create_battle, reachable, run_ai, turn_info)
from engine.data import UNITS
from engine.rules import _hurt, cheb
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
    inits = [UNITS[st.stacks[i].unit].initiative for i in st.queue]
    assert inits == sorted(inits, reverse=True)


def test_hurt_kills_whole_creatures():
    s = Stack("x", "swordsman", 0, count=5, top_hp=35, x=0, y=0)  # hp 35 на істоту
    assert _hurt(s, 40) == 1 and (s.count, s.top_hp) == (4, 30)
    assert _hurt(s, 1000) == 4 and s.count == 0


def test_move_blocked_cells_and_range():
    st = two_stacks()
    a = st.stacks[st.queue[0]]
    reach = reachable(st, a)
    assert all(cheb(a.x, a.y, x, y) <= 4 for x, y in reach)
    with pytest.raises(IllegalAction):
        apply(st, Move(a.x + 9, a.y))


def test_melee_move_attack_and_single_retaliation_per_round():
    st = two_stacks()
    a, b = put_adjacent(st)
    st.queue = [a.id, b.id]
    st2, ev = apply(st, Attack(b.id))
    kinds = [e["type"] for e in ev]
    assert kinds == ["attack", "retaliation"]
    assert st2.stacks[b.id].retaliated is True
    # другий удар по тому ж загону в тому ж раунді — без контратаки
    st2.queue = [a.id, b.id]
    st3, ev = apply(st2, Attack(b.id))
    assert [e["type"] for e in ev] == ["attack"]


def test_ranged_no_retaliation_and_shots_decrease():
    st = two_stacks("archer", "swordsman")
    a = st.stacks["s0_0"]
    st.queue = [a.id, "s1_0"]
    st2, ev = apply(st, Attack("s1_0"))
    assert [e["type"] for e in ev] == ["attack"] and ev[0]["ranged"]
    assert st2.stacks["s0_0"].shots_left == a.shots_left - 1


def test_wait_only_once_and_moves_to_end():
    st = create_battle([("knight", 1), ("archer", 1)], [("goblin", 1)], 1)
    first = st.queue[0]
    st2, _ = apply(st, Wait())
    assert st2.queue[-1] == first
    # той самий загін знову на початку черги не може чекати вдруге
    st3 = st2
    while st3.queue[0] != first:
        st3, _ = apply(st3, Defend())
    with pytest.raises(IllegalAction):
        apply(st3, Wait())


def test_input_state_not_mutated_and_roundtrip():
    st = two_stacks()
    snapshot = st.to_dict()
    apply(st, Defend())
    assert st.to_dict() == snapshot
    assert BattleState.from_dict(snapshot).to_dict() == snapshot


def test_turn_info_lists_targets():
    st = two_stacks()
    a, b = put_adjacent(st)
    st.queue = [a.id, b.id]
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
