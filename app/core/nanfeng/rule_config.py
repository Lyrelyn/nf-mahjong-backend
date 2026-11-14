"""规则配置 —— 对应前端 ``assets/scripts/core/ruleConfig.ts``。

南丰麻将的全部可调数值集中在这里。每个数值都来自 spec 或规则文档，
R-01~R-08 / R-10 与 Q-01~Q-06 已逐条确认（见 ``docs/rules-confirmed.md`` 的同名清单）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.nanfeng.fan_tags import FAN_TAG_ID, tag_key


@dataclass(frozen=True)
class JiaHuConfig:
    """假胡（全同一花色 / 全字牌，不需成结构）。R-03 确认存在，自摸与点炮都可以。"""

    enabled: bool = True
    allow_ron: bool = True


@dataclass(frozen=True)
class HuConfig:
    jia_hu: JiaHuConfig = field(default_factory=JiaHuConfig)
    qi_dui: bool = True
    shi_san_lan: bool = True
    #: 字牌顺子（南丰特色，5 种模式）。关掉后退化为标准刻子判定。
    word_straight: bool = True


@dataclass(frozen=True)
class GangConfig:
    """杠分（Q-02）：直杠单人付；补杠与暗杠三家各付。"""

    ming_gang: int = 2
    bu_gang: int = 1
    an_gang: int = 2


@dataclass(frozen=True)
class HuangZhuangConfig:
    """荒庄（R-08）：庄家赔每家 ``dealer_pays_each`` 分，不看听牌。"""

    dealer_pays_each: int = 1


@dataclass(frozen=True)
class ScoreConfig:
    #: 1 炮 = 1 分（已确认）。
    base_score: int = 1
    #: 0 表示不封顶。**2026-10-06 改为 8**：手牌炮数封顶 8，只有杠分能突破。
    cap: int = 8
    #: Q-01 确认为 False —— 自摸只是三家各付，单价与点炮相同。
    zimo_double: bool = False
    #: 杠上开花加炮（已确认 4）。
    gang_shang_kai_hua: int = 4
    gang: GangConfig = field(default_factory=GangConfig)
    huang_zhuang: HuangZhuangConfig = field(default_factory=HuangZhuangConfig)
    #: 非线性组合的例外覆盖表，键由 ``fan_tags.tag_key`` 生成。
    override: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ClaimConfig:
    #: 鸣牌窗口时长（毫秒）。
    window_ms: int = 15000
    #: 自己回合出牌超时（毫秒）。
    discard_timeout_ms: int = 20000
    #: 一炮多响（Q-05）：True = 多家同时胡都算，放炮者分别付给每家。
    allow_multiple_hu: bool = True


@dataclass(frozen=True)
class RuleConfig:
    tile_set: str = 'FULL_136'
    hu: HuConfig = field(default_factory=HuConfig)
    score: ScoreConfig = field(default_factory=ScoreConfig)
    claim: ClaimConfig = field(default_factory=ClaimConfig)
    #: 暗杠是否需要翻牌明示。
    an_gang_reveal_tile: bool = True
    #: 买码 / 马牌，V1 固定 False（结算口径 R-09/R-11 留到 V1.1）。
    buy_code_enabled: bool = False


DEFAULT_RULE_CONFIG = RuleConfig()


def validate_rule_config(cfg: RuleConfig) -> None:
    """配置自检：数值不合法立即抛错，不要带病开局。

    ``score.override`` 的键必须能被 ``tag_key`` 原样重建（标签名拼错、顺序写反都在启动时失败）。
    """

    def fail(msg: str) -> None:
        raise ValueError(f'规则配置非法：{msg}')

    if cfg.tile_set != 'FULL_136':
        fail(f'tile_set 只支持 FULL_136，收到 {cfg.tile_set}')
    if cfg.score.base_score < 1:
        fail('score.base_score 必须 >= 1')
    if cfg.score.cap < 0:
        fail('score.cap 不能为负（0 表示不封顶）')
    if cfg.score.gang_shang_kai_hua < 0:
        fail('score.gang_shang_kai_hua 不能为负')
    gang = cfg.score.gang
    if gang.ming_gang < 0 or gang.bu_gang < 0 or gang.an_gang < 0:
        fail('score.gang 的分值不能为负')
    if cfg.score.huang_zhuang.dealer_pays_each < 0:
        fail('score.huang_zhuang.dealer_pays_each 不能为负')
    if cfg.claim.window_ms <= 0:
        fail('claim.window_ms 必须为正')
    if cfg.claim.discard_timeout_ms <= 0:
        fail('claim.discard_timeout_ms 必须为正')
    if cfg.buy_code_enabled:
        # 买码会改变零和不变量的参与方（spec §13 S-07），V1 不允许打开。
        fail('buy_code 在 V1 必须为 False（Σ 零和参与方尚未定义，见 S-07）')

    for key in cfg.score.override:
        parts = key.split('+')
        for part in parts:
            if part not in FAN_TAG_ID:
                fail(f'score.override 的键 "{key}" 含未知标签 "{part}"')
        if tag_key(parts) != key:
            fail(f'score.override 的键 "{key}" 顺序不正确，应为 "{tag_key(parts)}"')
