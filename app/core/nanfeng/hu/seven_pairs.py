"""七对判定 —— 对应前端 ``assets/scripts/core/hu/sevenPairs.ts``。

南丰口径（规则文档 §2.5）：不要求 258 做将；4 张同牌算 2 对，
因此四归一 / 八归一 / 十二归一可以叠加在七对之上。门清要求由调用方 ``judge_hu`` 检查。
"""

from __future__ import annotations

from app.core.nanfeng.counts import Counts, total_count


def is_seven_pairs(counts: Counts) -> bool:
    # 总张数 14 且对数 7 ⟺ 每种牌都是偶数张（奇数张会浪费牌，使对数 < 7）。
    if total_count(counts) != 14:
        return False
    pairs = 0
    for tile in range(11, len(counts)):
        pairs += counts[tile] >> 1
    return pairs == 7
