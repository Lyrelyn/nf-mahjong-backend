"""``apply_action`` 状态机对拍 —— 对应前端 ``tests/core/state/apply.test.ts``。

逐条翻译：每个 pytest 用例的 docstring 都写着它在 TS 里的原题名，方便一对一核对。
差异只有两类（都是 Python 侧的既有约定，不是行为差异）：

    * TS 的 spread 更新 → ``dataclasses.replace``；
    * TS 的 ``Error`` / ``RangeError`` → ``ValueError``。
"""

from __future__ import annotations

import pytest

from app.core.nanfeng.action.hand import hand_tile_count
from app.core.nanfeng.action.options import PlayerAction
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.prng import create_rng, shuffle_wall
from app.core.nanfeng.state.apply import apply_action
from app.core.nanfeng.state.game_state import RoundOutcome, start_round
from app.core.nanfeng.state.phase import LEGAL_ACTIONS
from app.core.nanfeng.tiles import full_wall
from tests.nanfeng.fixtures import (
    CraftedHandSpec,
    an_gang_ready,
    bu_gang_ready,
    clone,
    crafted_round,
    ming_gang_ready,
    play_to_discard,
    ron_ready,
    start_base,
    with_wall_almost_empty,
    zimo_ready,
)

CFG = start_base().cfg


def hu_event_of(events):
    """``events.find(e => e.type === 'HU')``（事件是 dataclass，不是 union）。"""
    return next(event for event in events if event.type == 'HU')


def settle_event_of(events):
    return next(event for event in events if event.type == 'SETTLE')


# ---------------------------------------------------------------------------
# 洗牌与发牌
# ---------------------------------------------------------------------------

class TestShuffleAndDeal:
    def test_same_seed_same_wall_replayable_and_different_seed_differs(self):
        """TS：相同种子产生相同牌墙（可重放），不同种子不同"""
        a = shuffle_wall(full_wall(), create_rng(42))
        b = shuffle_wall(full_wall(), create_rng(42))
        assert a == b
        assert shuffle_wall(full_wall(), create_rng(43)) != a
        assert len(a) == 136
        assert len(set(a)) == 34  # 万条筒各 9 + 风 4 + 箭 3

    def test_deal_sizes_dealer_14_others_13_wall_left_83(self):
        """TS：开局发牌：庄家 14 张，其余 13 张，牌墙剩余 83 张"""
        state = start_round(start_base())
        assert hand_tile_count(state.hands[0]) == 14
        assert hand_tile_count(state.hands[1]) == 13
        assert len(state.wall) == 136 - 53
        assert state.wall_pos == 0
        assert state.phase == 'WAITING_PLAY'
        assert state.turn == 0
        assert state.dealer == 0
        assert state.round_gang_score == (0, 0, 0, 0)
        assert state.seq == 0


# ---------------------------------------------------------------------------
# 出牌与摸牌
# ---------------------------------------------------------------------------

class TestDiscardAndDraw:
    def test_discard_unclaimed_next_seat_draws(self):
        """TS：出牌 → 无人可响应 → 下家摸牌"""
        state = play_to_discard(0)
        result = apply_action(
            state, PlayerAction('DISCARD', 0, 11, 1), CFG, 1000)
        after = result.state
        assert after.phase == 'WAITING_PLAY'
        assert after.turn == 1
        assert after.claim is None
        assert after.discards[0] == (11,)
        assert after.hands[0].drawn_tile is None
        assert after.hands[1].drawn_tile is not None

    def test_seq_increments_once_per_client_action_and_actionlog_appends(self):
        """TS：seq 每次客户端动作 +1，actionLog 按发生顺序追加（摸牌是同一 seq 的后续）"""
        state = play_to_discard(0)
        seq0 = state.seq
        after = apply_action(
            state, PlayerAction('DISCARD', 0, 11, 1), CFG, 1).state
        assert after.seq == seq0 + 1
        assert [entry['type'] for entry in after.action_log] == ['DISCARD', 'DRAW']
        assert after.action_log[0]['seq'] == seq0 + 1
        assert after.action_log[1]['seq'] == seq0 + 1

    def test_empty_wall_draw_settles_as_huang_zhuang(self):
        """TS：摸空牌墙 → 荒庄，绝不死循环（Review Focus #1）"""
        state = with_wall_almost_empty(play_to_discard(0))
        result = apply_action(
            state, PlayerAction('DISCARD', 0, 11, 1), CFG, 1000)
        assert result.state.phase == 'SETTLING'
        assert any(event.type == 'HUANG_ZHUANG' for event in result.events)

    def test_illegal_action_rejected_without_touching_state(self):
        """TS：拒绝非法动作且不改状态"""
        state = start_round(start_base())
        before = clone(state)
        with pytest.raises(ValueError, match='不是你的回合'):
            apply_action(state, PlayerAction('DISCARD', 1, 11, 1), CFG, 1)
        with pytest.raises(ValueError):
            apply_action(state, PlayerAction('PENG', 1, 11, 1), CFG, 1)
        assert state == before

    def test_discarding_a_tile_not_in_hand_raises(self):
        """TS：打出手里没有的牌要报错"""
        state = play_to_discard(0)
        with pytest.raises(ValueError, match='没有'):
            apply_action(state, PlayerAction('DISCARD', 0, 19, 1), CFG, 1)


# ---------------------------------------------------------------------------
# 合法动作表
# ---------------------------------------------------------------------------

class TestLegalActions:
    def test_legal_actions_by_phase(self):
        """TS：按阶段给答案：WAITING_PLAY 能出牌/暗杠/补杠/自摸，CLAIM_WINDOW 能碰杠胡过"""
        waiting = LEGAL_ACTIONS['WAITING_PLAY']
        assert 'DISCARD' in waiting
        assert 'AN_GANG' in waiting
        assert 'BU_GANG' in waiting
        assert 'PENG' not in waiting
        assert LEGAL_ACTIONS['CLAIM_WINDOW'] == ('PENG', 'MING_GANG', 'HU', 'PASS')
        assert LEGAL_ACTIONS['SETTLING'] == ()
        assert LEGAL_ACTIONS['ENDED'] == ()


# ---------------------------------------------------------------------------
# 鸣牌窗口：碰与明杠
# ---------------------------------------------------------------------------

class TestClaimWindow:
    def test_peng_takes_three_tiles_removes_discard_and_grants_turn(self):
        """TS：碰：副露 3 张、牌河里的那张被拿走、出牌权转到碰的人"""
        state = ming_gang_ready(11, 1, 0)
        assert state.phase == 'CLAIM_WINDOW'
        assert state.claim.pending == (1,)

        after = apply_action(
            state, PlayerAction('PENG', 1, 11, 1), CFG, 1).state
        assert after.phase == 'WAITING_PLAY'
        assert after.turn == 1
        assert after.claim is None
        assert after.hands[1].melds == (Meld(kind='PENG', tile=11, from_seat=0),)
        assert after.hands[1].just_peng is True
        assert after.discards[0] == ()
        assert after.last_discard is None

    def test_ming_gang_draws_a_replacement_and_flags_gang_shang(self):
        """TS：明杠后补一张，杠上开花标记生效"""
        state = ming_gang_ready(11, 1, 0)
        after = apply_action(
            state, PlayerAction('MING_GANG', 1, 11, 1), CFG, 1).state
        assert after.phase == 'WAITING_PLAY'
        assert after.turn == 1
        assert after.hands[1].drawn_tile is not None
        assert after.drawn_from_gang is True
        assert after.hands[1].melds[0].kind == 'MING_GANG'

    def test_actions_not_offered_in_window_are_rejected(self):
        """TS：窗口内不能被提供没提供的操作（手里没有 11 就不能碰）"""
        state = ron_ready(11, [1], 0)
        with pytest.raises(ValueError, match='不能执行'):
            apply_action(state, PlayerAction('PENG', 1, 11, 1), CFG, 1)
        with pytest.raises(ValueError):
            apply_action(state, PlayerAction('DISCARD', 1, 12, 1), CFG, 1)

    def test_everyone_passes_discard_stays_next_seat_draws(self):
        """TS：全员不要 → 出牌留在牌河，下家摸牌"""
        state = ming_gang_ready(11, 1, 0)
        after = apply_action(
            state, PlayerAction('PASS', 1, None, 1), CFG, 1).state
        assert after.phase == 'WAITING_PLAY'
        assert after.turn == 1
        assert after.discards[0] == (11,)


# ---------------------------------------------------------------------------
# 胡牌（胜负与事件）
# ---------------------------------------------------------------------------

class TestHu:
    def test_zimo_settles_with_zimo_flag(self):
        """TS：自摸：进 SETTLING，事件 zimo=true"""
        state = zimo_ready(1)
        result = apply_action(
            state, PlayerAction('HU', 1, None, 1), CFG, 1)
        assert result.state.phase == 'SETTLING'
        hu = hu_event_of(result.events)
        assert len(hu.winners) == 1
        winner = hu.winners[0]
        assert (winner.seat, winner.zimo, winner.gang_shang) == (1, True, False)
        assert hu.loser_seat is None
        assert 'PING_HU' in winner.tags

    def test_ron_settles_with_loser_seat(self):
        """TS：点炮：胡的那家进 SETTLING，事件带放炮者"""
        state = ron_ready(11, [1], 0)
        result = apply_action(
            state, PlayerAction('HU', 1, 11, 1), CFG, 1)
        assert result.state.phase == 'SETTLING'
        hu = hu_event_of(result.events)
        assert [winner.seat for winner in hu.winners] == [1]
        assert (hu.winners[0].zimo, hu.winners[0].qiang_gang) == (False, False)
        assert hu.loser_seat == 0

    def test_multiple_hu_by_distance_ascending(self):
        """TS：一炮多响：两家同时胡都算，按距离升序（Q-05）"""
        state = ron_ready(11, [1, 2], 0)
        assert state.claim.pending == (1, 2)

        opened = apply_action(
            state, PlayerAction('HU', 2, 11, 1), CFG, 1).state
        assert opened.phase == 'CLAIM_WINDOW'  # 还有一家没响应

        result = apply_action(
            opened, PlayerAction('HU', 1, 11, 2), CFG, 2)
        assert result.state.phase == 'SETTLING'
        hu = hu_event_of(result.events)
        assert [winner.seat for winner in hu.winners] == [1, 2]


# ---------------------------------------------------------------------------
# 杠分即时入账（Q-02）
# ---------------------------------------------------------------------------

class TestGangScoreCreditedImmediately:
    def test_an_gang_plus_six_others_minus_two_zero_sum(self):
        """TS：暗杠：开杠者 +6，其余三家各 -2，自身零和"""
        state = an_gang_ready(1, 11)
        after = apply_action(
            state, PlayerAction('AN_GANG', 1, 11, 1), CFG, 1).state
        assert after.round_gang_score[1] == 6
        assert after.round_gang_score[0] == -2
        assert after.round_gang_score[2] == -2
        assert after.round_gang_score[3] == -2
        assert sum(after.round_gang_score) == 0
        assert after.hands[1].melds[0] == Meld(
            kind='AN_GANG', tile=11, from_seat=None)
        assert after.drawn_from_gang is True

    def test_ming_gang_paid_only_by_the_discarder(self):
        """TS：直杠：只由点杠者单付 2，其余两家不扣"""
        state = ming_gang_ready(11, 1, 0)
        after = apply_action(
            state, PlayerAction('MING_GANG', 1, 11, 1), CFG, 1).state
        assert after.round_gang_score == (-2, 2, 0, 0)
        assert after.discards[0] == ()  # 这张牌进了副露，不再算牌河

    def test_bu_gang_waits_for_the_qiang_gang_window(self):
        """TS：补杠：+3 必须等抢杠窗口关闭才入账"""
        state = bu_gang_ready(1, 11, 2)  # 座位 2 能抢杠
        after = apply_action(
            state, PlayerAction('BU_GANG', 1, 11, 1), CFG, 1).state
        assert after.phase == 'CLAIM_WINDOW'
        assert after.claim.gang_seat == 1
        assert after.round_gang_score[1] == 0  # 尚未入账
        assert after.hands[1].melds[0].kind == 'BU_GANG'

        passed = apply_action(
            after, PlayerAction('PASS', 2, None, 2), CFG, 2).state
        assert passed.phase == 'WAITING_PLAY'
        assert passed.turn == 1
        assert passed.round_gang_score == (-1, 3, -1, -1)
        # 补杠也要补一张：杠吃掉一张手牌，不补就少一张
        assert passed.hands[1].drawn_tile is not None
        assert passed.drawn_from_gang is True

    def test_bu_gang_credited_immediately_when_nobody_can_rob(self):
        """TS：没人能抢杠时补杠立即入账，并补一张"""
        state = bu_gang_ready(1, 11, None)
        after = apply_action(
            state, PlayerAction('BU_GANG', 1, 11, 1), CFG, 1).state
        assert after.phase == 'WAITING_PLAY'
        assert after.turn == 1
        assert after.round_gang_score == (-1, 3, -1, -1)
        assert after.hands[1].drawn_tile is not None
        assert after.drawn_from_gang is True

    def test_bu_gang_robbed_credits_nothing_and_emits_qiang_gang_hu(self):
        """TS：补杠被抢 → 本次一分不计，出抢杠胡事件"""
        state = bu_gang_ready(1, 11, 2)
        opened = apply_action(
            state, PlayerAction('BU_GANG', 1, 11, 1), CFG, 1).state
        result = apply_action(
            opened, PlayerAction('HU', 2, 11, 2), CFG, 2)

        assert result.state.phase == 'SETTLING'
        assert result.state.round_gang_score[1] == 0  # 被抢 → 不计
        event = next(
            event for event in result.events if event.type == 'QIANG_GANG_HU')
        assert event.gang_seat == 1
        assert [winner.seat for winner in event.winners] == [2]
        assert 'QIANG_GANG_HU' in event.winners[0].tags

    def test_bu_gang_needs_a_peng_and_an_gang_needs_the_turn(self):
        """TS：不能补杠没碰过的牌，也不能越权暗杠"""
        state = an_gang_ready(1, 11)
        with pytest.raises(ValueError):
            apply_action(state, PlayerAction('AN_GANG', 2, 11, 1), CFG, 1)
        with pytest.raises(ValueError, match='不能补杠'):
            apply_action(state, PlayerAction('BU_GANG', 1, 11, 1), CFG, 1)


# ---------------------------------------------------------------------------
# 碰碰胡单调：标签由「胡的是哪张」决定（2026-10-06 改规）
# ---------------------------------------------------------------------------

class TestPengPengHuDanDiao:
    def test_zimo_single_wait_scores_dan_diao_eight_fan(self):
        """TS：自摸单钓将 → 打 PENG_PENG_HU_DAN_DIAO，8 炮（正好等于封顶）"""
        # 来牌前 111 222 333 444 + 5，胡 5 是把将配成对
        state = crafted_round(
            hands=[
                CraftedHandSpec(
                    concealed=[11, 11, 11, 21, 21, 21, 31, 31, 31,
                               41, 41, 41, 51],
                    drawn_tile=51,
                ),
                None,
                None,
                None,
            ],
            turn=0,
            dealer=0,
        )
        result = apply_action(
            state, PlayerAction('HU', 0, None, 1), CFG, 1)
        assert 'PENG_PENG_HU_DAN_DIAO' in hu_event_of(result.events).winners[0].tags
        assert list(settle_event_of(result.events).deltas) == [24, -8, -8, -8]

    def test_two_pair_wait_on_the_same_14_tile_shape_is_plain_peng_peng_hu(self):
        """TS：对倒胡出同一个 14 张形 → 只有普通碰碰胡，4 炮"""
        # 来牌前 111 222 333 44 55，胡 4 是等对倒。成牌形与上一例完全相同，只有来牌不同。
        state = crafted_round(
            hands=[
                CraftedHandSpec(
                    concealed=[11, 11, 11, 21, 21, 21, 31, 31, 31,
                               41, 41, 51, 51],
                    drawn_tile=41,
                ),
                None,
                None,
                None,
            ],
            turn=0,
            dealer=0,
        )
        result = apply_action(
            state, PlayerAction('HU', 0, None, 1), CFG, 1)
        tags = hu_event_of(result.events).winners[0].tags
        assert 'PENG_PENG_HU' in tags
        assert 'PENG_PENG_HU_DAN_DIAO' not in tags
        assert list(settle_event_of(result.events).deltas) == [12, -4, -4, -4]

    def test_ron_single_wait_is_tagged_too(self):
        """TS：点炮单钓同样打标签（不是只有自摸才算）"""
        state = crafted_round(
            hands=[
                # 座 0 手里 13 张杂牌 + 刚摸到的 51，打出去给座 1 胡
                CraftedHandSpec(
                    concealed=[12, 13, 14, 15, 16, 17, 18, 19,
                               22, 23, 24, 25, 26],
                    drawn_tile=51,
                ),
                # 来牌前 111 222 333 444 + 5
                CraftedHandSpec(
                    concealed=[11, 11, 11, 21, 21, 21, 31, 31, 31,
                               41, 41, 41, 51]),
                # 另外两家给「看起来像听牌、其实胡不了 51」的杂牌，且完全不与上面两家撞牌
                CraftedHandSpec(
                    concealed=[32, 32, 32, 33, 33, 33, 34, 34, 34,
                               42, 42, 42, 43]),
                CraftedHandSpec(
                    concealed=[35, 35, 35, 36, 36, 36, 37, 37, 37,
                               44, 44, 44, 53]),
            ],
            turn=0,
            dealer=0,
        )
        discarded = apply_action(
            state, PlayerAction('DISCARD', 0, 51, 1), CFG, 1).state
        result = apply_action(
            discarded, PlayerAction('HU', 1, 51, 2), CFG, 2)
        winner = hu_event_of(result.events).winners[0]
        assert winner.seat == 1
        assert winner.zimo is False
        assert 'PENG_PENG_HU_DAN_DIAO' in winner.tags
        assert list(settle_event_of(result.events).deltas) == [-8, 8, 0, 0]


# ---------------------------------------------------------------------------
# 单局结算落进状态（结算面板的数据来源）
# ---------------------------------------------------------------------------

class TestSettleLandsInState:
    def test_fresh_round_has_no_settlement(self):
        """TS：开局没有结算"""
        state = start_round(start_base())
        assert state.last_settle is None
        assert state.last_outcome is None

    def test_zimo_last_settle_matches_settle_event_and_is_zero_sum(self):
        """TS：自摸胡：lastSettle 与 SETTLE 事件一致，deltas 零和，detail 带得出番型"""
        result = apply_action(
            zimo_ready(1), PlayerAction('HU', 1, None, 1), CFG, 1)
        state = result.state
        settle = settle_event_of(result.events)

        assert state.last_settle is not None
        assert state.last_settle['deltas'] == list(settle.deltas)
        assert state.last_settle['detail'] == list(settle.detail)
        assert sum(state.last_settle['deltas']) == 0

        line = state.last_settle['detail'][0]
        assert line.seat == 1
        assert line.zimo is True
        assert 'PING_HU' in line.tags
        assert line.income == line.unit * 3  # 自摸：三家各付一份

    def test_huang_zhuang_also_lands_with_empty_detail(self):
        """TS：荒庄也落进状态，且 detail 为空（面板要能显示「庄家赔三家」这种没有番型的局）"""
        state = with_wall_almost_empty(play_to_discard(0))
        result = apply_action(
            state, PlayerAction('DISCARD', 0, 11, 1), CFG, 1000)
        settle = settle_event_of(result.events)

        assert result.state.phase == 'SETTLING'
        assert result.state.last_settle is not None
        assert result.state.last_settle['deltas'] == list(settle.deltas)
        assert result.state.last_settle['detail'] == []
        assert sum(result.state.last_settle['deltas']) == 0
        assert result.state.last_outcome == RoundOutcome(kind='HUANG_ZHUANG')

    def test_ron_outcome_keeps_the_loser_seat(self):
        """TS：点炮胡：结果里带着放炮者（账目里没有这个信息）"""
        state = apply_action(
            ron_ready(11, [1], 0), PlayerAction('HU', 1, 11, 1), CFG, 1).state
        outcome = state.last_outcome
        assert outcome.kind == 'HU'
        assert outcome.loser_seat == 0
        assert [winner.seat for winner in outcome.winners] == [1]
        assert outcome.winners[0].zimo is False
        # 账目那一侧确实没有放炮者这个字段
        assert sorted(state.last_settle.keys()) == ['deltas', 'detail']

    def test_outcome_is_a_copy_of_the_event_payload(self):
        """TS：胜负结果是一份**拷贝**：改它不会改到事件里那份"""
        result = apply_action(
            ron_ready(11, [1], 0), PlayerAction('HU', 1, 11, 1), CFG, 1)
        from_event = hu_event_of(result.events)
        outcome = result.state.last_outcome
        assert outcome.kind == 'HU'

        # TS 靠「往拷贝里 push 一个标签，再看事件那份有没有跟着变」验拷贝语义。
        # Python 里 RoundWinner 是 frozen dataclass、tags 是 tuple，改不了；等价断言是两条：
        #   1) 状态里那份是**另一个对象**（clone_outcome 重建了 winners 与每个 RoundWinner）；
        #   2) 尝试追加标签会直接失败 —— 结构上就不可能被外部改动。
        assert outcome.winners is not from_event.winners
        assert outcome.winners[0] is not from_event.winners[0]
        assert outcome.winners[0].tags == from_event.winners[0].tags
        assert 'PENG_PENG_HU' not in from_event.winners[0].tags
        with pytest.raises(AttributeError):
            outcome.winners[0].tags.append('PENG_PENG_HU')
