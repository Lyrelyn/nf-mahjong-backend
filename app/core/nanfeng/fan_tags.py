"""牌型标签与其稳定 id —— 对应前端 ``assets/scripts/core/fanTags.ts``。

S-06 修正：每个标签有**显式稳定 id**，``tag_key`` 按 id 升序生成组合键。
id 分段遵循规则文档计分表的书写顺序（也是组合键的契约）：
    10-19 结构型 → 20-29 一色型 → 30-39 归一系列 → 40-49 事件型
因此 ``ZI_YI_SE_ZHEN+SI_GUI_YI`` 是正确键，字典序的 ``SI_GUI_YI+ZI_YI_SE_ZHEN`` 会让整张表失配。
"""

from __future__ import annotations

from typing import Iterable, Literal

FanTag = Literal[
    'PING_HU',
    'PENG_PENG_HU',
    'PENG_PENG_HU_DAN_DIAO',
    'QI_DUI',
    'SHI_SAN_LAN',
    'QI_XING_SHI_SAN_LAN',
    'QING_YI_SE_ZHEN',
    'QING_YI_SE_JIA',
    'ZI_YI_SE_ZHEN',
    'ZI_YI_SE_JIA',
    'SI_GUI_YI',
    'BA_GUI_YI',
    'SHI_ER_GUI_YI',
    'ZI_MO',
    'GANG_SHANG_KAI_HUA',
    'QIANG_GANG_HU',
]

#: 稳定的标签 id。**新标签一律往后取号，绝不重排已有 id**
#: （重排会让已存在的 ``score.override`` 键静默改指到别的标签）。
FAN_TAG_ID: dict[str, int] = {
    'PING_HU': 10,
    'PENG_PENG_HU': 11,
    'QI_DUI': 12,
    'SHI_SAN_LAN': 13,
    'QI_XING_SHI_SAN_LAN': 14,
    # 15 是结构型段里剩下的空位。
    'PENG_PENG_HU_DAN_DIAO': 15,
    'QING_YI_SE_ZHEN': 20,
    'QING_YI_SE_JIA': 21,
    'ZI_YI_SE_ZHEN': 22,
    'ZI_YI_SE_JIA': 23,
    'SI_GUI_YI': 30,
    'BA_GUI_YI': 31,
    'SHI_ER_GUI_YI': 32,
    'ZI_MO': 40,
    'GANG_SHANG_KAI_HUA': 41,
    # 42 / 43 曾是天胡 / 地胡，Q-03 确认南丰没有这两个牌型 —— id 空出来但**不复用**。
    'QIANG_GANG_HU': 44,
}

#: 全部标签，顺序即 tag_key 的排序结果。
ALL_FAN_TAGS: tuple[str, ...] = tuple(
    sorted(FAN_TAG_ID, key=lambda tag: FAN_TAG_ID[tag]))


def tag_key(tags: Iterable[str]) -> str:
    """组合键：去重后按稳定 id 升序，以 ``+`` 连接。"""
    unique = set(tags)
    return '+'.join(sorted(unique, key=lambda tag: FAN_TAG_ID[tag]))
