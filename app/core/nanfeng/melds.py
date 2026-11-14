"""副露（碰 / 杠）的表示与折算 —— 对应前端 ``assets/scripts/core/melds.ts``。

两种折算必须分开（规则文档 §2.2）：
    - ``meld_set_count``：占几组面子需求 —— 杠算刻，所以三种杠都算 1 组；
    - ``meld_tile_count``：这副露实际占了几张牌 —— 碰 3 张，三种杠各 4 张。

R-07 把「归一折算」与「张数折算」合并了：归一统计的口径是「该牌码的 4 张全归你」，
所以每副露对归一的贡献就是它占的张数，不需要单独的 ``meldGuiYiCount``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.core.nanfeng.tiles import Tile

MeldKind = Literal['PENG', 'MING_GANG', 'AN_GANG', 'BU_GANG']


@dataclass(frozen=True)
class Meld:
    kind: MeldKind
    tile: Tile
    #: 碰 / 明杠的来源座位；暗杠与补杠为 ``None``。
    from_seat: Optional[int] = None


def meld_set_count(meld: Meld) -> int:
    """面子需求折算：杠算刻，一律占 1 组。"""
    return 1


def meld_tile_count(meld: Meld) -> int:
    """张数折算：碰 3 张，明杠/暗杠/补杠各 4 张。"""
    return 3 if meld.kind == 'PENG' else 4
