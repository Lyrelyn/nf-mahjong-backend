"""归一系列判定 —— 对应前端 ``assets/scripts/core/hu/guiYi.ts``。

南丰「归一」= 某牌码凑齐 4 张。R-07 确认的口径：该牌码的 **4 张只要全归你**就算 ——
暗牌、碰、明杠、暗杠、补杠一律计入，每副露按它占的张数折算（碰 3、三种杠 4）。
"""

from __future__ import annotations

from app.core.nanfeng.counts import Counts
from app.core.nanfeng.fan_tags import FanTag
from app.core.nanfeng.melds import Meld, meld_tile_count


def count_gui_yi(counts: Counts, melds: tuple[Meld, ...] | list[Meld]) -> int:
    """归一牌码的个数（0..3）。"""
    quads = 0
    for tile in range(11, len(counts)):
        n = counts[tile]
        for meld in melds:
            if meld.tile == tile:
                n += meld_tile_count(meld)
        if n == 4:
            quads += 1
    return quads


def gui_yi_tag(quad_count: int) -> FanTag | None:
    """一个个数对应一个标签；0 个与 4 个（不可能）都不给标签。"""
    if quad_count == 1:
        return 'SI_GUI_YI'
    if quad_count == 2:
        return 'BA_GUI_YI'
    if quad_count == 3:
        return 'SHI_ER_GUI_YI'
    return None
