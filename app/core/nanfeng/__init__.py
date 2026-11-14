"""南丰麻将规则内核 —— 从前端 ``assets/scripts/core/`` 1:1 翻译。

约定（与前端引擎禁区一致，spec §3.3）：
    - 不 import asyncio / 网络 / 时钟 / 未注入的随机源；
    - 不 import ``app.game`` / ``app.api`` / ``app.ws``（内核不依赖传输层）；
    - 状态不可变：变换返回**新**对象，绝不改动入参。

模块与前端文件一一对应，便于逐文件对照：

    tiles.py        ↔ core/tiles.ts
    counts.py       ↔ core/counts.ts
    melds.py        ↔ core/melds.ts
    prng.py         ↔ core/prng.ts
    fan_tags.py     ↔ core/fanTags.ts
    rule_config.py  ↔ core/ruleConfig.ts
    hu/*            ↔ core/hu/*
    action/*        ↔ core/action/*
    state/*         ↔ core/state/*
    score/*         ↔ core/score/*
    view.py         ↔ spec §8 projectView
"""

from app.core.nanfeng.counts import (
    Counts,
    counts_key,
    counts_of,
    first_non_zero,
    total_count,
)
from app.core.nanfeng.fan_tags import ALL_FAN_TAGS, FAN_TAG_ID, FanTag, tag_key
from app.core.nanfeng.melds import Meld, MeldKind, meld_set_count, meld_tile_count
from app.core.nanfeng.prng import Rng, create_rng, shuffle_wall
from app.core.nanfeng.rule_config import (
    DEFAULT_RULE_CONFIG,
    RuleConfig,
    validate_rule_config,
)
from app.core.nanfeng.tiles import (
    COUNT_SIZE,
    WALL_SIZE,
    Suit,
    Tile,
    full_wall,
    is_dragon,
    is_number_tile,
    is_valid_tile,
    is_wind,
    is_word,
    rank_of,
    suit_of,
)

__all__ = [
    'ALL_FAN_TAGS',
    'COUNT_SIZE',
    'Counts',
    'DEFAULT_RULE_CONFIG',
    'FAN_TAG_ID',
    'FanTag',
    'Meld',
    'MeldKind',
    'Rng',
    'RuleConfig',
    'Suit',
    'Tile',
    'WALL_SIZE',
    'counts_key',
    'counts_of',
    'create_rng',
    'first_non_zero',
    'full_wall',
    'is_dragon',
    'is_number_tile',
    'is_valid_tile',
    'is_wind',
    'is_word',
    'meld_set_count',
    'meld_tile_count',
    'rank_of',
    'shuffle_wall',
    'suit_of',
    'tag_key',
    'total_count',
    'validate_rule_config',
]
