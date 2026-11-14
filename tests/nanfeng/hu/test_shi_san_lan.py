"""``tests/core/hu/shiSanLan.test.ts`` 的 pytest 等价用例。

覆盖四个 describe：
    - 十三烂（is_shi_san_lan）
    - 七星十三烂（is_qi_xing_shi_san_lan）
    - 字牌张数（R-05 的下限是推论，不是额外约束）
    - 只能自摸的十三烂（R-05，requires_self_draw）
"""

from __future__ import annotations

import pytest

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.shi_san_lan import (
    count_word_tiles,
    is_qi_xing_shi_san_lan,
    is_shi_san_lan,
    requires_self_draw,
)


# --------------------------------------------------------------------------- #
# describe('十三烂')
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ('tiles', 'expected'),
    [
        # TS: 间隔 ≥3 即成立，不限于 1/4/7 类（修正 S-04 的注释错误）
        # {1万,5万,9万} 相邻差 4、4，满足 ≥3，但既不属于 1/4/7 也不属于 2/5/8 或 3/6/9
        ([11, 15, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 51, 52], True),
        # TS: 同花色间隔 <3 不成立
        ([11, 13, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 51, 52], False),
        # TS: 同花色点数重复不成立
        ([11, 11, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 51, 52], False),
        # TS: 字牌重复不成立
        ([11, 15, 19, 21, 25, 29, 31, 35, 39, 41, 41, 43, 51, 52], False),
        # TS: 不同花色的相同点数允许（R-05 已确认）
        ([11, 14, 17, 21, 24, 27, 31, 34, 37, 41, 42, 43, 51, 52], True),
        # TS: 13 张不成立
        ([11, 15, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 51], False),
        # TS: 15 张不成立
        ([11, 15, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 51, 52, 53], False),
    ],
    ids=[
        'gap-four-is-fine',
        'same-suit-gap-below-three',
        'same-suit-duplicate-rank',
        'word-tile-duplicate',
        'same-rank-across-suits-allowed',
        'thirteen-tiles',
        'fifteen-tiles',
    ],
)
def test_is_shi_san_lan(tiles: list[int], expected: bool) -> None:
    assert is_shi_san_lan(counts_of(tiles)) is expected


# --------------------------------------------------------------------------- #
# describe('七星十三烂')
# --------------------------------------------------------------------------- #


def test_all_seven_word_kinds_is_qi_xing() -> None:
    """TS: 字牌七种齐全即为七星。"""
    c = counts_of([11, 15, 21, 25, 31, 35, 39, 41, 42, 43, 44, 51, 52, 53])
    assert is_shi_san_lan(c) is True
    assert is_qi_xing_shi_san_lan(c) is True


def test_six_word_kinds_is_shi_san_lan_but_not_qi_xing() -> None:
    """TS: 字牌只有六种时是十三烂但不算七星（8 张数牌 + 6 种字牌 = 14 张）。"""
    c = counts_of([11, 15, 19, 21, 25, 29, 31, 35, 41, 42, 43, 44, 51, 52])
    assert is_shi_san_lan(c) is True
    assert is_qi_xing_shi_san_lan(c) is False


def test_qi_xing_requires_shi_san_lan_first() -> None:
    """TS: 不成立十三烂时也不会成立七星。"""
    c = counts_of([11, 11, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 44, 51])
    assert is_qi_xing_shi_san_lan(c) is False


# --------------------------------------------------------------------------- #
# describe('字牌张数（R-05）')
#
# R-05 要求"字牌至少 5 张"。这里记录的是：这条下限**不是额外约束，而是推论**。
# 每花色在 1..9 中相邻差 ≥3 最多取 3 张（1/4/7、1/5/9…），故数牌最多 3×3 = 9 张，
# 14 张手牌里字牌必然 ≥ 5 张。所以 is_shi_san_lan 不需要再写一条下限判断。
# --------------------------------------------------------------------------- #


def test_word_count_lower_bound_of_five_cannot_be_violated() -> None:
    """TS: 数牌最多 9 张，故成立的十三烂其字牌数必为 5/6/7 —— 下限 5 无法被违反。

    9 张数牌（每花色已取满 3 张）+ 5 张字牌 = 14 张，字牌数正好是下限；
    想凑到 4 张字牌就得有 10 张数牌，而第 10 张必然把某花色的间隔压到 3 以下。
    """
    min_words = counts_of([11, 14, 17, 21, 24, 27, 31, 34, 37, 41, 42, 43, 51, 52])
    assert count_word_tiles(min_words) == 5
    assert is_shi_san_lan(min_words) is True

    ten_numbers = counts_of([11, 14, 17, 21, 24, 27, 31, 34, 37, 39, 41, 42, 43, 51])
    assert count_word_tiles(ten_numbers) == 4
    assert is_shi_san_lan(ten_numbers) is False


# --------------------------------------------------------------------------- #
# describe('只能自摸的十三烂（R-05）')
# --------------------------------------------------------------------------- #


def test_five_or_six_word_tiles_must_self_draw() -> None:
    """TS: 字牌 5 张、6 张时只能自摸（点炮拒胡）。"""
    assert requires_self_draw(
        counts_of([11, 14, 17, 21, 24, 27, 31, 34, 37, 41, 42, 43, 51, 52])) is True
    assert requires_self_draw(
        counts_of([11, 15, 19, 21, 25, 29, 31, 35, 41, 42, 43, 44, 51, 52])) is True


def test_qi_xing_may_ron() -> None:
    """TS: 七星（字牌 7 张）可以点炮 —— 只是点数从 5 炮降到 3 炮。"""
    assert requires_self_draw(
        counts_of([11, 15, 21, 25, 31, 35, 39, 41, 42, 43, 44, 51, 52, 53])) is False


def test_non_shi_san_lan_hands_have_no_ron_restriction() -> None:
    """TS: 不是十三烂的手牌一律不限制点炮。"""
    assert requires_self_draw(
        counts_of([11, 11, 11, 12, 12, 12, 13, 13, 13, 21, 21, 21, 31, 31])) is False


def test_fewer_than_fourteen_tiles_has_no_ron_restriction() -> None:
    """TS: 张数不足 14（含被副露占用）时不限制点炮。"""
    assert requires_self_draw(
        counts_of([11, 14, 17, 21, 24, 27, 31, 34, 37, 41, 42, 43, 51])) is False
