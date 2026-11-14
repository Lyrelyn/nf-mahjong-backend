"""计数工具 —— 对应前端 ``assets/scripts/core/counts.ts``。

把一组牌折算成「下标即牌码」的计数数组。判胡、归一、牌张守恒都在 counts 上运算，
避免到处传牌数组。用 ``bytearray`` 与 TS 的 ``Uint8Array`` 对齐语义（可拷贝、按下标读写）。
"""

from __future__ import annotations

from app.core.nanfeng.tiles import COUNT_SIZE, Tile

Counts = bytearray


def counts_of(tiles: list[Tile] | tuple[Tile, ...]) -> Counts:
    """统计每种牌的张数，每次返回新数组。"""
    counts = bytearray(COUNT_SIZE)
    for tile in tiles:
        counts[tile] += 1
    return counts


def total_count(counts: Counts) -> int:
    """总张数。"""
    return sum(counts)


def first_non_zero(counts: Counts) -> int:
    """最小非零牌码；全零返回 -1。

    判胡回溯的剪枝基础：每张牌必然属于某个面子，且以它为首张。
    """
    for tile in range(11, len(counts)):
        if counts[tile] > 0:
            return tile
    return -1


def counts_key(counts: Counts) -> str:
    """记忆化用的稳定字符串键（刻意不做位压缩，见 S-05）。"""
    return ''.join(chr(value) for value in counts)
