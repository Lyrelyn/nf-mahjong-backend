"""字牌顺子模式表（南丰特色）—— 对应前端 ``assets/scripts/core/hu/wordStraight.ts``。

3 张**不同**字牌组成一组面子。约束（规则文档 §2.3）：
    - 风牌（东南西北）取 3 有 4 种组合，箭牌（中发白）取 3 有 1 种，共 5 种；
    - 风与箭不可混搭；
    - 每个模式按牌码升序存储 —— 这是 ``decompose`` 剪枝正确性的前提：
      回溯时只从「最小非零牌」开始决策，因此只需要考虑以它为首张的模式。
"""

from __future__ import annotations

from app.core.nanfeng.tiles import Tile, is_dragon, is_wind

WORD_PATTERNS: tuple[tuple[Tile, ...], ...] = (
    (41, 42, 43),  # 东南西
    (41, 42, 44),  # 东南北
    (41, 43, 44),  # 东西北
    (42, 43, 44),  # 南北西
    (51, 52, 53),  # 中发白
)

WIND_TILES: tuple[Tile, ...] = (41, 42, 43, 44)
DRAGON_TILES: tuple[Tile, ...] = (51, 52, 53)
#: 七星十三烂要求的七种字牌。
SEVEN_WORD_TILES: tuple[Tile, ...] = WIND_TILES + DRAGON_TILES

NUMBER_SUIT_BASES: tuple[int, ...] = (10, 20, 30)


def word_patterns_starting_at(tile: Tile) -> tuple[tuple[Tile, ...], ...]:
    """以 ``tile`` 为最小元素的模式（``tile`` 必须是字牌，否则返回空元组）。"""
    if not is_wind(tile) and not is_dragon(tile):
        return ()
    return tuple(pattern for pattern in WORD_PATTERNS if pattern[0] == tile)
