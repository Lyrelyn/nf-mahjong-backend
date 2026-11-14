"""牌局阶段与「每个阶段允许哪些动作」—— 对应前端 ``assets/scripts/core/state/phase.ts``。

``LEGAL_ACTIONS`` 是 ``apply_action`` 的第一道闸：任何不在表里的动作直接拒绝。
表里只写**客户端能发起的意图**；``DRAW`` / ``DEAL`` 这种服务端内部推进不是动作，不在表里。

注意 ``CLAIM_WINDOW`` 里的 ``MING_GANG`` 只在「别人打出的牌」上成立；「抢杠窗口」里
只允许 ``HU`` / ``PASS``，那一条由 ``apply_action`` 按 ``claim.gang_seat`` 额外把关。
"""

from __future__ import annotations

from typing import Literal

Phase = Literal[
    'LOBBY', 'DEALING', 'WAITING_PLAY', 'CLAIM_WINDOW', 'GANG_DRAW', 'SETTLING', 'ENDED',
]

LEGAL_ACTIONS: dict[str, tuple[str, ...]] = {
    'LOBBY': (),
    'DEALING': (),
    'WAITING_PLAY': ('DISCARD', 'AN_GANG', 'BU_GANG', 'HU'),
    'CLAIM_WINDOW': ('PENG', 'MING_GANG', 'HU', 'PASS'),
    'GANG_DRAW': (),
    'SETTLING': (),
    'ENDED': (),
}
