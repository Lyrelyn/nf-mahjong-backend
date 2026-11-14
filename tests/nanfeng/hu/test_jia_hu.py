"""``tests/core/hu/jiaHu.test.ts`` 的 pytest 等价用例。

假胡（南丰已确认的口径，规则文档 §2.8）：全部牌同属一个花色，或全部为字牌 ——
**不需要构成任何面子/将**。牌张数（14 张）不是这个谓词的职责，由 judge_hu 在整手牌层面检查。
"""

from __future__ import annotations

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.hu.jia_hu import is_jia_hu
from app.core.nanfeng.melds import Meld


def test_same_suit_alone_is_jia_hu_without_any_structure() -> None:
    """TS: 全同一花色即成立，不需要任何面子结构。"""
    assert is_jia_hu(counts_of([11, 11, 12, 14, 15, 17, 17, 19, 19]), []) is True


def test_number_tiles_mixed_with_word_tiles_is_not_jia_hu() -> None:
    """TS: 数牌与字牌混杂不成立。"""
    assert is_jia_hu(counts_of([11, 12, 41]), []) is False


def test_two_number_suits_is_not_jia_hu() -> None:
    """TS: 跨两个数牌花色不成立。"""
    assert is_jia_hu(counts_of([11, 12, 21]), []) is False


def test_melds_take_part_in_the_suit_check() -> None:
    """TS: 副露参与花色判定。"""
    same_suit = [Meld(kind='PENG', tile=19, from_seat=1)]
    other_suit = [Meld(kind='PENG', tile=29, from_seat=1)]
    assert is_jia_hu(counts_of([11, 12]), same_suit) is True
    assert is_jia_hu(counts_of([11, 12]), other_suit) is False


def test_all_word_tiles_with_wind_and_dragon_mixed_is_jia_hu() -> None:
    """TS: 全字牌成立（风箭混搭也算）。"""
    assert is_jia_hu(counts_of([41, 44, 51, 53]), []) is True


def test_empty_hand_is_not_jia_hu() -> None:
    """TS: 空牌不成立。"""
    assert is_jia_hu(counts_of([]), []) is False
