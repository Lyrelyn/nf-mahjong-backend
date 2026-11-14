"""一色型判定 —— 对应前端 ``assets/scripts/core/hu/colors.ts``。

清一色（全同一数牌花色）与字一色（全字牌，风箭可混）。副露参与判定：
暗牌与全部副露牌必须同花色（或全为字牌）。空牌一律返回 False ——
不能让「没有牌」把谓词变成恒真。
"""

from __future__ import annotations

from app.core.nanfeng.counts import Counts
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.tiles import Suit, is_word, suit_of


def _collect_suits(counts: Counts, melds: tuple[Meld, ...] | list[Meld]) -> set[Suit]:
    suits: set[Suit] = set()
    for tile in range(11, len(counts)):
        if counts[tile] > 0:
            suits.add(suit_of(tile))
    for meld in melds:
        suits.add(suit_of(meld.tile))
    return suits


def is_qing_yi_se(counts: Counts, melds: tuple[Meld, ...] | list[Meld]) -> bool:
    """清一色：万 / 条 / 筒 三者之一，且牌数为正。"""
    suits = _collect_suits(counts, melds)
    if len(suits) != 1:
        return False
    only = next(iter(suits))
    return only in ('WAN', 'TIAO', 'TONG')


def is_zi_yi_se(counts: Counts, melds: tuple[Meld, ...] | list[Meld]) -> bool:
    """字一色：全部为字牌（风与箭可混），且牌数为正。"""
    has_tile = False
    for tile in range(11, len(counts)):
        if counts[tile] == 0:
            continue
        has_tile = True
        if not is_word(tile):
            return False
    for meld in melds:
        has_tile = True
        if not is_word(meld.tile):
            return False
    return has_tile
