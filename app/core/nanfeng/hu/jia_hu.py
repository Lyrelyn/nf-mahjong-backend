"""假胡判定 —— 对应前端 ``assets/scripts/core/hu/jiaHu.ts``。

条件（满足其一）：全部牌同属一个数牌花色；或全部为字牌。
**不需要构成任何面子/将** —— 这是南丰与常规麻将最大的判胡差异。不要求门清：副露参与花色判定。

牌张数（14 张含胡牌张）不是本谓词的职责，由 ``judge_hu`` 在整手牌层面统一检查。
"""

from __future__ import annotations

from app.core.nanfeng.counts import Counts
from app.core.nanfeng.hu.colors import is_qing_yi_se, is_zi_yi_se
from app.core.nanfeng.melds import Meld


def is_jia_hu(counts: Counts, melds: tuple[Meld, ...] | list[Meld]) -> bool:
    return is_qing_yi_se(counts, melds) or is_zi_yi_se(counts, melds)
