"""十三烂 / 七星十三烂判定 —— 对应前端 ``assets/scripts/core/hu/shiSanLan.ts``。

口径（规则文档 §2.6，S-04 修正后；R-05 已与牌友确认）：
    - 必须门清（无副露），14 张 —— 门清由调用方 ``judge_hu`` 检查；
    - 数牌：同花色内点数不重复，且排序后**相邻差 >= 3**（「1 和 4 这样就行」）；
      注意不是「只能落在 1/4/7、2/5/8、3/6/9」——{1,5,9} 相邻差 4、4 也成立；
    - 字牌：互不重复；
    - **字牌至少 5 张**：每花色在 1..9 中相邻差 >=3 最多取 3 张，数牌最多 9 张，
      14 张手牌里字牌必然 >= 5 张，所以这条不需要单独判断；
    - 七星十三烂：十三烂 且 东南西北中发白 七种字牌各恰好一张。

R-05 另定了一条**胡牌方式**限制：字牌 5 或 6 张的十三烂只能自摸，点炮不许胡；
7 张（七星）可以点炮，但炮数下降。谓词是 ``requires_self_draw``。
"""

from __future__ import annotations

from app.core.nanfeng.counts import Counts, total_count
from app.core.nanfeng.hu.word_straight import (
    NUMBER_SUIT_BASES,
    SEVEN_WORD_TILES,
)


def is_shi_san_lan(counts: Counts) -> bool:
    if total_count(counts) != 14:
        return False

    for base in NUMBER_SUIT_BASES:
        prev_rank = 0
        for rank in range(1, 10):
            n = counts[base + rank]
            if n == 0:
                continue
            if n > 1:
                return False  # 同花色点数重复
            if prev_rank != 0 and rank - prev_rank < 3:
                return False  # 相邻差 < 3
            prev_rank = rank

    for tile in SEVEN_WORD_TILES:
        if counts[tile] > 1:
            return False

    return True


def is_qi_xing_shi_san_lan(counts: Counts) -> bool:
    if not is_shi_san_lan(counts):
        return False
    for tile in SEVEN_WORD_TILES:
        if counts[tile] != 1:
            return False
    return True


def count_word_tiles(counts: Counts) -> int:
    """字牌张数（东南西北 + 中发白），十三烂的「几星」看的就是它。"""
    return sum(counts[tile] for tile in SEVEN_WORD_TILES)


def requires_self_draw(counts: Counts) -> bool:
    """这手牌是否**只能自摸**（R-05）。

    十三烂且字牌 5 或 6 张 → True，点炮路径必须直接拒胡；
    七星（7 张字牌）与其它所有牌型 → False，自摸点炮都能胡。

    副露的牌不在 counts 里，所以有副露时 ``total_count < 14`` → ``is_shi_san_lan`` 为 False
    → 返回 False，与「十三烂必须门清」一致。
    """
    if not is_shi_san_lan(counts):
        return False
    return count_word_tiles(counts) < 7
