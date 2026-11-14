"""分层计分 —— 对应前端 ``assets/scripts/core/score/scoreTable.ts``。

规则文档原本用一张 38 行的「组合键 → 炮数」枚举表，值是作者**直接列出**的、无法由基础分推导。
Task 0 与牌友确认后**放弃那张表**，改为分层相加：

    炮数 = 结构型分(取最高) + 一色加成 + 归一加成 + 事件加成

每层内部的规则：
    - **结构型（取最高）**：平胡 1 / 十三烂 3 / 碰碰胡 4 / 碰碰胡单调 8 / 七对 8；
      七星分档自摸 4、其他 2。**假胡没有结构分（0）** —— 这正是「清一色假胡 = 4」成立的原因；
    - **一色加成（取最高）**：清一色真 10 / 假 4，字一色真 20 / 假 11。真胡时它是**加成**：
      平胡 1 + 清一色真 10 = 11、平胡 1 + 字一色真 20 = 21 —— 这是**封顶前**的原始分；
    - **归一加成（取最高）**：四 3 / 八 5 / 十二 9；
    - **事件加成（相加）**：杠上开花 +4；抢杠胡本身 0 分。

**2026-10-06 改规：手牌炮数封顶 8，只有杠能突破。** 本函数返回的仍然是**封顶前的原始分**，
``cap`` 在结算那一层作用，而且**杠分是在封顶之后才并入** ``deltas`` 的 —— 所以「只有杠能突破
封顶」不需要额外代码，它是既有结构的自然结果。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.nanfeng.fan_tags import FanTag, tag_key
from app.core.nanfeng.rule_config import RuleConfig

#: 结构型基础分（互斥，取最高）。
STRUCTURE_SCORE: dict[str, int] = {
    'PING_HU': 1,
    'SHI_SAN_LAN': 3,
    'PENG_PENG_HU': 4,
    #: 碰碰胡 + 单钓将。8 正好等于封顶，所以它天然吃满。
    'PENG_PENG_HU_DAN_DIAO': 8,
    'QI_DUI': 8,
}

#: 七星十三烂的两档炮数（2026-10-06 改为自摸 4 / 其他 2）。
QI_XING_SCORE: dict[str, int] = {'zimo': 4, 'ron': 2}

#: 一色加成（真胡时叠加在结构分上；假胡没有结构分，所以它就是全部）。
COLOR_BONUS: dict[str, int] = {
    'QING_YI_SE_ZHEN': 10,
    #: 2026-10-06 改为 4（原 6）—— 假胡很容易凑一色，压下来。
    'QING_YI_SE_JIA': 4,
    'ZI_YI_SE_ZHEN': 20,
    'ZI_YI_SE_JIA': 11,
}

#: 归一加成（互斥，取最高）。
GUI_YI_BONUS: dict[str, int] = {
    'SI_GUI_YI': 3,
    'BA_GUI_YI': 5,
    'SHI_ER_GUI_YI': 9,
}

#: 事件加成（相加）。
EVENT_BONUS: dict[str, int] = {
    'GANG_SHANG_KAI_HUA': 4,
    'QIANG_GANG_HU': 0,
}


@dataclass(frozen=True)
class ScoreResult:
    score: int
    #: 没有在分层表里定义的标签。**正常路径必须为空**（留字段是为了以后加规则时能报出来）。
    unmapped: tuple[FanTag, ...] = ()


def _max_in(table: dict[str, int], tags: frozenset[str] | set[str]) -> int:
    best = 0
    for tag, value in table.items():
        if tag in tags:
            best = max(best, value)
    return best


def score_of_tags(
    tags: frozenset[str] | set[str],
    cfg: RuleConfig,
    zimo: bool = False,
) -> ScoreResult:
    overridden = cfg.score.override.get(tag_key(tags))
    if overridden is not None:
        return ScoreResult(score=overridden)

    if 'QI_XING_SHI_SAN_LAN' in tags:
        structure = max(
            _max_in(STRUCTURE_SCORE, tags),
            QI_XING_SCORE['zimo'] if zimo else QI_XING_SCORE['ron'],
        )
    else:
        structure = _max_in(STRUCTURE_SCORE, tags)

    color = _max_in(COLOR_BONUS, tags)
    gui_yi = _max_in(GUI_YI_BONUS, tags)

    event = 0
    for tag, value in EVENT_BONUS.items():
        if tag in tags:
            event += value

    known = (
        set(STRUCTURE_SCORE)
        | set(COLOR_BONUS)
        | set(GUI_YI_BONUS)
        | set(EVENT_BONUS)
        | {'QI_XING_SHI_SAN_LAN', 'ZI_MO'}
    )
    unmapped = tuple(tag for tag in tags if tag not in known)

    return ScoreResult(score=structure + color + gui_yi + event, unmapped=unmapped)
