"""视图投影 —— 对应前端 spec §8 ``projectView``。

唯一的数据出口是一个纯函数：UI/传输层只接收投影结果，永远不接触 ``GameState``。
    - ``player``：自己的暗牌 + 自己的可操作项 + 全部公开信息；
    - ``spectator``（南丰的轮空买码者）：只有公开信息，无任何暗牌、无牌墙顺序。

**投影是隐私边界**：五个连接里有一个人这局轮空，他绝不能拿到四家的手牌。
所以这里只输出「该连接有权看到的」字段，而不是输出完整状态再由调用方裁剪。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.core.nanfeng.action.hand import HandState
from app.core.nanfeng.action.options import ActionOption, own_turn_options
from app.core.nanfeng.melds import Meld
from app.core.nanfeng.state.game_state import ClaimState, GameState
from app.core.nanfeng.state.invariants import effective_hand_size

ViewerKind = Literal['player', 'spectator']


@dataclass(frozen=True)
class Viewer:
    kind: ViewerKind
    #: 打牌座位号（0..3）；观战者为 ``None``。
    seat: Optional[int] = None


def _meld_payload(meld: Meld) -> dict:
    return {'kind': meld.kind, 'tile': meld.tile, 'fromSeat': meld.from_seat}


def _tiles_of(hand: HandState) -> list[int]:
    """把计数数组展开成牌码列表（升序，便于前端直接排牌）。"""
    tiles: list[int] = []
    for tile in range(11, len(hand.concealed)):
        tiles.extend([tile] * hand.concealed[tile])
    return tiles


def _option_payload(option: ActionOption) -> dict:
    return {
        'type': option.type,
        'priority': option.priority,
        'distance': option.distance,
        'tile': option.tile,
        'huPreview': option.hu_preview,
    }


def _claim_payload(claim: Optional[ClaimState], viewer_seat: Optional[int]) -> Optional[dict]:
    if claim is None:
        return None
    payload = {
        'triggerSeat': claim.trigger_seat,
        'triggerTile': claim.trigger_tile,
        'gangSeat': claim.gang_seat,
        'pending': list(claim.pending),
        'deadlineAt': claim.deadline_at,
        # 只有轮到自己响应时才下发自己的可选项；别人的选项不下发（那也是信息）。
        'options': [],
    }
    if viewer_seat is not None and viewer_seat in claim.options:
        payload['options'] = [_option_payload(option)
                              for option in claim.options[viewer_seat]]
    return payload


def project_view(state: GameState, viewer: Viewer) -> dict:
    """把权威状态投影成「该连接有权看到的」视图。"""
    seat = viewer.seat
    is_player = viewer.kind == 'player' and seat is not None and 0 <= seat < len(state.hands)

    own_options: list[dict] = []
    own_hand: Optional[dict] = None
    if is_player:
        assert seat is not None
        hand = state.hands[seat]
        own_hand = {
            'concealed': _tiles_of(hand),
            'drawnTile': hand.drawn_tile,
            'melds': [_meld_payload(meld) for meld in hand.melds],
            'justPeng': hand.just_peng,
        }
        if state.claim is not None:
            own_options = [
                _option_payload(option)
                for option in state.claim.options.get(seat, [])
            ]
        elif state.phase == 'WAITING_PLAY' and state.turn == seat:
            own_options = [_option_payload(option)
                           for option in own_turn_options(hand, state.cfg)]

    return {
        'seq': state.seq,
        'round': state.round,
        'phase': state.phase,
        'dealer': state.dealer,
        'turn': state.turn,
        'wallLeft': len(state.wall) - state.wall_pos,
        'scores': list(state.scores),
        'roundGangScore': list(state.round_gang_score),
        # 牌河与副露是公开信息；手牌张数也是公开的（只给数量，不给内容）。
        'discards': [list(pile) for pile in state.discards],
        'melds': [[_meld_payload(meld) for meld in hand.melds] for hand in state.hands],
        'handSizes': [effective_hand_size(hand) for hand in state.hands],
        'lastDiscard': state.last_discard,
        'claim': _claim_payload(state.claim, seat),
        'lastSettle': state.last_settle,
        'lastOutcome': None if state.last_outcome is None else {
            'kind': state.last_outcome.kind,
            'loserSeat': state.last_outcome.loser_seat,
            'winners': [
                {
                    'seat': winner.seat,
                    'zimo': winner.zimo,
                    'gangShang': winner.gang_shang,
                    'qiangGang': winner.qiang_gang,
                    'tags': list(winner.tags),
                }
                for winner in state.last_outcome.winners
            ],
        },
        'viewer': {
            'kind': 'player' if is_player else 'spectator',
            'seat': seat if is_player else None,
        },
        'hand': own_hand,
        'options': own_options,
    }
