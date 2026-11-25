import pytest

from engine import (Attack, BattleState, Defend, IllegalAction, Move, Wait,
                    apply, create_battle, forecast, reachable, run_ai, turn_info)
from engine.data import UNITS
from engine.events import action_events, reconstruct
from engine.rules import _hurt, cheb, expected_damage, init_timeline
from engine.state import HeroTurn, Stack


def two_stacks(unit_a="swordsman", unit_b="swordsman", ca=5, cb=5, seed=1):
    return create_battle([(unit_a, ca)], [(unit_b, cb)], seed)


def put_adjacent(st):
    a, b = st.stacks["s0_0"], st.stacks["s1_0"]
    a.x, a.y, b.x, b.y = 5, 2, 6, 2
    return a, b


def test_field_size_is_independent_of_army_size():
    small = create_battle([("peasant", 5)], [("goblin", 5)], 1, level=4, mode="pve")
    assert (small.width, small.height) == (12, 10)
    army = [("peasant", 1)] * 7
    big = create_battle(army, [("goblin", 1)], 1, level=4, mode="pve")
    assert big.height == 10
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


def test_hero_shot_ignores_defense_and_is_recorded_without_retaliation():
    st = two_stacks()
    hero = HeroTurn("hero_0", 0, "Герой", 1, 20, 0, 0, 0, 0, 5, 8)
    st.heroes[hero.id] = hero
    init_timeline(st)
    assert st.active_id == hero.id and forecast(st, 1) == [{"id": hero.id}]
    assert turn_info(st)["targets"] == [{"id": "s1_0", "from": []}]
    with pytest.raises(IllegalAction):
        apply(st, Move(1, 0))
    with pytest.raises(IllegalAction):
        apply(st, Attack("s0_0"))

    _, normal = apply(st, Attack("s1_0"))
    st.stacks["s1_0"].defending = True
    new, events = apply(st, Attack("s1_0"))
    assert [event["type"] for event in events] == ["hero_attack"]
    assert 5 <= events[0]["damage"] == normal[0]["damage"] <= 8
    assert new.heroes[hero.id].ready > hero.ready
    assert reconstruct(st.to_dict(), action_events(st, new, events)) == new.to_dict()


def test_wait_repeats_and_delays_by_half_period():
    from backend.engine.rules import forecast, wait_delay

    st = create_battle([("knight", 1), ("archer", 1)], [("goblin", 1)], 1)
    actor = st.active()
    expected = forecast(st, 12, after_wait=True)
    st, _ = apply(st, Wait())
    assert st.stacks[actor.id].ready == actor.ready + wait_delay(actor)
    assert expected == forecast(st, 12)
    while st.active_id != actor.id:
        st, _ = apply(st, Defend())
    next_state, _ = apply(st, Wait())
    assert next_state.stacks[actor.id].ready == st.stacks[actor.id].ready + wait_delay(actor)


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


def test_initial_readiness_varies_within_ten_percent_and_is_snapshotted():
    from engine.rules import period

    offsets = set()
    for seed in range(20):
        state = two_stacks(seed=seed)
        hero = HeroTurn("hero_0", 0, "Герой", 1, 10, 0, 0, 0, 0, 5, 8)
        state.heroes[hero.id] = hero
        init_timeline(state)
        assert set(state.initial_ready_at) == {actor.id for actor in state.actors()}
        for actor in state.actors():
            assert state.initial_ready_at[actor.id] == actor.ready
            offset = actor.ready - period(actor)
            assert abs(offset) <= period(actor) // 10
            offsets.add(offset)
        snapshot = state.to_dict()
        init_timeline(state)
        assert state.to_dict() == snapshot == BattleState.from_dict(snapshot).to_dict()
    assert min(offsets) < 0 < max(offsets)


def test_attack_previews_match_defended_shot_and_forced_melee():
    from math import floor

    from engine.actions import action_from_dict
    from engine.flow import play_turn

    state = two_stacks("archer", "swordsman", ca=15, cb=10)
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    actor.x, actor.y, target.x, target.y = 0, 0, 6, 0
    state.active_id = actor.id
    target.defending = True
    preview = turn_info(state)["targets"][0]["preview"]
    unit, enemy = UNITS[actor.unit], UNITS[target.unit]
    multiplier = 1 + .025 * (unit.attack - enemy.defense * 1.3)
    assert preview["eff_def"] == enemy.defense * 1.3
    assert preview["mult"] == pytest.approx(multiplier)
    assert (preview["base_dmg_min"], preview["base_dmg_max"]) == (15 * unit.dmg_min, 15 * unit.dmg_max)
    assert (preview["roll_count"], preview["roll_scale"]) == (10, 1.5)
    assert preview["average_damage"] == 2 * floor(15 * (unit.dmg_min + unit.dmg_max) / 2 * multiplier)
    assert preview["final_dmg_max"] == 2 * floor(15 * unit.dmg_max * multiplier)
    assert preview["unit_dmg_min"] == max(1, floor(unit.dmg_min * multiplier * 2))
    assert preview["estimated_kills"] == min(target.count, preview["final_dmg_max"] // enemy.hp)
    assert preview["is_double_shot"] and not preview["will_counterattack"]
    _, shot = apply(state, Attack(target.id))
    assert preview["final_dmg_min"] <= shot[0]["damage"] <= preview["final_dmg_max"]

    target.x = 7
    distant = turn_info(state)["targets"][0]["preview"]
    assert not distant["is_double_shot"] and distant["final_dmg_max"] * 2 == preview["final_dmg_max"]
    with pytest.raises(IllegalAction):
        apply(state, Attack(target.id, (6, 0), force_melee=True))

    target.x = 2
    choices = turn_info(state)["targets"][0]
    assert [1, 0] in choices["melee_from"] and choices["melee_preview"]["will_counterattack"]
    action = {"type": "attack", "target_id": target.id, "from_pos": [1, 0], "force_melee": True}
    after, steps = play_turn(state, 0, action_from_dict(action))
    assert after.stacks[actor.id].shots_left == actor.shots_left
    assert [event["type"] for event in steps[0].events] == ["move", "attack", "retaliation"]
    hit = next(event for event in steps[0].replay_events if event["type"] == "DAMAGE_APPLIED")
    assert (hit["seq"], hit["actor_id"], hit["target_id"], hit["action"]) == (1, actor.id, target.id, action)
    assert hit["payload"]["distance"] == 1 and not hit["payload"]["double_damage"]
    assert hit["payload"]["target_hp_pool_after"] == hit["payload"]["hp_after"]
    assert hit["payload"]["damage_dealt"] == hit["payload"]["hp_before"] - hit["payload"]["hp_after"]
    assert hit["payload"]["target_count_after"] == hit["payload"]["creatures_after"]
    ended = next(event for event in steps[0].replay_events if event["type"] == "TURN_ENDED")
    assert ended["payload"]["next_ready_at"] == after.stacks[actor.id].ready
    assert reconstruct(state.to_dict(), steps[0].replay_events) == after.to_dict()

    target.x = 1
    info = turn_info(state)
    assert info["shooting_blocked"] and not info["can_shoot"]
    assert not info["targets"][0]["preview"]["can_shoot"]

    from engine.rules import attack_preview
    knight = Stack("knight", "knight", 0, 1, UNITS["knight"].hp, 0, 0)
    assert attack_preview(knight, target, ranged=False)["mult"] == pytest.approx(1.02)


def test_elf_summon_with_full_slots_replaces_and_replays_until_battle_end():
    from copy import deepcopy

    from engine.actions import Summon
    from engine.flow import play_turn, surrender_turn
    from engine.rules import period
    from engine.summoning import available_elements, hp_pool, max_energy

    state = create_battle([("peasant", 2)] * 8, [("goblin", 20)], seed=37, level=4)
    hero = HeroTurn("hero_0", 0, "Ельф", 4, 10, 0, 0, 1, 2, 5, 8, faction="elves")
    state.heroes[hero.id] = hero
    state.summoning["0"] = {"elements": available_elements(2), "school_level": 2,
                            "energy": max_energy(hero.knowledge), "hp_pool": hp_pool(hero.spell_power), "cost": 10}
    init_timeline(state)
    state.active_id = hero.id
    blocked = deepcopy(state)
    for y in range(blocked.height):
        for x in range(blocked.width // 2):
            key = f"block_{x}_{y}"
            blocked.stacks[key] = Stack(key, "peasant", 0, 1, UNITS["peasant"].hp, x, y)
    with pytest.raises(IllegalAction, match="немає місця"):
        apply(blocked, Summon("earth"))
    assert blocked.summoning["0"]["energy"] == 20

    first, steps = play_turn(state, 0, Summon("earth"))
    summon = next(stack for stack in first.stacks.values() if stack.summoned)
    assert len([stack for stack in first.stacks.values() if stack.owner == 0]) == 9
    assert summon.initial_count == summon.count
    assert summon.ready == hero.ready + period(summon) and summon.x < first.width // 2
    event = next(event for event in steps[0].replay_events if event["type"] == "ELEMENTAL_SUMMONED")
    assert event["payload"]["summon_ready_at"] == summon.ready
    assert event["payload"]["spawn_pos"] == (summon.x, summon.y)
    assert event["payload"]["spell"] == "earth" and event["payload"]["summon_id"] == summon.id
    assert reconstruct(state.to_dict(), steps[0].replay_events) == first.to_dict()

    first.active_id = hero.id
    second, steps = play_turn(first, 0, Summon("water"))
    assert summon.id not in second.stacks
    assert all(entry["id"] != summon.id for entry in forecast(second))
    assert second.summoning["0"]["energy"] == 0
    assert reconstruct(first.to_dict(), steps[0].replay_events) == second.to_dict()
    final, steps = surrender_turn(second, 0)
    assert not any(stack.summoned for stack in final.stacks.values())
    assert steps[0].replay_events[-1]["payload"]["outcome"] == {"winner_side": 1, "surrendered_side": 0}
    assert reconstruct(second.to_dict(), steps[0].replay_events) == final.to_dict()


def test_weighted_movement_uses_speed_times_ten():
    state = two_stacks()
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    state.active_id = actor.id
    actor.x, actor.y, target.x, target.y = 0, 0, 7, 4
    costs = reachable(state, actor)
    assert UNITS[actor.unit].speed == 4
    assert costs[4, 0] == costs[3, 2] == 40
    assert (3, 3) not in costs and (5, 0) not in costs
    assert turn_info(state)["move_points"] == 40
    with pytest.raises(IllegalAction, match="недосяжна"):
        apply(state, Move(3, 3))


def test_ground_route_avoids_obstacles_and_blocked_corners():
    state = two_stacks("swordsman", "peasant")
    actor, blocker = state.stacks["s0_0"], state.stacks["s1_0"]
    state.active_id = actor.id
    actor.x, actor.y, blocker.x, blocker.y = 0, 0, 0, 1
    state.obstacles = [[1, 0]]
    assert reachable(state, actor) == {(0, 0): 0}

    blocker.x, blocker.y = 7, 4
    routes = turn_info(state)["move_paths"]
    assert routes["1,1"]["cost"] == 15
    assert routes["2,0"] == {"cost": 30, "path": [[0, 0], [1, 1], [2, 0]]}
    after, events = apply(state, Move(2, 0))
    assert events[0]["path"] == routes["2,0"]["path"]
    assert events[0]["move_points"] == 30 and not events[0]["flying"]
    assert reconstruct(state.to_dict(), action_events(state, after, events)) == after.to_dict()


def test_corner_cutting_checks_the_entire_ground_footprint():
    state = two_stacks("ogre", "peasant")
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    actor.x, actor.y, target.x, target.y = 0, 0, 7, 4
    state.obstacles = [[2, 0], [0, 2]]
    assert (1, 1) not in reachable(state, actor)
    state.obstacles.pop()
    assert reachable(state, actor)[1, 1] == 15


def test_dragon_flies_over_units_and_obstacles_but_needs_a_free_landing():
    state = two_stacks("dragon", "peasant")
    actor, blocker = state.stacks["s0_0"], state.stacks["s1_0"]
    state.active_id = actor.id
    actor.x, actor.y, blocker.x, blocker.y = 0, 0, 3, 2
    state.obstacles = [[2, y] for y in range(state.height)]
    costs = reachable(state, actor)
    assert costs[4, 2] == 50  # Two diagonal steps plus two straight steps.
    assert (3, 2) not in costs  # Blocked by the squad.
    assert (2, 2) not in costs  # Blocked by the wall.
    assert (5, 1) not in costs  # 55 move points.
    assert (7, 0) not in costs  # The landing footprint extends off the board.
    after, events = apply(state, Move(4, 2))
    assert events[0] == {
        "type": "move", "stack": actor.id, "path": [[0, 0], [4, 2]], "move_points": 50, "flying": True,
    }
    assert reconstruct(state.to_dict(), action_events(state, after, events)) == after.to_dict()


def test_melee_approach_uses_weighted_routes_and_logs_the_chosen_path():
    state = two_stacks()
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    state.active_id = actor.id
    actor.x, actor.y, target.x, target.y = 0, 0, 4, 4
    assert turn_info(state)["targets"] == []
    with pytest.raises(IllegalAction, match="недосяжна"):
        apply(state, Attack(target.id, (3, 3)))

    target.y = 3
    info = turn_info(state)
    assert info["targets"][0]["melee_from"] == [[3, 2]]
    route = info["move_paths"]["3,2"]
    after, events = apply(state, Attack(target.id, (3, 2)))
    assert events[0]["path"] == route["path"]
    assert events[0]["move_points"] == route["cost"] == 40
    replay_events = action_events(state, after, events)
    assert replay_events[0]["payload"]["to"] == [3, 2]
    assert replay_events[0]["payload"]["path"] == route["path"][1:]
    assert reconstruct(state.to_dict(), replay_events) == after.to_dict()


@pytest.mark.parametrize("line", ["elves_solaris", "underground_elves_obscuro"])
@pytest.mark.parametrize("form", [1, 2, 3])
def test_form_abilities_control_movement(line, form):
    key = f"{line}_{form}"
    state = two_stacks(key, "peasant")
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    state.active_id = actor.id
    actor.x, actor.y, target.x, target.y = 0, 0, 7, 4
    state.obstacles = [[2, 0], [0, 2], [2, 2]]
    info = turn_info(state)
    if form == 1:
        assert UNITS[key].abilities == ()
        assert not info["flying"] and info["move"] == []
        return

    assert UNITS[key].abilities == ("flying",)
    assert info["flying"] and info["move_paths"]["3,2"] == {"cost": 40, "path": [[0, 0], [3, 2]]}
    assert [2, 2] not in info["move"]
    after, events = apply(state, Move(3, 2))
    assert events[0]["flying"] and events[0]["move_points"] == 40
    assert reconstruct(state.to_dict(), action_events(state, after, events)) == after.to_dict()


def test_form_abilities_fall_back_to_parent_unless_given_a_list(monkeypatch):
    from copy import deepcopy

    from engine import data

    rosters = deepcopy(data.FACTION_ROSTERS)
    lineage = next(line for line in rosters["elves"] if line["key"] == "solaris")
    lineage["abilities"] = ["flying"]
    lineage["forms"][1].pop("abilities")
    lineage["forms"][2]["abilities"] = "flying"
    monkeypatch.setattr(data, "FACTION_ROSTERS", rosters)
    units = data.load_creatures()
    assert units["elves_solaris_1"].abilities == ()
    assert units["elves_solaris_2"].abilities == units["elves_solaris_3"].abilities == ("flying",)
    assert units["dragon"].abilities == ("flying",)
    assert data.resolved_abilities({}, {"abilities": None}) == []


@pytest.mark.parametrize("level", [1, 4])
def test_obstacle_generation_varies_with_seed_and_preserves_clear_deployment(level):
    from engine.obstacles import _connected
    from engine.setup import ZONE_COLS

    layouts = set()
    for seed in range(12):
        state = create_battle([("swordsman", 10)], [("dragon", 1), ("ogre", 2)], seed, level=level)
        obstacles = {tuple(cell) for cell in state.obstacles}
        assert obstacles and state.obstacle_kind == "rock"
        assert len(obstacles) <= state.width * state.height // 20
        assert all(ZONE_COLS <= x < state.width - ZONE_COLS and 0 <= y < state.height for x, y in obstacles)
        assert not obstacles.intersection(cell for stack in state.stacks.values() for cell in stack.cells())
        assert _connected(state.width, state.height, (2, 3), obstacles)
        snapshot = state.to_dict()
        assert BattleState.from_dict(snapshot).to_dict() == snapshot
        assert create_battle([("swordsman", 10)], [("dragon", 1), ("ogre", 2)], seed, level=level).to_dict() == snapshot
        layouts.add(frozenset(obstacles))
    assert len(layouts) > 1


def test_generated_rocks_change_ground_routes_and_only_block_flight_landings():
    state = two_stacks("swordsman", "dragon", seed=2)
    ground, flyer = state.stacks["s0_0"], state.stacks["s1_0"]
    assert [3, 1] in state.obstacles
    ground.x, ground.y = 2, 1
    state.active_id = ground.id
    routes = turn_info(state)["move_paths"]
    assert "3,1" not in routes
    assert routes["4,1"] == {"cost": 30, "path": [[2, 1], [3, 0], [4, 1]]}

    ground.x, ground.y, flyer.x, flyer.y = 11, 6, 0, 1
    state.active_id = flyer.id
    routes = turn_info(state)["move_paths"]
    assert "3,1" not in routes
    assert routes["4,1"] == {"cost": 40, "path": [[0, 1], [4, 1]]}
    after, events = apply(state, Move(4, 1))
    assert reconstruct(state.to_dict(), action_events(state, after, events)) == after.to_dict()


def test_luck_and_morale_streaks_escalate_independently_and_reset(monkeypatch):
    from engine import squad_effects

    class NearMaximum:
        def __init__(self, seed):
            pass

        def random(self):
            return .9999

    monkeypatch.setattr(squad_effects, "Random", NearMaximum)
    state = two_stacks()
    actor = state.stacks["s0_0"]
    actor.luck, actor.morale = 5, -10
    events = []
    assert squad_effects.roll_squad_stat(state, actor, "morale", events) == 0
    assert [squad_effects.roll_squad_stat(state, actor, "luck", events) for _ in range(4)] == [0, 0, 0, 1]
    assert [event["chance"] for event in events[1:]] == [25, 50, 75, 100]
    assert events[-1]["animation_event"] and events[-1]["anim_type"] == "positive_luck"
    assert all(not event["animation_event"] for event in events[:-1])
    assert (actor.luck_streak, actor.morale_streak) == (1, 2)
    assert squad_effects.roll_squad_stat(state, actor, "morale", events) == -1
    assert events[-1]["chance"] == 100 and events[-1]["anim_type"] == "negative_morale"
    assert (actor.luck_streak, actor.morale_streak) == (1, 1)


@pytest.mark.parametrize(("stat", "sign"), [(20, "positive"), (-20, "negative")])
def test_luck_changes_final_shot_and_morale_adjusts_readiness(stat, sign):
    from engine.rules import period

    state = two_stacks("archer", "swordsman", ca=5, cb=20)
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    actor.x, actor.y, target.x, target.y = 0, 0, 6, 0
    state.active_id = actor.id
    _, baseline = apply(state, Attack(target.id))
    actor.luck = actor.morale = stat
    before = state.to_dict()
    after, events = apply(state, Attack(target.id))
    luck, attack, morale = events
    expected_damage = baseline[0]["damage"] * 2 if stat > 0 else max(1, baseline[0]["damage"] // 2)
    expected_interval = period(actor) // 2 if stat > 0 else period(actor) + period(actor) // 2
    assert attack["damage"] == luck["damage_after"] == expected_damage
    assert luck["outcome"] == morale["outcome"] == sign
    assert morale["next_ready_at"] == after.stacks[actor.id].ready == actor.ready + expected_interval
    recorded = action_events(state, after, events, {"type": "attack", "target_id": target.id})
    assert reconstruct(before, recorded) == after.to_dict()
    assert apply(state, Attack(target.id))[1] == events


def test_healing_fills_wounded_unit_first_and_caps_resurrection():
    from engine.squad_effects import heal_squad

    stack = Stack("s0_0", "swordsman", 0, 2, 5, 0, 0, initial_count=4)
    assert heal_squad(stack, 100) == 30 and (stack.count, stack.top_hp) == (2, 35)
    assert heal_squad(stack, 1, allow_resurrect=True) == 1 and (stack.count, stack.top_hp) == (3, 1)
    assert heal_squad(stack, 500, allow_resurrect=True) == 69 and (stack.count, stack.top_hp) == (4, 35)
    assert heal_squad(stack, 1, allow_resurrect=True) == 0
    stack.count = stack.top_hp = 0
    assert heal_squad(stack, 300) == 0 and stack.count == 0
    assert heal_squad(stack, 300, allow_resurrect=True) == 140 and stack.count == stack.initial_count


def test_heal_event_replays_with_luck_and_morale():
    from engine.squad_effects import heal_squad

    state = two_stacks("archer", "peasant", ca=10, cb=2)
    actor, target = state.stacks["s0_0"], state.stacks["s1_0"]
    state.active_id = actor.id
    actor.luck = actor.morale = 20
    actor.x, actor.y, target.x, target.y = 0, 0, 4, 0
    reserve = Stack("reserve", "peasant", 1, 3, 4, 7, 4, initial_count=3)
    state.stacks[reserve.id] = reserve
    after, events = apply(state, Attack(target.id))
    assert target.id not in after.stacks
    target = Stack(target.id, target.unit, target.owner, 0, 0, target.x, target.y, initial_count=2)
    assert heal_squad(target, 100, allow_resurrect=True, events=events) == 8
    after.stacks[target.id] = target
    replay_events = action_events(state, after, events)
    assert {"LUCK_ROLLED", "MORALE_ROLLED", "UNIT_HEALED"} <= {e["type"] for e in replay_events}
    assert reconstruct(state.to_dict(), replay_events) == after.to_dict()


@pytest.mark.parametrize("hero_sides, height", [([0, 1], 10), ([0, 0, 1], 20), ([0, 1, 1], 20), ([0, 0, 1, 1], 20)])
def test_battle_height_depends_on_the_largest_hero_team(hero_sides, height):
    heroes = [HeroTurn(f"hero_{i}", side, f"Герой {i}", 1, 10, 0, 0, 0, 0, 5, 8)
              for i, side in enumerate(hero_sides)]
    battle = create_battle([("peasant", 1)], [("dragon", 1)], 45, mode="pvp", heroes=heroes)
    assert (battle.width, battle.height) == (12, height)
    assert len(battle.heroes) == len(heroes)
    assert BattleState.from_dict(battle.to_dict()).height == height
