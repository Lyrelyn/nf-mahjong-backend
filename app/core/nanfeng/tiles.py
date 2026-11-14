"""南丰麻将牌编码与常量 —— 对应前端 ``assets/scripts/core/tiles.ts``。

编码约定（spec「Global Constraints」）：
    万 11..19 / 条 21..29 / 筒 31..39 / 风 41..44（东南西北）/ 箭 51..53（中发白）

本模块是引擎禁区（spec §3.3）：不 import asyncio / 网络 / 时钟 / 随机。
"""

from __future__ import annotations

from typing import Literal

Tile = int

Suit = Literal['WAN', 'TIAO', 'TONG', 'WIND', 'DRAGON']

#: counts 数组长度：下标即牌码；0..10 与 54.. 不使用。
COUNT_SIZE = 54

#: 整副牌张数（每种 4 张）。
WALL_SIZE = 136


def is_number_tile(tile: Tile) -> bool:
    """数牌：万 11..19、条 21..29、筒 31..39。"""
    return 11 <= tile <= 39 and 1 <= tile % 10 <= 9


def is_wind(tile: Tile) -> bool:
    """风牌：41..44（东南西北）。"""
    return 41 <= tile <= 44


def is_dragon(tile: Tile) -> bool:
    """箭牌：51..53（中发白）。"""
    return 51 <= tile <= 53


def is_word(tile: Tile) -> bool:
    """字牌 = 风牌 或 箭牌。"""
    return is_wind(tile) or is_dragon(tile)


def is_valid_tile(tile: Tile) -> bool:
    """任一有效牌码。"""
    return is_number_tile(tile) or is_word(tile)


def suit_of(tile: Tile) -> Suit:
    """花色。非法牌码抛错，不静默返回。"""
    if is_number_tile(tile):
        tens = tile // 10
        if tens == 1:
            return 'WAN'
        if tens == 2:
            return 'TIAO'
        return 'TONG'
    if is_wind(tile):
        return 'WIND'
    if is_dragon(tile):
        return 'DRAGON'
    raise ValueError(f'非法牌码：{tile}')


def rank_of(tile: Tile) -> int:
    """点数：数牌 1..9；风 1..4；箭 1..3。非法牌码抛错。"""
    if is_number_tile(tile):
        return tile % 10
    if is_wind(tile):
        return tile - 40
    if is_dragon(tile):
        return tile - 50
    raise ValueError(f'非法牌码：{tile}')


def full_wall() -> list[Tile]:
    """整副牌：34 种 × 4 张 = 136 张。顺序固定，洗牌由 ``prng.shuffle_wall`` 负责。"""
    wall: list[Tile] = []
    for base in (10, 20, 30):
        for rank in range(1, 10):
            wall.extend([base + rank] * 4)
    for tile in range(41, 45):
        wall.extend([tile] * 4)
    for tile in range(51, 54):
        wall.extend([tile] * 4)
    return wall
