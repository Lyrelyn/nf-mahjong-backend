"""``action/arbiter.py`` 的 pytest 对拍 —— 逐条翻译
``tests/core/action/arbiter.test.ts``。

``arbitrate(trigger_seat, responses, cfg, seat_count=4)`` → ``ArbitrationResult``。
TS 的 ``Map<number, ActionType>`` 对应 Python 的 ``dict[int, str]``。
"""

from __future__ import annotations

from dataclasses import replace

from app.core.nanfeng.action.arbiter import ArbitrationResult, arbitrate
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG

cfg = DEFAULT_RULE_CONFIG

NO_MULTI = replace(cfg, claim=replace(cfg.claim, allow_multiple_hu=False))


def resp(*pairs) -> dict[int, str]:
    """TS ``resp(...pairs)``：``new Map(pairs)``。"""
    return dict(pairs)


def winners_of(result) -> list[tuple[int, str]]:
    return [(winner.seat, winner.type) for winner in result.winners]


# ---------------------------------------------------------------------------
# 仲裁优先级（对应 Review Focus #2）
# ---------------------------------------------------------------------------

def test_hu_beats_gang_and_peng_and_takes_all():
    """胡 > 杠 > 碰，且胡通吃（有人胡时碰/杠全部作废）。"""
    result = arbitrate(0, resp((1, 'PENG'), (2, 'MING_GANG'), (3, 'HU')), cfg)
    assert winners_of(result) == [(3, 'HU')]
    assert sorted(result.others) == [1, 2]


def test_ming_gang_beats_peng():
    """明杠压过碰。"""
    result = arbitrate(0, resp((1, 'PENG'), (3, 'MING_GANG')), cfg)
    assert winners_of(result) == [(3, 'MING_GANG')]
    assert list(result.others) == [1]


def test_same_rank_picks_nearest():
    """同级取距出牌者最近者（碰/杠只出一个赢家）。"""
    assert winners_of(arbitrate(0, resp((3, 'PENG'), (1, 'PENG')), cfg)) == [(1, 'PENG')]
    # 3→1 距离 2，3→2 距离 3
    assert winners_of(arbitrate(3, resp((1, 'PENG'), (2, 'PENG')), cfg)) == [(1, 'PENG')]


def test_all_pass_means_no_winner():
    """全员 PASS → 无赢家。"""
    assert winners_of(arbitrate(0, resp((1, 'PASS'), (2, 'PASS')), cfg)) == []


def test_pass_responders_are_not_in_others():
    """PASS 的响应者不进 others（没有碰/杠需要作废）。"""
    result = arbitrate(0, resp((1, 'PENG'), (2, 'PASS')), cfg)
    assert winners_of(result) == [(1, 'PENG')]
    assert list(result.others) == []


def test_unresponsive_players_are_ignored():
    """只影响窗口内已响应的玩家，未响应者不算 PASS 也不参与。"""
    assert winners_of(arbitrate(0, resp((1, 'PENG')), cfg)) == [(1, 'PENG')]


def test_same_input_gives_same_result():
    """同一输入重复调用结果一致（确定性）。"""
    responses = resp((1, 'PENG'), (2, 'PENG'))
    assert arbitrate(0, responses, cfg) == arbitrate(0, responses, cfg)


# ---------------------------------------------------------------------------
# 一炮多响（Q-05）
# ---------------------------------------------------------------------------

def test_multiple_hu_all_count_sorted_by_distance():
    """多家同时胡都算，全部进 winners，且按距离升序（顺序固定）。"""
    result = arbitrate(0, resp((2, 'HU'), (1, 'HU')), cfg)
    assert winners_of(result) == [(1, 'HU'), (2, 'HU')]
    assert list(result.others) == []


def test_three_hu_all_count():
    """三家同时胡也全部算。"""
    result = arbitrate(0, resp((1, 'HU'), (2, 'HU'), (3, 'HU')), cfg)
    assert [winner.seat for winner in result.winners] == [1, 2, 3]


def test_non_hu_claims_voided_when_multiple_hu():
    """多家胡时不相干的碰/杠全部作废并进 others。"""
    result = arbitrate(0, resp((1, 'HU'), (2, 'HU'), (3, 'PENG')), cfg)
    assert winners_of(result) == [(1, 'HU'), (2, 'HU')]
    assert list(result.others) == [3]


def test_two_hu_winners_are_both_reported():
    """单家胡时 others 里的另一家胡（被通吃）也要报出来。"""
    result = arbitrate(0, resp((1, 'HU'), (3, 'HU')), cfg)
    assert [winner.seat for winner in result.winners] == [1, 3]


def test_multiple_hu_can_be_disabled():
    """关掉 allowMultipleHu 时退回"只取最近一家"（开关保留）。"""
    result = arbitrate(0, resp((1, 'HU'), (2, 'HU')), NO_MULTI)
    assert winners_of(result) == [(1, 'HU')]
    assert list(result.others) == [2]


# ---------------------------------------------------------------------------
# 防御性输入
# ---------------------------------------------------------------------------

def test_out_of_window_actions_are_not_winners():
    """窗口外动作（暗杠/补杠/出牌）不会被当成赢家。"""
    result = arbitrate(0, resp((1, 'AN_GANG'), (2, 'PENG')), cfg)
    assert winners_of(result) == [(2, 'PENG')]
    assert list(result.others) == [1]


def test_only_out_of_window_actions_means_no_winner():
    """只有窗口外动作时无赢家。"""
    result = arbitrate(0, resp((1, 'BU_GANG')), cfg)
    assert winners_of(result) == []
    assert list(result.others) == [1]


def test_empty_responses():
    """空响应表 → 无赢家、无 others。"""
    assert arbitrate(0, resp(), cfg) == ArbitrationResult(winners=(), others=())
