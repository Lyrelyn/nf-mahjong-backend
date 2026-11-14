"""``tests/core/hu/huJudge.test.ts`` 的 pytest 等价用例。

覆盖三个 describe：
    - judgeHu 维度合并（结构型互斥 + 其余维度独立叠加，假胡只作兜底）
    - 组合键的稳定性（S-06，fan_tags.tag_key）
    - 配置自检（rule_config.validate_rule_config）

TS 抛 Error/RangeError 的两处（override 键非法、buyCode）在 Python 统一抛 ``ValueError``。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.nanfeng.counts import counts_of
from app.core.nanfeng.fan_tags import tag_key
from app.core.nanfeng.hu.judge import judge_hu
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.rule_config import (
    DEFAULT_RULE_CONFIG,
    JiaHuConfig,
    validate_rule_config,
)

CFG = DEFAULT_RULE_CONFIG


# --------------------------------------------------------------------------- #
# describe('judgeHu 维度合并')
# --------------------------------------------------------------------------- #


def test_all_wan_standard_shape_gets_structure_tags_not_fake_hu_tags() -> None:
    """TS: 全万子标准型：给结构标签与清一色真胡，不给假胡标签（S-01/S-02 的回归锁）。"""
    c = counts_of([11, 12, 13, 11, 12, 13, 14, 15, 16, 17, 17, 17, 18, 18])
    r = judge_hu(c, [], CFG)
    assert r.structure == 'STANDARD'
    assert 'PING_HU' in r.tags
    assert 'QING_YI_SE_ZHEN' in r.tags
    assert 'QING_YI_SE_JIA' not in r.tags


def test_single_suit_without_structure_is_fake_hu() -> None:
    """TS: 全同一花色但不成结构 → 假胡。"""
    c = counts_of([11, 11, 12, 14, 15, 17, 17, 19, 19, 11, 12, 14, 15, 17])
    r = judge_hu(c, [], CFG)
    assert r.structure == 'NONE'
    assert 'QING_YI_SE_JIA' in r.tags
    assert 'QING_YI_SE_ZHEN' not in r.tags


def test_seven_pairs_plus_qing_yi_se_gives_both_tags() -> None:
    """TS: 七对 + 清一色 同时给两个标签（计分表的多标签行必须可达）。"""
    c = counts_of([11, 11, 12, 12, 13, 13, 14, 14, 15, 15, 16, 16, 17, 17])
    r = judge_hu(c, [], CFG)
    assert r.structure == 'QI_DUI'
    assert 'QI_DUI' in r.tags
    assert 'QING_YI_SE_ZHEN' in r.tags
    assert len(r.tags) > 1


def test_seven_pairs_plus_si_gui_yi_stack() -> None:
    """TS: 七对 + 四归一 叠加。"""
    c = counts_of([11, 11, 11, 11, 12, 12, 13, 13, 21, 21, 22, 22, 41, 41])
    r = judge_hu(c, [], CFG)
    assert r.structure == 'QI_DUI'
    assert 'QI_DUI' in r.tags
    assert 'SI_GUI_YI' in r.tags


def test_peng_peng_hu_plus_zi_yi_se_needs_no_meld() -> None:
    """TS: 碰碰胡 + 字一色真胡（一副露都不需要）。"""
    c = counts_of([41, 41, 41, 42, 42, 42, 43, 43, 43, 51, 51, 51, 52, 52])
    r = judge_hu(c, [], CFG)
    assert r.structure == 'STANDARD'
    assert 'PENG_PENG_HU' in r.tags
    assert 'ZI_YI_SE_ZHEN' in r.tags
    assert 'ZI_YI_SE_JIA' not in r.tags


def test_shi_san_lan_and_qi_xing_get_their_own_tags() -> None:
    """TS: 十三烂 与 七星十三烂 分别给对应标签。"""
    lan = judge_hu(
        counts_of([11, 15, 19, 21, 25, 29, 31, 35, 39, 41, 42, 43, 51, 52]), [], CFG)
    assert lan.structure == 'SHI_SAN_LAN'
    assert 'SHI_SAN_LAN' in lan.tags

    qi_xing = judge_hu(
        counts_of([11, 15, 21, 25, 31, 35, 39, 41, 42, 43, 44, 51, 52, 53]), [], CFG)
    assert qi_xing.structure == 'SHI_SAN_LAN'
    assert 'QI_XING_SHI_SAN_LAN' in qi_xing.tags
    assert 'SHI_SAN_LAN' not in qi_xing.tags


def test_seven_pairs_and_shi_san_lan_are_not_judged_with_melds() -> None:
    """TS: 有副露时不判七对与十三烂。"""
    melds = [Meld(kind='PENG', tile=41, from_seat=1)]
    r = judge_hu(counts_of([11, 11, 12, 12, 13, 13, 21, 21, 22, 22]), melds, CFG)
    assert r.structure != 'QI_DUI'
    assert 'QI_DUI' not in r.tags


def test_disabling_jia_hu_kills_the_whole_fallback_path() -> None:
    """TS: 关掉假胡开关后整条通路失效。"""
    off = replace(CFG, hu=replace(CFG.hu, jia_hu=JiaHuConfig(enabled=False, allow_ron=False)))
    c = counts_of([11, 11, 12, 14, 15, 17, 17, 19, 19, 11, 12, 14, 15, 17])
    assert len(judge_hu(c, [], off).tags) == 0


def test_hands_not_totalling_fourteen_tiles_never_win() -> None:
    """TS: 张数不是 14（含副露折算）时一律不胡。

    9 张全万子：花色够格，但张数不足 —— 不能让短牌型被判成假胡；
    10 张暗牌 + 1 组碰 = 13 张，同样不足。
    """
    short = counts_of([11, 11, 12, 14, 15, 17, 17, 19, 19])
    assert len(judge_hu(short, [], CFG).tags) == 0

    melds = [Meld(kind='PENG', tile=41, from_seat=1)]
    assert len(judge_hu(
        counts_of([11, 11, 12, 12, 13, 13, 21, 21, 22, 22]), melds, CFG).tags) == 0


def test_melds_count_towards_the_fourteen_tiles() -> None:
    """TS: 副露计入张数：11 张暗牌 + 1 组碰 = 14 张，可正常判胡。"""
    melds = [Meld(kind='PENG', tile=41, from_seat=1)]
    c = counts_of([11, 12, 13, 11, 12, 13, 14, 15, 16, 18, 18])
    r = judge_hu(c, melds, CFG)
    assert r.structure == 'STANDARD'
    assert 'PING_HU' in r.tags


# --------------------------------------------------------------------------- #
# describe('组合键的稳定性（S-06）')
# --------------------------------------------------------------------------- #


def test_tag_key_is_independent_of_written_order() -> None:
    """TS: 与标签书写顺序无关。"""
    assert tag_key(['SI_GUI_YI', 'ZI_YI_SE_ZHEN']) == tag_key(['ZI_YI_SE_ZHEN', 'SI_GUI_YI'])


def test_tag_key_sorts_by_dimension_segment() -> None:
    """TS: 按维度分段排序：一色型在归一系列之前（与规则文档计分表的写法一致）。"""
    assert tag_key(['SI_GUI_YI', 'ZI_YI_SE_ZHEN']) == 'ZI_YI_SE_ZHEN+SI_GUI_YI'
    assert tag_key(['SHI_ER_GUI_YI', 'ZI_YI_SE_ZHEN', 'QI_DUI']) == (
        'QI_DUI+ZI_YI_SE_ZHEN+SHI_ER_GUI_YI')


def test_tag_key_deduplicates() -> None:
    """TS: 去重。"""
    assert tag_key(['QI_DUI', 'QI_DUI']) == 'QI_DUI'


# --------------------------------------------------------------------------- #
# describe('配置自检')
# --------------------------------------------------------------------------- #


def test_default_rule_config_is_valid() -> None:
    """TS: 默认配置合法（不抛错）。"""
    validate_rule_config(CFG)


def test_override_key_with_unknown_tag_fails_at_startup() -> None:
    """TS: override 键里出现未知标签 → 启动即失败。"""
    bad = replace(CFG, score=replace(CFG.score, override={'QI_DUI+NOT_A_TAG': 99}))
    with pytest.raises(ValueError, match='未知标签'):
        validate_rule_config(bad)


def test_override_key_with_wrong_order_fails_at_startup() -> None:
    """TS: override 键的顺序不对 → 启动即失败（否则整张表静默失配）。"""
    bad = replace(CFG, score=replace(CFG.score, override={'SI_GUI_YI+ZI_YI_SE_ZHEN': 99}))
    with pytest.raises(ValueError, match='顺序'):
        validate_rule_config(bad)


def test_override_key_in_correct_order_passes() -> None:
    """TS: 顺序正确的 override 键通过。"""
    good = replace(
        CFG, score=replace(CFG.score, override={'QI_DUI+ZI_YI_SE_ZHEN+SHI_ER_GUI_YI': 321}))
    validate_rule_config(good)


def test_buy_code_cannot_be_enabled_in_v1() -> None:
    """TS: V1 不允许打开买码（零和参与方尚未定义，见 S-07）。

    TS 的 ``buyCode`` 在 Python 侧是 ``buy_code_enabled``，故错误信息里匹配 snake_case 写法。
    """
    bad = replace(CFG, buy_code_enabled=True)
    with pytest.raises(ValueError, match='buy_code'):
        validate_rule_config(bad)
