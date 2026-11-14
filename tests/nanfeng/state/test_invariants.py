"""全局不变量对拍 —— 对应前端 ``tests/core/state/invariants.test.ts``。

四条检查（逐牌上限 / 牌张守恒 / 手牌数符合阶段 / 得分零和）。
坏状态一律在**产生它的那一次变换**上炸掉，所以这里的做法是「改坏一份状态，看它报哪一条」。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.nanfeng.action.hand import add_meld, add_tile, create_hand
from app.core.nanfeng.action.options import PlayerAction
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG
from app.core.nanfeng.state.apply import apply_action
from app.core.nanfeng.state.game_state import start_round
from app.core.nanfeng.state.invariants import (
    assert_invariants,
    effective_hand_size,
    physical_hand_size,
)

from tests.nanfeng.fixtures import (
    an_gang_ready,
    bu_gang_ready,
    clone,
    corrupt_state,
    ming_gang_ready,
    play_to_discard,
    start_base,
)

CFG = DEFAULT_RULE_CONFIG


def assert_did_not_raise(state, cfg=CFG):
    """``expect(() => assertInvariants(...)).not.toThrow()`` 的直白写法。"""
    assert_invariants(state, cfg)


# ---------------------------------------------------------------------------
# 两个张数概念
# ---------------------------------------------------------------------------

class TestTwoHandSizeConcepts:
    def test_physical_counts_gang_as_4_structural_as_3_slots(self):
        """TS：物理张数把杠算 4，结构张数把杠算 3 个位"""
        hand = add_meld(
            add_tile(create_hand(), 11),
            Meld(kind='AN_GANG', tile=22, from_seat=None),
        )
        assert physical_hand_size(hand) == 5  # 1 张暗牌 + 4 张杠
        assert effective_hand_size(hand) == 4  # 1 张暗牌 + 一副露（3 个位）


# ---------------------------------------------------------------------------
# 牌张守恒
# ---------------------------------------------------------------------------

class TestTileConservation:
    def test_fresh_round_is_valid(self):
        """TS：开局状态合法，不抛"""
        assert_did_not_raise(start_round(start_base()))

    def test_still_conserved_after_discard_draw_peng_and_gang(self):
        """TS：出牌、摸牌、碰、杠之后都仍然守恒"""
        discarded = apply_action(
            play_to_discard(0), PlayerAction('DISCARD', 0, 11, 1), CFG, 1).state
        assert_did_not_raise(discarded)

        penged = apply_action(
            ming_gang_ready(11, 1, 0), PlayerAction('PENG', 1, 11, 1), CFG, 1).state
        assert_did_not_raise(penged)

        for state in (an_gang_ready(1, 11), ming_gang_ready(11, 1, 0)):
            kind = ('AN_GANG'
                    if state.turn == 1 and state.hands[1].concealed[11] == 4
                    else 'MING_GANG')
            after = apply_action(
                state, PlayerAction(kind, 1, 11, 1), CFG, 1).state
            assert_did_not_raise(after)

    def test_removing_a_tile_from_the_wall_is_caught(self):
        """TS：牌张守恒：从牌墙抽走一张（谁也没拿到）→ 报错"""
        broken = clone(start_round(start_base()))
        broken = replace(broken, wall=broken.wall[1:])
        with pytest.raises(ValueError, match='牌张守恒'):
            assert_invariants(broken, CFG)

    def test_stuffing_a_tile_into_discards_hits_the_four_copy_check_first(self):
        """TS：往牌河凭空多塞一张会先被「超过 4 张」拦住（两条检查的顺序是有意的）"""
        broken = clone(start_round(start_base()))
        broken = replace(broken, discards=((11,), (), (), ()))
        with pytest.raises(ValueError, match='超过 4 张'):
            assert_invariants(broken, CFG)


# ---------------------------------------------------------------------------
# 每种牌不得超过 4 张
# ---------------------------------------------------------------------------

class TestFourCopyCap:
    def test_adding_a_fifth_copy_in_hand_is_caught(self):
        """TS：手里已经 4 张再添一张 → 超过 4 张报错"""
        state = an_gang_ready(1, 11)  # 座位 1 手里正好 4 张 11
        broken = clone(state)
        hand = broken.hands[1]
        concealed = bytearray(hand.concealed)
        concealed[11] += 1
        hands = list(broken.hands)
        hands[1] = replace(hand, concealed=concealed)
        broken = replace(broken, hands=tuple(hands))
        with pytest.raises(ValueError, match='超过 4 张'):
            assert_invariants(broken, CFG)

    def test_fresh_round_has_exactly_four_of_each_tile(self):
        """TS：开局状态里每种牌恰好 4 张（分布正确）"""
        state = start_round(start_base())
        tally: dict[int, int] = {}
        for index in range(state.wall_pos, len(state.wall)):
            tile = state.wall[index]
            tally[tile] = tally.get(tile, 0) + 1
        for hand in state.hands:
            for tile in range(len(hand.concealed)):
                if hand.concealed[tile]:
                    tally[tile] = tally.get(tile, 0) + hand.concealed[tile]
            if hand.drawn_tile is not None:
                tally[hand.drawn_tile] = tally.get(hand.drawn_tile, 0) + 1
        assert len(tally) == 34
        for tile, n in tally.items():
            assert n == 4, f'牌码 {tile}'


# ---------------------------------------------------------------------------
# 手牌数符合阶段
# ---------------------------------------------------------------------------

class TestHandSizeByPhase:
    def test_waiting_play_discarder_has_14_others_13(self):
        """TS：WAITING_PLAY：出牌那家 14 张、其余 13 张"""
        state = start_round(start_base())
        assert_did_not_raise(state)

        # 把座位 2 的一张牌挪给座位 3：守恒仍然成立，只有手牌数不对
        broken = clone(state)
        hands = list(broken.hands)
        moved = next(tile for tile, n in enumerate(hands[2].concealed) if n > 0)
        source = bytearray(hands[2].concealed)
        source[moved] -= 1
        target = bytearray(hands[3].concealed)
        target[moved] += 1
        hands[2] = replace(hands[2], concealed=source)
        hands[3] = replace(hands[3], concealed=target)
        broken = replace(broken, hands=tuple(hands))
        with pytest.raises(ValueError, match='手牌数'):
            assert_invariants(broken, CFG)

    def test_claim_window_has_13_for_everyone_including_qiang_gang(self):
        """TS：CLAIM_WINDOW：四家都是 13 张（含抢杠窗口）"""
        assert_did_not_raise(ming_gang_ready(11, 1, 0))

        bu_gang = apply_action(
            bu_gang_ready(1, 11, 2), PlayerAction('BU_GANG', 1, 11, 1), CFG, 1).state
        assert bu_gang.phase == 'CLAIM_WINDOW'
        assert_did_not_raise(bu_gang)

    def test_after_gang_replacement_14_structural_15_physical(self):
        """TS：杠后补一张仍然是 14 张（结构上），物理上则是 15 张"""
        state = an_gang_ready(1, 11)
        after = apply_action(
            state, PlayerAction('AN_GANG', 1, 11, 1), CFG, 1).state
        assert effective_hand_size(after.hands[1]) == 14
        assert physical_hand_size(after.hands[1]) == 15
        assert_did_not_raise(after)

    def test_moving_a_tile_away_from_the_discarder_is_caught(self):
        """TS：把出牌那家的一张牌挪给别家 → 两家张数都不对"""
        state = start_round(start_base())
        broken = clone(state)
        hands = list(broken.hands)
        moved = next(
            tile for tile, n in enumerate(hands[broken.turn].concealed) if n > 0)
        other = (broken.turn + 1) % len(hands)
        source = bytearray(hands[broken.turn].concealed)
        source[moved] -= 1
        target = bytearray(hands[other].concealed)
        target[moved] += 1
        hands[broken.turn] = replace(hands[broken.turn], concealed=source)
        hands[other] = replace(hands[other], concealed=target)
        broken = replace(broken, hands=tuple(hands))
        with pytest.raises(ValueError, match='手牌数'):
            assert_invariants(broken, CFG)


# ---------------------------------------------------------------------------
# 得分零和
# ---------------------------------------------------------------------------

class TestZeroSumScore:
    def test_zero_sum_after_gang_score_is_credited(self):
        """TS：杠分入账后仍然零和"""
        state = ming_gang_ready(11, 1, 0)
        after = apply_action(
            state, PlayerAction('MING_GANG', 1, 11, 1), CFG, 1).state
        assert_did_not_raise(after)

    def test_tampered_score_is_caught(self):
        """TS：分数被人为改坏 → 得分不为零报错"""
        broken = clone(start_round(start_base()))
        broken = replace(broken, round_gang_score=(5, 0, 0, 0))
        with pytest.raises(ValueError, match='得分不为零'):
            assert_invariants(broken, CFG)


# ---------------------------------------------------------------------------
# applyAction 前后各断言一次
# ---------------------------------------------------------------------------

class TestApplyAssertsBothSides:
    def test_corrupt_input_state_is_rejected_before_the_transition(self):
        """TS：喂进来的坏状态在变换前就被挡住"""
        with pytest.raises(ValueError, match='牌张守恒'):
            apply_action(
                corrupt_state(), PlayerAction('DISCARD', 0, 11, 1), CFG, 1)

    def test_valid_state_runs_through_without_false_positive(self):
        """TS：合法状态照常跑完，不误报"""
        after = apply_action(
            play_to_discard(0), PlayerAction('DISCARD', 0, 11, 1), CFG, 1).state
        assert after.phase == 'WAITING_PLAY'
        assert_did_not_raise(after)

    def test_a_different_cfg_does_not_change_the_assertions(self):
        """TS：换成与牌局不同的 cfg 也不影响断言（四条检查都与配置无关）"""
        state = start_round(start_base())
        other = replace(CFG, score=replace(CFG.score, cap=99))
        assert_did_not_raise(state, other)
