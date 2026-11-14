"""标准型判胡 —— 对应前端 ``assets/scripts/core/hu/decompose.ts``。

算法（规则文档 §2.4）：枚举将牌 → 扣掉 → 对剩余牌做面子分解。
分解用「只从最小非零牌开始决策」的标准剪枝，保证不重不漏；
记忆化用 ``counts_key`` 字符串（**不做位压缩**，见 S-05）。
"""

from __future__ import annotations

from app.core.nanfeng.counts import Counts, counts_key, first_non_zero, total_count
from app.core.nanfeng.hu.word_straight import word_patterns_starting_at
from app.core.nanfeng.rule_config import RuleConfig
from app.core.nanfeng.tiles import Tile, is_number_tile, is_word, rank_of


def _all_zero(counts: Counts) -> bool:
    for tile in range(11, len(counts)):
        if counts[tile] > 0:
            return False
    return True


def decompose(counts: Counts, sets_left: int, cfg: RuleConfig) -> bool:
    """能否用 ``counts`` 里的牌凑出 ``sets_left`` 组面子。不改动调用方的 counts。"""
    return _search(bytearray(counts), sets_left, cfg, set())


def _search(counts: Counts, sets_left: int, cfg: RuleConfig, failed: set[str]) -> bool:
    if sets_left == 0:
        return _all_zero(counts)

    key = f'{sets_left}:{counts_key(counts)}'
    if key in failed:
        return False

    tile = first_non_zero(counts)
    if tile == -1:
        failed.add(key)
        return False

    # (a) 刻子
    if counts[tile] >= 3:
        counts[tile] -= 3
        ok = _search(counts, sets_left - 1, cfg, failed)
        counts[tile] += 3
        if ok:
            return True

    # (b) 数牌顺子：rank <= 7 才可能同花色连续三张
    if (is_number_tile(tile) and rank_of(tile) <= 7
            and counts[tile + 1] > 0 and counts[tile + 2] > 0):
        counts[tile] -= 1
        counts[tile + 1] -= 1
        counts[tile + 2] -= 1
        ok = _search(counts, sets_left - 1, cfg, failed)
        counts[tile] += 1
        counts[tile + 1] += 1
        counts[tile + 2] += 1
        if ok:
            return True

    # (c) 字牌顺子（南丰特色）：以 tile 为最小元素的模式
    if cfg.hu.word_straight and is_word(tile):
        for pattern in word_patterns_starting_at(tile):
            if not all(counts[p] > 0 for p in pattern):
                continue
            for p in pattern:
                counts[p] -= 1
            ok = _search(counts, sets_left - 1, cfg, failed)
            for p in pattern:
                counts[p] += 1
            if ok:
                return True

    failed.add(key)
    return False


def is_peng_peng_hu(counts: Counts, meld_count: int) -> bool:
    """碰碰胡：4 组面子全部是刻子（副露里的碰与杠都算刻子），加一对将。"""
    sets_needed = 4 - meld_count
    if sets_needed < 0:
        return False
    if total_count(counts) != sets_needed * 3 + 2:
        return False

    work = bytearray(counts)
    for tile in range(11, len(work)):
        if work[tile] < 2:
            continue
        work[tile] -= 2
        ok = _consume_triplets(work, sets_needed)
        work[tile] += 2
        if ok:
            return True
    return False


def _consume_triplets(counts: Counts, sets_left: int) -> bool:
    if sets_left == 0:
        return _all_zero(counts)
    tile = first_non_zero(counts)
    # 最小非零牌不足 3 张就不可能成刻子，直接否
    if tile == -1 or counts[tile] < 3:
        return False
    counts[tile] -= 3
    ok = _consume_triplets(counts, sets_left - 1)
    counts[tile] += 3
    return ok


def is_peng_peng_hu_dan_diao(counts: Counts, meld_count: int, win_tile: Tile) -> bool:
    """碰碰胡单调：碰碰胡，且**胡的那张牌是把将牌配成对子的那一张**（听单钓将）。

    同一个 14 张成牌形 ``111 222 333 444 55`` 可能来自两种听牌形（单钓 5 / 对倒 4），
    所以这不是成牌形的性质，而是「怎么胡的」的性质 —— 必须知道胡的是哪张。
    """
    sets_needed = 4 - meld_count
    if sets_needed < 0:
        return False
    if total_count(counts) != sets_needed * 3 + 2:
        return False
    if win_tile < 0 or win_tile >= len(counts):
        return False
    if counts[win_tile] < 2:
        return False

    work = bytearray(counts)
    work[win_tile] -= 2
    return _consume_triplets(work, sets_needed)


def is_standard(counts: Counts, meld_count: int, cfg: RuleConfig) -> bool:
    """标准型判胡（``meld_count`` = 已副露组数，每组抵扣 1 组面子需求）。"""
    sets_needed = 4 - meld_count
    if sets_needed < 0:
        return False
    # 张数必须恰好：每组面子 3 张 + 将 2 张。先做这个判断可以挡掉绝大多数否例。
    if total_count(counts) != sets_needed * 3 + 2:
        return False

    work = bytearray(counts)
    for tile in range(11, len(work)):
        if work[tile] < 2:
            continue
        work[tile] -= 2
        ok = decompose(work, sets_needed, cfg)
        work[tile] += 2
        if ok:
            return True
    return False
