import pytest

from engine import Defend, IllegalAction, create_battle
from engine.actions import Attack, Move, Skip, Wait, action_from_dict, action_to_dict
from engine.flow import NotYourTurn, advance_ai, play_turn, surrender_turn


def fresh():
    st = create_battle([("swordsman", 5), ("archer", 6)], [("goblin", 9), ("skeleton", 7)],
                       seed=3, level=1, mode="pve")
    return advance_ai(st, {1})  # якщо першим ходить ШІ


def test_action_roundtrip():
    for a in (Move(2, 3), Attack("s1_0", (4, 4)), Attack("s1_0"), Wait(), Defend(), Skip()):
        assert action_from_dict(action_to_dict(a)) == a


def test_ai_moves_first_when_needed_then_human():
    st, steps = fresh()
    assert st.active().owner == 0
    assert all(s.side == 1 for s in steps)


def test_play_turn_runs_ai_and_numbers_actions():
    st, _ = fresh()
    seq0 = st.seq
    st2, steps = play_turn(st, 0, Defend(), ai_sides={1})
    assert steps[0].side == 0 and steps[0].action == {"type": "defend"}
    assert all(s.side == 1 for s in steps[1:])
    assert st2.seq == seq0 + len(steps)
    assert st2.status == "finished" or st2.active().owner == 0


def test_wrong_side_rejected():
    st, _ = fresh()
    with pytest.raises(NotYourTurn):
        play_turn(st, 1, Defend(), ai_sides={1})


def test_full_pve_game_via_flow_terminates():
    st, _ = fresh()
    for _ in range(700):
        if st.status == "finished":
            break
        st, _ = play_turn(st, 0, Defend(), ai_sides={1})  # людина лише захищається
    assert st.status == "finished"


def test_finished_battle_rejects_actions():
    st, _ = fresh()
    while st.status != "finished":
        st, _ = play_turn(st, 0, Defend(), ai_sides={1})
    with pytest.raises(IllegalAction):
        play_turn(st, 0, Defend(), ai_sides={1})


def test_surrender_turn_logs_step_and_finishes():
    st, _ = fresh()
    st2, steps = surrender_turn(st, 0)
    assert st2.status == "finished" and st2.winner == 1 and st2.seq == st.seq + 1
    assert steps[0].action == {"type": "surrender"} and steps[0].side == 0
