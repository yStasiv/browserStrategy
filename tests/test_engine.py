import pytest

from engine import (Attack, BattleState, Defend, IllegalAction, Move, Wait,
                    apply, create_battle, forecast, reachable, run_ai, surrender, turn_info)
from engine.data import UNITS
from engine.rules import _hurt, rect_dist
from engine.state import Stack


def two_stacks(unit_a="swordsman", unit_b="swordsman", ca=5, cb=5, seed=1):
    return create_battle([(unit_a, ca)], [(unit_b, cb)], seed, level=1, mode="pve")


def put_adjacent(st):
    a, b = st.stacks["s0_0"], st.stacks["s1_0"]
    a.x, a.y, b.x, b.y = 5, 2, 6, 2
    return a, b


# ---------- поле і розстановка ----------

def test_field_size_is_independent_of_army_size():
    small = create_battle([("peasant", 5)], [("goblin", 5)], 1, level=4, mode="pve")
    assert (small.width, small.height) == (12, 10)
    big = create_battle([("peasant", 1)] * 7, [("goblin", 1)], 1, level=4, mode="pve")
    assert big.height == 10
    cells = [c for s in big.stacks.values() for c in s.cells()]
    assert len(cells) == len(set(cells))


def test_low_level_pve_is_12x10_with_5_slots():
    army = [("peasant", 1)] * 5
    st = create_battle(army, army, 1, level=3, mode="pve")
    assert (st.width, st.height) == (12, 10)
    assert {s.x for s in st.stacks.values()} == {0, 11}
    with pytest.raises(ValueError):
        create_battle([("peasant", 1)] * 6, army, 1, level=3, mode="pve")


def test_pvp_and_level4_allow_8_slots():
    army = [("peasant", 1)] * 8
    pvp = create_battle(army, army, 1, level=1, mode="pvp")
    assert (pvp.width, pvp.height) == (12, 10)
    pve4 = create_battle(army, army, 1, level=4, mode="pve")
    assert (pve4.width, pve4.height) == (12, 10)
    with pytest.raises(ValueError):
        create_battle([("peasant", 1)] * 9, army, 1, level=4, mode="pvp")


def all_cells_ok(st):
    cells = [c for s in st.stacks.values() for c in s.cells()]
    assert len(cells) == len(set(cells)), "загони накладаються"
    assert all(0 <= x < st.width and 0 <= y < st.height for x, y in cells), "вихід за поле"


def test_big_units_footprints_and_deploy():
    st = create_battle([("dragon", 1), ("ogre", 1), ("peasant", 5)],
                       [("ogre", 2), ("goblin", 9)], 1, level=1, mode="pve")
    all_cells_ok(st)
    d = st.stacks["s0_0"]
    assert (d.w, d.h) == (2, 3) and len(d.cells()) == 6
    assert st.stacks["s1_0"].x == st.width - 2   # великий загін справа притиснутий до краю


def test_tall_army_falls_back_to_multi_column_layout():
    army = [("dragon", 1), ("dragon", 1), ("dragon", 1), ("peasant", 1), ("peasant", 1)]  # висота 11 > 10
    st = create_battle(army, [("goblin", 3)], 1, level=3, mode="pve")
    all_cells_ok(st)


def test_army_too_big_for_field_rejected():
    army = [("dragon", 1)] * 5   # У 3 колонках не поміщаються п’ять загонів 2×3.
    with pytest.raises(ValueError):
        create_battle(army, [("goblin", 3)], 1, level=3, mode="pve")


# ---------- геометрія великих загонів ----------

def test_rect_dist_adjacency():
    # огр 2x2 у (3,3)-(4,4)
    assert rect_dist(3, 3, 2, 2, 5, 4, 1, 1) == 1   # збоку
    assert rect_dist(3, 3, 2, 2, 5, 5, 1, 1) == 1   # по діагоналі
    assert rect_dist(3, 3, 2, 2, 6, 3, 1, 1) == 2   # через клітинку
    assert rect_dist(3, 3, 2, 2, 3, 5, 1, 1) == 1   # знизу


def test_big_unit_reach_never_overlaps_or_leaves_field():
    st = create_battle([("ogre", 2), ("peasant", 5)], [("goblin", 4), ("archer", 3)], 2, level=1, mode="pve")
    ogre = st.stacks["s0_0"]
    others = {c for s in st.stacks.values() if s.id != ogre.id for c in s.cells()}
    reach = reachable(st, ogre)
    assert len(reach) > 1
    for (x, y) in reach:
        cells = {(x + i, y + j) for i in range(ogre.w) for j in range(ogre.h)}
        assert all(0 <= cx < st.width and 0 <= cy < st.height for cx, cy in cells)
        assert not cells & others


def test_attack_big_target_from_adjacent_cells():
    st = two_stacks("swordsman", "ogre", ca=5, cb=2)
    a, b = st.stacks["s0_0"], st.stacks["s1_0"]
    a.x, a.y, b.x, b.y = 2, 2, 5, 2
    st.active_id = a.id
    t = turn_info(st)["targets"][0]
    assert t["id"] == b.id and t["from"]
    for fx, fy in t["from"]:
        assert rect_dist(fx, fy, 1, 1, b.x, b.y, 2, 2) == 1
    st2, ev = apply(st, Attack(b.id, tuple(t["from"][0])))
    assert ev[0]["type"] == "move" and ev[1]["type"] == "attack"


def test_archer_next_to_big_enemy_corner_cannot_shoot():
    st = two_stacks("archer", "ogre", ca=10, cb=1)
    a, b = st.stacks["s0_0"], st.stacks["s1_0"]
    a.x, a.y, b.x, b.y = 3, 3, 4, 4   # діагональний контакт з кутом огра
    st.active_id = a.id
    assert turn_info(st)["ranged"] is False


# ---------- шкода ----------

def test_hurt_kills_whole_creatures():
    s = Stack("x", "swordsman", 0, count=5, top_hp=35, x=0, y=0)
    assert _hurt(s, 40) == 1 and (s.count, s.top_hp) == (4, 30)
    assert _hurt(s, 1000) == 4 and s.count == 0


# ---------- рух і бій ----------

def test_move_blocked_cells_and_range():
    st = two_stacks()
    a = st.active()
    assert all(max(abs(a.x - x), abs(a.y - y)) <= UNITS[a.unit].speed for x, y in reachable(st, a))
    with pytest.raises(IllegalAction):
        apply(st, Move(a.x + 9, a.y))


def test_no_second_retaliation_before_own_turn():
    st = two_stacks()
    a, b = put_adjacent(st)
    st.active_id = a.id
    b.retaliated = True          # b уже контратакував, а власного ходу ще не було
    st2, ev = apply(st, Attack(b.id))
    assert [e["type"] for e in ev] == ["attack"]


def test_retaliation_resets_on_own_turn():
    st = two_stacks("swordsman", "swordsman", ca=20, cb=20)
    a, b = put_adjacent(st)
    st.active_id = a.id
    st, ev = apply(st, Attack(b.id))
    assert [e["type"] for e in ev] == ["attack", "retaliation"]
    # тепер ходить b — його прапорець контратаки скинуто, і a може контратакувати у відповідь
    assert st.active().id == b.id and st.stacks[b.id].retaliated is False
    st, ev = apply(st, Attack(a.id))
    assert [e["type"] for e in ev] == ["attack", "retaliation"]


def test_ranged_no_retaliation_and_shots_decrease():
    st = two_stacks("archer", "swordsman")
    a = st.stacks["s0_0"]
    st.active_id = a.id
    st2, ev = apply(st, Attack("s1_0"))
    assert [e["type"] for e in ev] == ["attack"] and ev[0]["ranged"]
    assert st2.stacks["s0_0"].shots_left == a.shots_left - 1


def test_archer_adjacent_enemy_forces_melee():
    st = two_stacks("archer", "swordsman", ca=20)
    a, b = put_adjacent(st)
    st.active_id = a.id
    assert turn_info(st)["ranged"] is False
    st2, ev = apply(st, Attack(b.id))
    assert [e["type"] for e in ev] == ["attack", "retaliation"]
    assert ev[0]["ranged"] is False
    assert st2.stacks[a.id].shots_left == a.shots_left


def test_archer_without_adjacent_enemy_still_shoots():
    st = two_stacks("archer", "swordsman")
    st.active_id = "s0_0"
    info = turn_info(st)
    assert info["ranged"] is True
    assert info["targets"][0]["from"] == [[st.stacks["s0_0"].x, st.stacks["s0_0"].y]]


# ---------- черга, очікування, здача ----------

def test_order_follows_initiative_without_rounds():
    st = create_battle([("knight", 1), ("archer", 1)], [("goblin", 1), ("swordsman", 1)], 1, level=1, mode="pve")
    assert "round" not in st.to_dict() and "queue" not in st.to_dict()
    fc = forecast(st, 10)
    # лучник (ініціатива 10) і мечник (10) діють раніше за лицаря (8)
    first_units = [st.stacks[f["id"]].unit for f in fc[:2]]
    assert set(first_units) == {"archer", "swordsman"}


def test_faster_units_act_more_often():
    st = create_battle([("archer", 5)], [("knight", 5)], 1, level=1, mode="pve")  # 10 проти 8
    counts = {"archer": 0, "knight": 0}
    for f in forecast(st, 45):
        counts[st.stacks[f["id"]].unit] += 1
    assert counts["archer"] > counts["knight"]


def test_wait_remains_available_on_the_next_turn():
    st = create_battle([("knight", 1), ("archer", 1)], [("goblin", 1)], 1, level=1, mode="pve")
    first = st.active_id
    st2, ev = apply(st, Wait())
    assert ev == [{"type": "wait", "stack": first}]
    assert st2.stacks[first].ready > st.stacks[first].ready
    cur = st2
    for _ in range(50):                   # доходимо до того ж загону знову
        if cur.active_id == first:
            break
        cur, _ = apply(cur, Defend())
    assert cur.active_id == first
    assert turn_info(cur)["can_wait"] is True
    later, _ = apply(cur, Wait())
    assert later.stacks[first].ready > cur.stacks[first].ready


def test_surrender_ends_battle_with_other_winner():
    st = two_stacks()
    st2, ev = surrender(st, 0)
    assert st2.status == "finished" and st2.winner == 1 and st2.surrendered == 0
    assert [e["type"] for e in ev] == ["surrender", "battle_end"]
    assert st2.active() is None and turn_info(st2) is None
    with pytest.raises(IllegalAction):
        apply(st2, Defend())
    with pytest.raises(IllegalAction):
        surrender(st2, 1)


def test_surrender_allowed_out_of_turn():
    st = two_stacks()
    other = 1 - st.active().owner
    st2, _ = surrender(st, other)
    assert st2.winner == 1 - other


# ---------- прогноз ----------

def test_forecast_matches_real_turn_order():
    st = create_battle([("swordsman", 5), ("archer", 6), ("peasant", 9)],
                       [("goblin", 9), ("skeleton", 7), ("knight", 2)], seed=5, level=1, mode="pve")
    fc = forecast(st, 50)
    assert len(fc) == 50
    real, cur = [], st
    for _ in range(50):
        real.append(cur.active().id)
        cur, _ = apply(cur, Defend())   # «захист» не вбиває — склад загонів не міняється
    assert [f["id"] for f in fc] == real


def test_forecast_empty_when_finished():
    st, _ = surrender(two_stacks(), 0)
    assert forecast(st) == []


# ---------- загальне ----------

def test_input_state_not_mutated_and_roundtrip():
    st = two_stacks()
    snapshot = st.to_dict()
    apply(st, Defend())
    assert st.to_dict() == snapshot
    assert BattleState.from_dict(snapshot).to_dict() == snapshot


def test_from_dict_ignores_legacy_keys():
    d = two_stacks().to_dict()
    d["round"] = 3
    d["queue"] = ["x"]
    assert BattleState.from_dict(d).width == d["width"]


def test_turn_info_lists_targets():
    st = two_stacks()
    a, b = put_adjacent(st)
    st.active_id = a.id
    info = turn_info(st)
    assert info["active"] == a.id and info["targets"][0]["id"] == b.id


def test_ai_vs_ai_with_big_units_finishes_and_is_deterministic():
    army_a = [("ogre", 3), ("archer", 12), ("peasant", 30)]
    army_b = [("knight", 3), ("goblin", 25), ("skeleton", 20), ("dragon", 1)]
    results = []
    for _ in range(2):
        st = create_battle(army_a, army_b, seed=42, level=4, mode="pve")
        st, ev = run_ai(st, ai_sides={0, 1})
        all_cells_ok(st)
        results.append((st.to_dict(), len(ev)))
    assert results[0] == results[1]
    assert results[0][0]["status"] == "finished"


def test_human_turn_stops_ai_loop():
    st = create_battle([("swordsman", 3)], [("goblin", 3)], 7, level=1, mode="pve")
    st, _ = run_ai(st, ai_sides={1})
    assert st.status == "active" and st.active().owner == 0
