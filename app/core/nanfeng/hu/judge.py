"""判胡入口 —— 对应前端 ``assets/scripts/core/hu/huJudge.ts``。

按维度独立判定后**合并标签集合**，而不是「特型优先短路 + 返回单一枚举」：
    - S-01：计分表按多标签组合建键（如 ``QI_DUI+ZI_YI_SE_ZHEN``），只返回单一枚举会让
      表里所有多标签行永远不可达，所以必须返回 ``set[FanTag]``；
    - S-02：假胡只作**兜底**，真结构成立时绝不叠加假胡标签（H-31）。

结构型（标准型 / 七对 / 十三烂）互斥，取第一个成立的；其余维度各自独立叠加。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.nanfeng.counts import Counts, total_count
from app.core.nanfeng.fan_tags import FanTag
from app.core.nanfeng.hu.colors import is_qing_yi_se, is_zi_yi_se
from app.core.nanfeng.hu.decompose import is_peng_peng_hu, is_standard
from app.core.nanfeng.hu.gui_yi import count_gui_yi, gui_yi_tag
from app.core.nanfeng.hu.jia_hu import is_jia_hu
from app.core.nanfeng.hu.seven_pairs import is_seven_pairs
from app.core.nanfeng.hu.shi_san_lan import is_qi_xing_shi_san_lan, is_shi_san_lan
from app.core.nanfeng.melds import Meld, meld_tile_count
from app.core.nanfeng.rule_config import RuleConfig

StructureKind = Literal['STANDARD', 'QI_DUI', 'SHI_SAN_LAN', 'NONE']


@dataclass(frozen=True)
class JudgeResult:
    structure: StructureKind
    tags: frozenset[str] = field(default_factory=frozenset)


def judge_hu(
    counts: Counts,
    melds: tuple[Meld, ...] | list[Meld],
    cfg: RuleConfig,
) -> JudgeResult:
    tags: set[FanTag] = set()
    meld_count = len(melds)

    # 整手牌必须是 14 张（暗牌 + 副露折算，含胡牌张）。张数不对一律不胡。
    meld_tiles = sum(meld_tile_count(meld) for meld in melds)
    if total_count(counts) + meld_tiles != 14:
        return JudgeResult(structure='NONE', tags=frozenset())

    # 结构型：互斥，取第一个成立的。七对与十三烂都要求门清（无副露）。
    structure: StructureKind = 'NONE'
    if meld_count == 0 and cfg.hu.qi_dui and is_seven_pairs(counts):
        structure = 'QI_DUI'
    elif meld_count == 0 and cfg.hu.shi_san_lan and is_shi_san_lan(counts):
        structure = 'SHI_SAN_LAN'
    elif is_standard(counts, meld_count, cfg):
        structure = 'STANDARD'

    qing = is_qing_yi_se(counts, melds)
    zi = is_zi_yi_se(counts, melds)

    if structure != 'NONE':
        if structure == 'QI_DUI':
            tags.add('QI_DUI')
        if structure == 'SHI_SAN_LAN':
            tags.add('QI_XING_SHI_SAN_LAN' if is_qi_xing_shi_san_lan(counts)
                     else 'SHI_SAN_LAN')
        if structure == 'STANDARD':
            tags.add('PENG_PENG_HU' if is_peng_peng_hu(counts, meld_count) else 'PING_HU')
        if qing:
            tags.add('QING_YI_SE_ZHEN')
        if zi:
            tags.add('ZI_YI_SE_ZHEN')
        gui_yi = gui_yi_tag(count_gui_yi(counts, melds))
        if gui_yi:
            tags.add(gui_yi)
    elif cfg.hu.jia_hu.enabled and is_jia_hu(counts, melds):
        # 假胡兜底：真结构成立时绝不叠加假胡标签（H-31），故只在 structure == 'NONE' 时到达。
        if qing:
            tags.add('QING_YI_SE_JIA')
        if zi:
            tags.add('ZI_YI_SE_JIA')

    return JudgeResult(structure=structure, tags=frozenset(tags))
