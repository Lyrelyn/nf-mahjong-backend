"""每局换座对拍 —— ``next_round_seating`` 的四种结果（R-02 / C-9）。

对应前端 ``tests/core/state/apply.test.ts`` 的「每局换座（R-02 五人轮换）」那一组，
以及 ``tests/core/rules-conformance.test.ts`` 的 R-02（同一张表，两边各锁一次）。

    ================  ==================  ==================
    本局结果           下局庄家             下场的人
    ================  ==================  ==================
    庄家胡（含自摸）    庄家连庄             庄家的**对家**
    别人**点炮**胡       **胡牌者**坐庄        **放炮者**
    别人**自摸**胡       **胡牌者**坐庄        自摸者的**对家**
    荒庄               庄家的**对家**        **庄家**
    ================  ==================  ==================
"""

from __future__ import annotations

import pytest

from app.core.nanfeng.state.game_state import (
    RoundOutcome,
    RoundWinner,
    next_round_seating,
    start_round,
)
from tests.nanfeng.fixtures import start_base


def hu_outcome(winners, loser_seat):
    return RoundOutcome(
        kind='HU',
        winners=tuple(RoundWinner(seat=seat, zimo=zimo) for seat, zimo in winners),
        loser_seat=loser_seat,
    )


HUANG_ZHUANG = RoundOutcome(kind='HUANG_ZHUANG')


class TestNextRoundSeating:
    @pytest.mark.parametrize(
        ('dealer', 'outcome', 'expected'),
        [
            # 庄家胡（含自摸）→ 庄家连庄，**对家**下场
            (1, hu_outcome([(1, True)], None), {'dealer': 1, 'sitting_out': 3}),
            # 别人**点炮**胡 → 胡牌者坐庄，**放炮者**下场
            (1, hu_outcome([(2, False)], 0), {'dealer': 2, 'sitting_out': 0}),
            # 别人**自摸**胡 → 胡牌者坐庄，自摸者的**对家**下场
            (1, hu_outcome([(2, True)], None), {'dealer': 2, 'sitting_out': 0}),
            # 荒庄 → 庄家的**对家**坐庄，**庄家**下场
            (1, HUANG_ZHUANG, {'dealer': 3, 'sitting_out': 1}),
        ],
        ids=['dealer-hu', 'ron', 'non-dealer-zimo', 'huang-zhuang'],
    )
    def test_four_outcomes(self, dealer, outcome, expected):
        """TS：庄家胡 → 连庄、对家下场；点炮胡 → 胡牌者坐庄、放炮者下场；流局 → 对家坐庄、庄家下场"""
        state = start_round(start_base(dealer=dealer))
        assert next_round_seating(state, outcome) == expected

    def test_dealer_being_roned_does_not_keep_the_dealership(self):
        """TS：庄家被点炮胡时不再连庄，改由胡牌者坐庄"""
        state = start_round(start_base(dealer=1))
        assert next_round_seating(state, hu_outcome([(3, False)], 1)) == {
            'dealer': 3, 'sitting_out': 1}

    def test_multiple_winners_take_the_first_one_by_distance(self):
        """TS：多家同时胡时取距放炮者最近的那家坐庄"""
        state = start_round(start_base(dealer=3))
        seating = next_round_seating(state, hu_outcome([(1, False), (2, False)], 0))
        assert seating['dealer'] == 1

    def test_non_dealer_zimo_moves_the_dealership_and_sits_out_opposite(self):
        """TS：非庄家自摸：胡牌者坐庄，自摸者的对家下场（R-02 的表漏掉的第三种情形）"""
        state = start_round(start_base(dealer=0))
        # 座位 1 自摸 → 1 坐庄、1 的对家 3 下场
        assert next_round_seating(state, hu_outcome([(1, True)], None)) == {
            'dealer': 1, 'sitting_out': 3}
        # 座位 2 自摸 → 2 坐庄、对家 0（原来的庄家）下场
        assert next_round_seating(state, hu_outcome([(2, True)], None)) == {
            'dealer': 2, 'sitting_out': 0}

    def test_ron_without_a_loser_seat_raises_instead_of_defaulting(self):
        """TS：点炮胡但没给放炮者 → 报错，不静默取默认值"""
        state = start_round(start_base(dealer=1))
        with pytest.raises(ValueError, match='放炮'):
            next_round_seating(state, hu_outcome([(2, False)], None))
