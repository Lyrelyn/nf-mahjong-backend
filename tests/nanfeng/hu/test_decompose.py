"""``tests/core/hu/decompose.test.ts`` 的 pytest 等价用例。

覆盖两个 describe：
    - 标准型面子分解（is_standard，含纯函数语义与副露抵扣）
    - 碰碰胡单调：胡的那张牌配成将（is_peng_peng_hu / is_peng_peng_hu_dan_diao）
"""

from __future__ import annotations

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.decompose import (
    is_peng_peng_hu,
    is_peng_peng_hu_dan_diao,
    is_standard,
)
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG

CFG = DEFAULT_RULE_CONFIG


# --------------------------------------------------------------------------- #
# describe('标准型面子分解')
# --------------------------------------------------------------------------- #


def test_four_sets_plus_one_pair() -> None:
    """TS: 4 组面子 + 1 将成立。"""
    c = counts_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41])
    assert is_standard(c, 0, CFG) is True


def test_waiting_shape_of_thirteen_tiles_is_not_standard() -> None:
    """TS: 听牌形（13 张）不成立。"""
    c = counts_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41])
    assert is_standard(c, 0, CFG) is False


def test_extra_single_tile_is_not_standard() -> None:
    """TS: 多一个单张不成立。"""
    c = counts_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41, 45])
    assert is_standard(c, 0, CFG) is False


def test_meld_covers_one_set_requirement() -> None:
    """TS: 副露抵扣面子需求（3 组 + 将，外加 1 组碰）。"""
    c = counts_of([11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41])
    melds = [Meld(kind='PENG', tile=51, from_seat=2)]
    assert is_standard(c, len(melds), CFG) is True


def test_only_the_correct_pair_candidate_works() -> None:
    """TS: 将牌有多种选择时，只有正确的那个成立（枚举必须走完全部候选）。

    11/12/13 各两张 + 21 刻 + 31 刻 + 41 对：
    以 11、12、13 为将都拆不出第二组面子，只有以 41 为将时 11-12-13 能连续成两组顺子。
    """
    c = counts_of([11, 11, 12, 12, 13, 13, 21, 21, 21, 31, 31, 31, 41, 41])
    assert is_standard(c, 0, CFG) is True


def test_multiple_pair_candidates_that_all_fail_are_rejected() -> None:
    """TS: 同为多将牌候选但都不成立时判否（把 41 对换成 41 + 42）。"""
    c = counts_of([11, 11, 12, 12, 13, 13, 21, 21, 21, 31, 31, 31, 41, 42])
    assert is_standard(c, 0, CFG) is False


def test_all_triplets_shape_is_standard() -> None:
    """TS: 全刻子（碰碰胡形）成立。"""
    c = counts_of([11, 11, 11, 21, 21, 21, 31, 31, 31, 41, 41, 41, 51, 51])
    assert is_standard(c, 0, CFG) is True


def test_is_standard_does_not_mutate_caller_counts() -> None:
    """TS: 不修改调用方传入的 counts（纯函数语义）。"""
    c = counts_of([11, 12, 13, 11, 12, 13, 21, 22, 23, 31, 31, 31, 41, 41])
    before = bytes(c)
    is_standard(c, 0, CFG)
    assert bytes(c) == before


def test_more_than_four_melds_is_never_standard() -> None:
    """TS: 副露超过 4 组时不成立。"""
    c = counts_of([11, 11])
    assert is_standard(c, 5, CFG) is False


# --------------------------------------------------------------------------- #
# describe('碰碰胡单调：胡的那张牌配成将')
#
# 111 222 333 444 + 55 这个 14 张形，可能来自两种不同的听牌形：
#   来牌前 111 222 333 444 5  → 胡 5 是单钓
#   来牌前 111 222 333 44 55  → 胡 4 是对倒
# 只看成牌分不出两者，所以判定必须知道"胡的是哪张"。
# --------------------------------------------------------------------------- #


def _peng_peng_shape() -> bytearray:
    return counts_of([11, 11, 11, 21, 21, 21, 31, 31, 31, 41, 41, 41, 51, 51])


def test_the_tile_that_completes_the_pair_is_dan_diao() -> None:
    """TS: 胡成将的那张 → 成立。"""
    c = _peng_peng_shape()
    assert is_peng_peng_hu(c, 0) is True
    assert is_peng_peng_hu_dan_diao(c, 0, 51) is True


def test_the_tile_from_a_two_sided_pair_wait_is_not_dan_diao() -> None:
    """TS: 对倒来的那一张 → 不算单调（同一个形，只看胡牌张就能区分）。"""
    assert is_peng_peng_hu_dan_diao(_peng_peng_shape(), 0, 41) is False


def test_dan_diao_after_meld_offset() -> None:
    """TS: 副露抵扣面子需求后同样成立（3 组 + 将，胡 41 单调）。"""
    c = counts_of([11, 11, 11, 21, 21, 21, 31, 31, 31, 41, 41])
    assert is_peng_peng_hu_dan_diao(c, 1, 41) is True


def test_a_hand_with_a_run_is_never_peng_peng_hu() -> None:
    """TS: 不是碰碰胡（含顺子）一律不成立。

    11/12/13 各两张 + 14/15/16 顺子：将牌候选都拆不出全刻子。
    """
    c = counts_of([11, 11, 12, 12, 13, 13, 14, 15, 16, 21, 21, 21, 41, 41])
    assert is_peng_peng_hu(c, 0) is False
    assert is_peng_peng_hu_dan_diao(c, 0, 41) is False


def test_wrong_tile_count_or_win_tile_not_in_hand_is_not_dan_diao() -> None:
    """TS: 张数不对、或手上根本没有那张牌时不成立。"""
    assert is_peng_peng_hu_dan_diao(
        counts_of([11, 11, 11, 21, 21, 21, 31, 31, 31, 41, 41]), 0, 41) is False
    assert is_peng_peng_hu_dan_diao(_peng_peng_shape(), 0, 52) is False


def test_is_peng_peng_hu_dan_diao_does_not_mutate_caller_counts() -> None:
    """TS: 不修改调用方传入的 counts（纯函数语义）。"""
    c = _peng_peng_shape()
    before = bytes(c)
    is_peng_peng_hu_dan_diao(c, 0, 51)
    assert bytes(c) == before
