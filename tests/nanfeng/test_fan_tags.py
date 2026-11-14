"""标签表用例 —— 对应前端 ``tests/core/fanTags.test.ts``。

每组用例与 TS 的 ``it`` 一一对应（docstring 里标出 TS 标题），断言值与 TS 完全一致。
"""

from dataclasses import fields

import pytest

from app.core.nanfeng.fan_tags import ALL_FAN_TAGS, FAN_TAG_ID, tag_key
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG


@pytest.mark.parametrize('tag', ['TIAN_HU', 'DI_HU'])
def test_不存在天胡地胡标签(tag: str) -> None:
    """TS: 不存在 TIAN_HU / DI_HU 两个标签 —— 南丰麻将没有这两个牌型（Q-03）。"""
    assert tag not in ALL_FAN_TAGS
    assert tag not in FAN_TAG_ID


def test_腾出的_id_42_43_不复用() -> None:
    """TS: 腾出来的 id 42/43 不复用给其它标签（复用会让已有的 score.override 键静默改指）。"""
    assert 42 not in FAN_TAG_ID.values()
    assert 43 not in FAN_TAG_ID.values()


def test_标签_id_唯一() -> None:
    """TS: 标签 id 唯一。"""
    ids = list(FAN_TAG_ID.values())
    assert len(set(ids)) == len(ids)


def test_组合键仍然按维度分段() -> None:
    """TS: 组合键仍然按维度分段（一色型在归一系列之前）。"""
    assert tag_key(['SI_GUI_YI', 'ZI_YI_SE_ZHEN']) == 'ZI_YI_SE_ZHEN+SI_GUI_YI'


def test_score_里没有天胡地胡的固定分项() -> None:
    """TS: score 里没有天胡/地胡的固定分项（Q-03：固定分通路删除）。

    TS 的 ``'tianDiHu' in DEFAULT_RULE_CONFIG.score``：Python 移植版是 frozen dataclass，
    对应的「成员存在性」检查是 dataclass 字段名（蛇形命名）里没有 ``tian_di_hu``。
    """
    assert 'tian_di_hu' not in {field.name for field in fields(DEFAULT_RULE_CONFIG.score)}
