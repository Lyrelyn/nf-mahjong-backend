"""大厅状态对拍 —— 对应前端 ``tests/core/state/lobby.test.ts``。

大厅 = **还没开局**的那一段时间。它存在的理由：``start_round`` 硬要求恰好 4 个座位
（房主要能在座位表里定位到自己），而「等人到齐」这个阶段座位表**本来就不满**。
``phase`` 里早就有 ``LOBBY``（``LEGAL_ACTIONS['LOBBY'] == ()``，所有动作被拒），
所以大厅不需要新的状态机，只需要一个能装下 < 4 个人的开局状态。
"""

from __future__ import annotations

import inspect

import pytest

from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG
from app.core.nanfeng.state.game_state import start_lobby
from app.core.nanfeng.state.invariants import assert_invariants
from app.core.nanfeng.tiles import WALL_SIZE

CFG = DEFAULT_RULE_CONFIG


class TestLobbyState:
    def test_lobby_can_be_built_before_the_table_is_full(self):
        """TS：人还没到齐也能建（这就是它存在的理由）"""
        for seats in (('a',), ('a', 'b'), ('a', 'b', 'c'), ('a', 'b', 'c', 'd')):
            state = start_lobby(seats, CFG, epoch=1)
            assert state.phase == 'LOBBY'
            assert len(state.hands) == len(seats)
            assert state.seats == tuple(seats)

    def test_no_tile_has_been_dealt_yet(self):
        """TS：**一副牌都没发出去**：136 张全在牌墙里，四家都是空的"""
        state = start_lobby(('a', 'b'), CFG, epoch=1)
        assert len(state.wall) == WALL_SIZE
        assert state.wall_pos == 0
        assert all(hand.drawn_tile is None and len(hand.melds) == 0
                   for hand in state.hands)
        assert state.discards == ((), ())
        assert state.scores == (0, 0)

    def test_lobby_passes_all_invariants(self):
        """TS：通过全部不变量（守恒、逐牌上限、零和）"""
        state = start_lobby(('a', 'b', 'c'), CFG, epoch=1)
        assert_invariants(state, CFG)

    def test_round_is_zero_before_the_first_deal(self):
        """TS：还没有开局，所以局数是 0（面板靠它显示「第几局」）"""
        state = start_lobby(('a', 'b'), CFG, epoch=1)
        assert state.round == 0
        # 大厅里没有任何「上一局的结果」，所以结算面板与换座都无从谈起
        assert state.last_settle is None
        assert state.last_outcome is None

    def test_host_seat_validation_has_no_server_side_counterpart(self):
        """TS：房主不在座位表里 → 直接抛，不静默给个错的 hostSeat

        前端要校验「房主在座位表里」，因为房主兼任裁判。后端把裁判固定在服务端进程
        （见 ``game_state.py`` 模块注释：没有 ``host_id`` / ``host_seat``，也没有房主迁移），
        所以这条用例在 Python 侧的正确等价物是**这个入参根本不存在**，而不是「它会抛错」。
        """
        params = inspect.signature(start_lobby).parameters
        assert 'host_id' not in params
        assert 'host_seat' not in params

    def test_empty_seat_list_raises(self):
        """TS：一个人都没有 → 也抛（没有房主就没有权威）"""
        with pytest.raises(ValueError, match='房主|座位'):
            start_lobby((), CFG, epoch=1)
