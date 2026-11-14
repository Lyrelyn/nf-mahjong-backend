"""``score/score_table.py`` 的 pytest 对拍 —— 逐条翻译
``tests/core/score/scoreTable.test.ts``。

``scoreOfTags(tags, cfg, { zimo }).score`` → ``score_of_tags(tags, cfg, zimo).score``。
TS 的 ``Set<FanTag>`` 对应 Python 的 ``set``（或 ``frozenset``）。
"""

from __future__ import annotations

from dataclasses import replace

from app.core.nanfeng.fan_tags import ALL_FAN_TAGS
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG
from app.core.nanfeng.score.score_table import (
    COLOR_BONUS,
    GUI_YI_BONUS,
    STRUCTURE_SCORE,
    score_of_tags,
)

cfg = DEFAULT_RULE_CONFIG


def tags(*names: str) -> set[str]:
    """TS ``tags(...t)``：``new Set(t)``。"""
    return set(names)


def score(tag_set, c=None, zimo: bool = False) -> int:
    """TS ``score(set, c = cfg, zimo = false)``。"""
    return score_of_tags(tag_set, cfg if c is None else c, zimo=zimo).score


# ---------------------------------------------------------------------------
# 分层计分：结构型（取最高）
# ---------------------------------------------------------------------------

def test_single_structure_tag_base_scores():
    """单标签基础分与 Task 0 确认的数值一致。"""
    assert score(tags('PING_HU')) == 1
    assert score(tags('SHI_SAN_LAN')) == 3
    assert score(tags('PENG_PENG_HU')) == 4
    assert score(tags('QI_DUI')) == 8


def test_structure_tags_are_mutually_exclusive():
    """结构型互斥，同时出现时取最高而不是相加。"""
    assert score(tags('PING_HU', 'PENG_PENG_HU')) == 4
    assert score(tags('PING_HU', 'PENG_PENG_HU', 'QI_DUI')) == 8


def test_qi_xing_has_two_tiers():
    """七星十三烂两档：自摸 4 炮、其他 2 炮（2026-10-06 改规）。"""
    assert score(tags('QI_XING_SHI_SAN_LAN'), cfg, True) == 4
    assert score(tags('QI_XING_SHI_SAN_LAN'), cfg, False) == 2


def test_peng_peng_hu_dan_diao_is_eight():
    """碰碰胡单调 8 炮，高于普通碰碰胡 4 炮；同时出现取最高的 8。"""
    assert score(tags('PENG_PENG_HU_DAN_DIAO')) == 8
    assert score(tags('PENG_PENG_HU', 'PENG_PENG_HU_DAN_DIAO')) == 8


# ---------------------------------------------------------------------------
# 分层计分：一色型（加成）
# ---------------------------------------------------------------------------

def test_qing_yi_se_bonus_adds_to_structure():
    """真胡的一色是加在结构分上的：平胡 1 + 清一色 10 = 11（Q-03 确认的真胡 11 分）。"""
    assert COLOR_BONUS['QING_YI_SE_ZHEN'] == 10
    assert score(tags('PING_HU', 'QING_YI_SE_ZHEN')) == 11


def test_zi_yi_se_bonus_adds_to_structure():
    """字一色真：平胡 1 + 20 = 21（Q-04 确认的 21 分）。"""
    assert COLOR_BONUS['ZI_YI_SE_ZHEN'] == 20
    assert score(tags('PING_HU', 'ZI_YI_SE_ZHEN')) == 21


def test_jia_hu_color_is_the_whole_score():
    """假胡没有结构分，一色值就是全部：清一色假 4、字一色假 11。

    （2026-10-06 改规，字一色假靠封顶落到 8 —— 封顶在结算层，这里仍是 11。）
    """
    assert score(tags('QING_YI_SE_JIA')) == 4
    assert score(tags('ZI_YI_SE_JIA')) == 11


def test_color_tags_are_mutually_exclusive():
    """一色型之间互斥（清一色与字一色不可能同时成立），取最高。"""
    assert score(tags('PING_HU', 'QING_YI_SE_ZHEN', 'ZI_YI_SE_ZHEN')) == 21


# ---------------------------------------------------------------------------
# 分层计分：归一与事件（叠加）
# ---------------------------------------------------------------------------

def test_gui_yi_bonus_values():
    """归一加成 四/八/十二 = 3/5/9。"""
    assert GUI_YI_BONUS == {'SI_GUI_YI': 3, 'BA_GUI_YI': 5, 'SHI_ER_GUI_YI': 9}
    assert score(tags('QI_DUI', 'SI_GUI_YI')) == 8 + 3
    assert score(tags('QI_DUI', 'BA_GUI_YI')) == 8 + 5
    assert score(tags('QI_DUI', 'SHI_ER_GUI_YI')) == 8 + 9


def test_gui_yi_tags_are_mutually_exclusive():
    """归一系列互斥，同时出现取最高。"""
    assert score(tags('QI_DUI', 'SI_GUI_YI', 'SHI_ER_GUI_YI')) == 8 + 9


def test_gang_shang_kai_hua_adds_four():
    """杠上开花 +4 事件加成。"""
    assert score(tags('PING_HU', 'GANG_SHANG_KAI_HUA')) == 1 + 4
    assert score(tags('PING_HU', 'QING_YI_SE_ZHEN', 'GANG_SHANG_KAI_HUA')) == 1 + 10 + 4


def test_qiang_gang_hu_adds_nothing():
    """抢杠胡本身不加分（分数来自牌型）。"""
    assert score(tags('PING_HU', 'QIANG_GANG_HU')) == 1


def test_multi_dimension_qi_dui_qing_yi():
    """多维叠加：七对 + 清一色真 + 四归一 = 8 + 10 + 3。"""
    assert score(tags('QI_DUI', 'QING_YI_SE_ZHEN', 'SI_GUI_YI')) == 21


def test_multi_dimension_peng_peng_zi_yi():
    """多维叠加：碰碰胡 + 字一色真 = 4 + 20；再加十二归一 = 4 + 20 + 9。"""
    assert score(tags('PENG_PENG_HU', 'ZI_YI_SE_ZHEN')) == 24
    assert score(tags('PENG_PENG_HU', 'ZI_YI_SE_ZHEN', 'SHI_ER_GUI_YI')) == 33


def test_empty_tag_set_scores_zero():
    """空标签集是 0 分（不该出现在正常流程里，但不许报错）。"""
    assert score(tags()) == 0


# ---------------------------------------------------------------------------
# 例外覆盖表与自检
# ---------------------------------------------------------------------------

def test_override_takes_precedence_over_formula():
    """override 优先于分层公式，键由 tag_key 生成。"""
    c = replace(cfg, score=replace(cfg.score, override={'QI_DUI+QING_YI_SE_ZHEN': 99}))
    assert score(tags('QI_DUI', 'QING_YI_SE_ZHEN'), c) == 99
    # 只覆盖命中的那一组，其它组合照走公式
    assert score(tags('QI_DUI', 'ZI_YI_SE_ZHEN'), c) == 8 + 20


def test_every_fan_tag_is_defined_in_the_tables():
    """每个 FanTag 都在分层表里有定义（防止漏配导致静默低分）。"""
    defined = set(STRUCTURE_SCORE) | set(COLOR_BONUS) | set(GUI_YI_BONUS) | {
        'QI_XING_SHI_SAN_LAN',
        'GANG_SHANG_KAI_HUA',
        'QIANG_GANG_HU',
        'ZI_MO',
    }
    for tag in ALL_FAN_TAGS:
        assert tag in defined, f'标签 {tag} 没有在计分表里定义'


def test_uncovered_combination_falls_back_to_formula():
    """未覆盖组合回落到分层公式，而不是取最大值兜底，unmapped 为空。"""
    result = score_of_tags(tags('PENG_PENG_HU', 'SI_GUI_YI'), cfg)
    assert result.score == 4 + 3
    assert result.unmapped == ()


def test_cap_is_not_applied_at_this_layer():
    """cap 不在这一层做（封顶属于结算，Task 19）。"""
    capped = replace(cfg, score=replace(cfg.score, cap=5))
    assert score(tags('ZI_YI_SE_ZHEN', 'PING_HU'), capped) == 21
