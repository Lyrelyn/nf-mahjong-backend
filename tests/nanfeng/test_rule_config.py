"""规则配置用例 —— 对应前端 ``tests/core/ruleConfig.test.ts``。

每条 pytest 用例与 TS 的 ``it`` 一一对应（docstring 里标出 TS 标题）。
语言层差异：
    - 字段名蛇形化（``zimoDouble`` → ``zimo_double``、``allowMultipleHu`` → ``allow_multiple_hu``）；
    - TS 的 ``toEqual({...})`` 是结构比较，Python 用 ``dataclasses.asdict`` 展开后比字典；
    - TS 的 ``{...cfg, score: {...}}`` 展开用 ``dataclasses.replace`` 实现（配置是 frozen dataclass）；
    - TS 抛 ``RangeError`` 的地方，移植版统一抛 ``ValueError``。
"""

from dataclasses import asdict, fields, replace

import pytest

from app.core.nanfeng.rule_config import (
    DEFAULT_RULE_CONFIG,
    HuangZhuangConfig,
    validate_rule_config,
)

CFG = DEFAULT_RULE_CONFIG


def test_自摸不翻倍() -> None:
    """TS: 自摸不翻倍（Q-01）：自摸与点炮的单价相同，只是付款人数不同。"""
    assert CFG.score.zimo_double is False


def test_杠分() -> None:
    """TS: 杠分（Q-02）：直杠 2 / 补杠 1 / 暗杠 2，在开杠时即时结算。"""
    assert asdict(CFG.score.gang) == {'ming_gang': 2, 'bu_gang': 1, 'an_gang': 2}


def test_荒庄() -> None:
    """TS: 荒庄（R-08）：庄家赔每家 1 分（共 3 分）。"""
    assert asdict(CFG.score.huang_zhuang) == {'dealer_pays_each': 1}


def test_一炮多响() -> None:
    """TS: 一炮多响（Q-05）：多家同时胡都算，放炮者分别付给每家。"""
    assert CFG.claim.allow_multiple_hu is True


def test_封顶_8_炮() -> None:
    """TS: 封顶 8 炮（2026-10-06 改规，原为不封顶）：只有杠分能突破。"""
    assert CFG.score.cap == 8
    # 杠分是独立台账，不参与封顶；荒庄也保留。
    assert asdict(CFG.score.gang) == {'ming_gang': 2, 'bu_gang': 1, 'an_gang': 2}


def test_买码结算在_V1_保持关闭() -> None:
    """TS: 买码结算在 V1 保持关闭（S-07）。

    TS 读的是 ``cfg.buyCode.enabled``；移植版把买码开关摊平成 ``RuleConfig.buy_code_enabled``
    （见报告「结构差异」），断言的布尔值仍是 ``false``。
    """
    assert CFG.buy_code_enabled is False


def test_配置项_forbiddenHu_整个删除() -> None:
    """TS: 配置项 forbiddenHu 整个删除 —— 两条限制都不存在，没有可配的东西（R-06）。

    TS 用 ``'forbiddenHu' in cfg``；frozen dataclass 的对应检查是字段名集合。
    """
    assert 'forbidden_hu' not in {field.name for field in fields(CFG)}


def test_默认配置合法() -> None:
    """TS: 默认配置合法。"""
    validate_rule_config(CFG)  # 不抛错即通过（对应 TS 的 `.not.toThrow()`）


def test_杠分为负_启动即失败() -> None:
    """TS: 杠分为负 → 启动即失败。"""
    bad = replace(
        CFG,
        score=replace(CFG.score, gang=replace(CFG.score.gang, an_gang=-1)),
    )
    with pytest.raises(ValueError, match='gang'):
        validate_rule_config(bad)


def test_荒庄赔付为负_启动即失败() -> None:
    """TS: 荒庄赔付为负 → 启动即失败。

    TS 断言 ``toThrow(/huangZhuang/)``：正则匹配的是报错里的字段名。
    移植版字段名统一蛇形化（``huangZhuang`` → ``huang_zhuang``），报错文案也跟着是
    ``score.huang_zhuang.dealer_pays_each``，所以这里的正则按同一套命名转换写成
    ``huang_zhuang`` —— 断言语义（报错指出 huangZhuang 字段）与 TS 等价。
    """
    bad = replace(
        CFG,
        score=replace(CFG.score, huang_zhuang=HuangZhuangConfig(dealer_pays_each=-1)),
    )
    with pytest.raises(ValueError, match='huang_zhuang'):
        validate_rule_config(bad)
