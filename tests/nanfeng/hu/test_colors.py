"""``tests/core/hu/colors.test.ts`` 的 pytest 等价用例。

清一色（全同一数牌花色）与字一色（全字牌，风箭可混）；副露参与判定，空牌一律 False。
"""

from __future__ import annotations

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.colors import is_qing_yi_se, is_zi_yi_se
from app.core.nanfeng.melds import Meld


# --------------------------------------------------------------------------- #
# describe('清一色')
# --------------------------------------------------------------------------- #


def test_concealed_tiles_and_meld_in_the_same_number_suit() -> None:
    """TS: 暗牌 + 副露同属一个数牌花色 → 成立。"""
    melds = [Meld(kind='PENG', tile=17, from_seat=2)]
    assert is_qing_yi_se(counts_of([11, 12, 13, 14, 15, 16]), melds) is True


def test_meld_in_a_different_suit_breaks_qing_yi_se() -> None:
    """TS: 副露与暗牌不同花色 → 不成立。"""
    melds = [Meld(kind='PENG', tile=27, from_seat=2)]
    assert is_qing_yi_se(counts_of([11, 12, 13]), melds) is False


def test_all_word_tiles_is_not_qing_yi_se() -> None:
    """TS: 只有字牌 → 不是清一色（那是字一色）。"""
    assert is_qing_yi_se(counts_of([41, 42, 51]), []) is False


def test_empty_hand_is_not_qing_yi_se() -> None:
    """TS: 空牌不算清一色（不能因为"没有牌"而恒真）。"""
    assert is_qing_yi_se(counts_of([]), []) is False


# --------------------------------------------------------------------------- #
# describe('字一色')
# --------------------------------------------------------------------------- #


def test_all_word_tiles_with_winds_and_dragons_mixed() -> None:
    """TS: 全字牌成立，风与箭可混。"""
    assert is_zi_yi_se(counts_of([41, 42, 51, 52]), []) is True


def test_any_number_tile_breaks_zi_yi_se() -> None:
    """TS: 含数牌不成立。"""
    assert is_zi_yi_se(counts_of([41, 42, 11]), []) is False


def test_number_tile_meld_breaks_zi_yi_se() -> None:
    """TS: 副露是数牌时不成立。"""
    melds = [Meld(kind='PENG', tile=11, from_seat=1)]
    assert is_zi_yi_se(counts_of([41, 42]), melds) is False


def test_all_word_meld_plus_all_word_concealed_tiles() -> None:
    """TS: 副露全字牌且暗牌全字牌 → 成立。"""
    melds = [Meld(kind='AN_GANG', tile=41, from_seat=None)]
    assert is_zi_yi_se(counts_of([51, 52]), melds) is True


def test_empty_hand_is_not_zi_yi_se() -> None:
    """TS: 空牌不算字一色。"""
    assert is_zi_yi_se(counts_of([]), []) is False
