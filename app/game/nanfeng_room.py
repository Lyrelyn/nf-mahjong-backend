"""南丰麻将房间会话 —— 5 个连接、4 人打牌、每局换座。

与旧（莲花）房间模型的根本差别：

* **座位是两个概念**。``slot`` 是「连接位」（0..4，WS 的 seat 就是它，重进码绑在它上面）；
  ``table_seat`` 是本局打牌的座位（0..3，引擎的 seat）。每局结束换座只改这两者的映射，
  **身份从不搬家** —— 所以重进码、断线托管、WS 绑定都不用跟着换。
* **5 人轮换**。``rotation[:4]`` 是本局的四个打牌位，``rotation[4]`` 是本局轮空（买码/观战）
  的人。规则见 ``core.nanfeng.state.game_state.next_round_seating``。
* **服务端就是裁判**。没有房主迁移、没有私有手牌上报、没有一致性哈希 —— 快照即唯一真源。

同时保留旧房间层验证过的工程能力：重进码限速、断线自动代打、房间限时与看门狗、
结算落库、逐座位裁剪的快照。
"""

from __future__ import annotations

import asyncio
import os
import random
import secrets
import time
from dataclasses import dataclass, replace
from typing import Optional

from loguru import logger

from app.core.nanfeng.action.hand import HandState
from app.core.nanfeng.action.options import ActionType, PlayerAction, own_turn_options
from app.core.nanfeng.prng import create_rng
from app.core.nanfeng.rule_config import DEFAULT_RULE_CONFIG, RuleConfig
from app.core.nanfeng.state.apply import GameEvent, apply_action
from app.core.nanfeng.state.game_state import (
    RoundOutcome,
    StartRoundOptions,
    next_round_seating,
    start_round,
)
from app.core.nanfeng.view import Viewer, project_view
from app.ws.manager import ConnectionManager

RULESET_ID = 'nanfeng'
#: 连接位数量：4 个打牌位 + 1 个轮空/买码位（前端 spec §4.1）。
PLAYER_SLOTS = 5
#: 一桌固定 4 人打牌。
TABLE_SEATS = 4

ROOM_LIFETIME = float(os.environ.get('ROOM_LIFETIME', str(60 * 60)))
ROOM_MATCH_MAX = float(os.environ.get('ROOM_MATCH_MAX', str(90 * 60)))
ROOM_WATCHDOG_INTERVAL = float(os.environ.get('ROOM_WATCHDOG_INTERVAL', '30'))

#: 换座/结算之间的停顿（秒）；测试传 0 即可即时推进。
SETTLE_PAUSE = 0.6


class RoomError(Exception):
    """房间级业务错误；``str(exc)`` 就是给客户端看的错误码。"""


def _make_rejoin_code() -> str:
    return secrets.token_urlsafe(12)


@dataclass
class SeatState:
    """一个**连接位**（不是打牌座位）。身份、重进码、准备态都挂在这里。"""

    slot: int
    nickname: str
    rejoin_code: str
    player_id: Optional[str] = None
    avatar: str = ''
    ready: bool = False

    @property
    def seat(self) -> int:
        """兼容 REST/WS 层的历史叫法：``seat`` == 连接位。"""
        return self.slot


class RoomSession:
    """单房间会话：连接位 / 轮换 / 对局驱动 / 断线代打 / 落库。"""

    ruleset_id = RULESET_ID

    def __init__(self, room_id: str, mode: str = 'east', capacity: int = PLAYER_SLOTS,
                 storage=None, turn_timeout: float = 20.0, match_length: int = 4,
                 rule_config: RuleConfig | None = None,
                 random_seed: int | None = None, pace: float = 0.0):
        self.room_id = room_id
        self.mode = mode
        self.capacity = PLAYER_SLOTS
        self.player_count = PLAYER_SLOTS
        self.match_length = match_length
        self.cfg = rule_config or DEFAULT_RULE_CONFIG
        self.storage = storage
        self.turn_timeout = turn_timeout
        self.pace = pace
        self.random_seed = random_seed

        self.status = 'lobby'          # lobby / playing / finished / closed
        self.slots: list[Optional[SeatState]] = [None] * PLAYER_SLOTS
        self.creator_slot: Optional[int] = None
        self.lifetime = ROOM_LIFETIME
        self.created_at = time.monotonic()
        self.deadline = self.created_at + ROOM_LIFETIME

        #: ``rotation[:4]`` = 本局四个打牌位（table seat 0..3）对应的连接位；
        #: ``rotation[4]`` = 本局轮空的连接位（没人时是 -1）。
        self.rotation: list[int] = [-1] * PLAYER_SLOTS
        self.state = None              # GameState | None
        #: 累计得分按**连接位**记（座位每局会换，分数不能跟着座位走）。
        self.total_scores: dict[int, int] = {}
        self.round_index = 0
        self.match_id: Optional[str] = None
        self.match_started_at: Optional[float] = None
        self.match_finished = False
        self._forfeited_slots: set[int] = set()

        self.conn = ConnectionManager()
        self._rejoin_attempts: dict[str, list[float]] = {}
        self._rejoin_window = 30.0
        self._rejoin_limit = 5
        self._deadline_task: Optional[asyncio.Task] = None
        self._round_task: Optional[asyncio.Task] = None
        self._forced = False

    # ── 生命周期 ─────────────────────────────────────────

    def is_past_deadline(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.monotonic()) >= self.deadline

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.status == 'playing':
            return False
        return self.is_past_deadline(now)

    @property
    def creator_seat(self) -> Optional[int]:
        return self.creator_slot

    @creator_seat.setter
    def creator_seat(self, value: Optional[int]) -> None:
        self.creator_slot = value

    @property
    def rules(self):
        """旧接口兼容：房间不再有规则集插件，但上层可能读它。"""
        return None

    def has_humans(self) -> bool:
        return any(state is not None for state in self.slots)

    def occupied_slots(self) -> list[int]:
        return [slot for slot, state in enumerate(self.slots) if state is not None]

    # ── 入座 / 重连 ──────────────────────────────────────

    def join_or_rejoin(self, nickname: str, player_id: Optional[str] = None,
                       avatar: str = '') -> tuple[int, bool, SeatState]:
        """REST join：占第一个空连接位并签发重进码。失败抛 ``RoomError``。"""
        if player_id and self.storage is not None and self.storage.is_banned('player', player_id):
            raise RoomError('BANNED')
        if player_id:
            for state in self.slots:
                if state is not None and state.player_id == player_id:
                    return state.slot, True, state
        if self.status not in ('lobby', 'finished'):
            raise RoomError('ROOM_CLOSED')
        for state in self.slots:
            if state is not None and state.nickname == nickname:
                raise RoomError('NICKNAME_TAKEN')
        slot = next((index for index, state in enumerate(self.slots) if state is None), None)
        if slot is None:
            raise RoomError('ROOM_FULL')
        state = SeatState(slot=slot, nickname=nickname,
                          rejoin_code=_make_rejoin_code(),
                          player_id=player_id, avatar=avatar)
        self.slots[slot] = state
        self.total_scores.setdefault(slot, 0)
        if self.creator_slot is None:
            self.creator_slot = slot
        self._persist_seat(state)
        return slot, False, state

    def resume_by_code(self, rejoin_code: str) -> tuple[int, SeatState]:
        """WS 重连：持有原重进码者接管该连接位。"""
        for state in self.slots:
            if state is not None and state.rejoin_code == rejoin_code:
                if (self.storage is not None and state.player_id
                        and self.storage.is_banned('player', state.player_id)):
                    raise RoomError('BANNED')
                return state.slot, state
        raise RoomError('INVALID_REJOIN_CODE')

    def check_rejoin_rate(self, rejoin_code: str) -> bool:
        """重进码握手限速：30s 窗口内最多 5 次（防重连风暴 / 顶号刷码）。"""
        now = time.monotonic()
        attempts = [t for t in self._rejoin_attempts.get(rejoin_code, [])
                    if now - t < self._rejoin_window]
        self._rejoin_attempts[rejoin_code] = attempts
        return len(attempts) < self._rejoin_limit

    def note_rejoin_failure(self, rejoin_code: str) -> None:
        self._rejoin_attempts.setdefault(rejoin_code, []).append(time.monotonic())

    def reset_rejoin_rate(self, rejoin_code: str) -> None:
        self._rejoin_attempts.pop(rejoin_code, None)

    def release_seat(self, slot: int) -> None:
        """释放连接位。对局中释放 = 该位由「自动代打」接管，对局继续。"""
        if not 0 <= slot < PLAYER_SLOTS:
            raise RoomError('INVALID_SEAT')
        state = self.slots[slot]
        if state is None:
            raise RoomError('SEAT_EMPTY')
        self.slots[slot] = None
        self._forfeited_slots.add(slot)
        if self.storage is not None:
            self.storage.remove_room_seat(self.room_id, slot)
        if self.creator_slot == slot:
            next_slot = next((s for s, item in enumerate(self.slots) if item is not None), None)
            self.creator_slot = next_slot
        if self.status == 'lobby' and not self.has_humans():
            self.status = 'closed'

    def ready_seat(self, slot: int, ready: Optional[bool] = None) -> bool:
        state = self.slots[slot]
        if state is None:
            raise RoomError('SEAT_EMPTY')
        if self.status not in ('lobby', 'finished'):
            raise RoomError('ROOM_PLAYING')
        state.ready = (not state.ready) if ready is None else ready
        return state.ready

    def set_avatar(self, slot: int, avatar: str) -> None:
        state = self.slots[slot]
        if state is not None and avatar:
            state.avatar = avatar

    # ── 开局 / 轮换 ──────────────────────────────────────

    def _table_slot(self, table_seat: int) -> Optional[int]:
        if not 0 <= table_seat < TABLE_SEATS:
            return None
        slot = self.rotation[table_seat]
        return None if slot < 0 else slot

    def _table_seat_of_slot(self, slot: int) -> Optional[int]:
        """连接位 → 本局打牌座位；轮空/未入局返回 ``None``。"""
        for table_seat in range(TABLE_SEATS):
            if self.rotation[table_seat] == slot:
                return table_seat
        return None

    def _player_key(self, slot: int) -> str:
        state = self.slots[slot]
        if state is not None and state.player_id:
            return state.player_id
        return f'slot-{slot}'

    async def start(self) -> None:
        """开局：至少 4 个连接位、且这些位都 ready。"""
        if self.status == 'playing':
            raise RoomError('ALREADY_STARTED')
        if self.status == 'closed':
            raise RoomError('ROOM_CLOSED')
        occupied = self.occupied_slots()
        if len(occupied) < TABLE_SEATS:
            raise RoomError('NOT_ENOUGH_PLAYERS')
        if not all(self.slots[slot] is not None and self.slots[slot].ready
                   for slot in occupied):
            raise RoomError('NOT_ALL_READY')
        if self.creator_slot is None or self.slots[self.creator_slot] is None:
            raise RoomError('NOT_CREATOR')

        bench = next((s for s in range(PLAYER_SLOTS) if s not in occupied), -1)
        self.rotation = occupied[:TABLE_SEATS] + [bench]
        self.status = 'playing'
        self.match_finished = False
        self.match_started_at = time.monotonic()
        self.round_index = 0
        self.total_scores = {slot: 0 for slot in occupied}
        self._forfeited_slots = set()

        if self.storage is not None:
            self.match_id = self.storage.create_match(
                self.room_id, self.mode, RULESET_ID, self.match_length)
            self.storage.upsert_match_players(self.match_id, [
                {'seat': slot, 'player_id': self._player_key(slot),
                 'nickname': self.slots[slot].nickname if self.slots[slot] else f'座位{slot}'}
                for slot in occupied
            ])
            self.storage.update_room_status(self.room_id, 'playing')

        dealer = self._table_seat_of_slot(self.creator_slot) or 0
        await self._begin_round(dealer)

    async def _begin_round(self, dealer: int) -> None:
        """按当前 ``rotation`` 发牌开一局。"""
        player_keys = tuple(self._player_key(self.rotation[seat])
                            for seat in range(TABLE_SEATS))
        if self.random_seed is not None:
            rng = create_rng(self.random_seed + self.round_index)
        else:
            rng = random.Random()
        state = start_round(StartRoundOptions(
            seats=player_keys,
            dealer=dealer,
            cfg=self.cfg,
            rng=rng,
            round=self.round_index + 1,
            epoch=self.round_index + 1,
        ))
        # 累计分按连接位记，发牌时映射回本局座位。
        state = replace(state, scores=tuple(
            self.total_scores.get(self.rotation[seat], 0) for seat in range(TABLE_SEATS)))
        self.state = state
        self.round_index = state.round
        logger.bind(room_id=self.room_id).info(
            f"开局 第{state.round}局 庄家={dealer} 座位={self.rotation}")
        await self._broadcast_events((GameEvent(type='DRAW', seat=dealer,
                                                tile=state.hands[dealer].drawn_tile),),
                                     force_snapshot=True)
        self._schedule_deadline()

    # ── 动作 ────────────────────────────────────────────

    async def handle_client_message(self, slot: int, message: dict) -> tuple[bool, str]:
        """处理一条客户端消息。返回 ``(ok, error_code)``。"""
        kind = (message.get('kind') or 'action').lower()
        if kind == 'ping':
            await self.conn.send_to_seat(slot, {'kind': 'pong'})
            return True, ''
        if kind not in ('action', 'act'):
            return False, 'UNKNOWN_MESSAGE'

        return await self.apply_slot_action(
            slot,
            action_type=(message.get('type') or '').upper(),
            tile=message.get('tile'),
            req_id=int(message.get('reqId') or 0),
        )

    async def apply_slot_action(self, slot: int, action_type: str,
                                tile: Optional[int] = None,
                                req_id: int = 0) -> tuple[bool, str]:
        if self.state is None or self.status != 'playing':
            return False, 'ROOM_NOT_PLAYING'
        table_seat = self._table_seat_of_slot(slot)
        if table_seat is None:
            return False, 'SITTING_OUT'
        if slot in self._forfeited_slots:
            return False, 'SEAT_RELEASED'
        try:
            action = PlayerAction(type=action_type, seat=table_seat,  # type: ignore[arg-type]
                                  tile=tile, req_id=req_id)
        except TypeError:
            return False, 'INVALID_ACTION'

        now_ms = time.monotonic() * 1000.0
        try:
            result = apply_action(self.state, action, self.cfg, now_ms)
        except ValueError as exc:
            logger.bind(room_id=self.room_id, seat=table_seat).debug(f'动作被拒 {exc}')
            return False, str(exc)

        self.state = result.state
        await self._broadcast_events(result.events)
        await self._after_state_change(result.events)
        self._schedule_deadline()
        return True, ''

    # ── 自动代打（超时 / 已释放座位）────────────────────

    def _decision(self) -> tuple[float, bool] | None:
        """返回（距截止秒数, 是否鸣牌窗口）。"""
        state = self.state
        if state is None or self.status != 'playing':
            return None
        if state.phase == 'CLAIM_WINDOW' and state.claim is not None:
            delay = max(0.0, (state.claim.deadline_at - time.monotonic() * 1000.0) / 1000.0)
            return delay, True
        if state.phase == 'WAITING_PLAY':
            return max(0.0, self.turn_timeout), False
        return None

    def _schedule_deadline(self) -> None:
        self._cancel_deadline()
        decision = self._decision()
        if decision is None:
            return
        delay, _is_claim = decision
        loop = asyncio.get_event_loop()
        self._deadline_task = loop.create_task(self._auto_play_after(delay + 0.01))

    def _cancel_deadline(self) -> None:
        task, self._deadline_task = self._deadline_task, None
        if task is not None and not task.done():
            task.cancel()

    async def _auto_play_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if self.state is None or self.status != 'playing':
            return
        now_ms = time.monotonic() * 1000.0
        await self._auto_play(now_ms)

    async def _auto_play(self, now_ms: float) -> None:
        """超时/离线代打：鸣牌窗口一律 PASS，自己回合打掉刚摸的牌（能自摸就自摸）。"""
        state = self.state
        if state is None:
            return
        if state.phase == 'CLAIM_WINDOW' and state.claim is not None:
            for pending_seat in list(state.claim.pending):
                if self.state is None or self.state.claim is None:
                    return
                if pending_seat not in self.state.claim.pending:
                    continue
                slot = self._table_slot(pending_seat)
                if slot is None:
                    continue
                await self._submit_auto(slot, 'PASS', None, now_ms)
            return
        if state.phase == 'WAITING_PLAY':
            seat = state.turn
            slot = self._table_slot(seat)
            if slot is None:
                return
            hand = state.hands[seat]
            options = own_turn_options(hand, self.cfg)
            hu = next((option for option in options if option.type == 'HU'), None)
            if hu is not None:
                await self._submit_auto(slot, 'HU', hu.tile, now_ms)
                return
            await self._submit_auto(slot, 'DISCARD', self._auto_discard_tile(hand), now_ms)

    @staticmethod
    def _auto_discard_tile(hand: HandState) -> int:
        """代打出牌：优先打刚摸的那张，否则打最大的牌（确定性，便于复现）。"""
        if hand.drawn_tile is not None:
            return hand.drawn_tile
        for tile in range(len(hand.concealed) - 1, 10, -1):
            if hand.concealed[tile] > 0:
                return tile
        raise RoomError('AUTO_DISCARD_FAILED')

    async def _submit_auto(self, slot: int, action_type: str,
                           tile: Optional[int], now_ms: float) -> None:
        table_seat = self._table_seat_of_slot(slot)
        if table_seat is None:
            return
        try:
            action = PlayerAction(type=action_type, seat=table_seat,  # type: ignore[arg-type]
                                  tile=tile, req_id=0)
            result = apply_action(self.state, action, self.cfg, now_ms)
        except ValueError:
            return
        self.state = result.state
        await self._broadcast_events(result.events)
        await self._after_state_change(result.events)

    # ── 广播 / 快照 ──────────────────────────────────────

    def snapshot_for(self, slot: int) -> dict:
        table_seat = self._table_seat_of_slot(slot)
        viewer = Viewer(kind='player', seat=table_seat) if table_seat is not None \
            else Viewer(kind='spectator')
        payload = {
            'kind': 'state_snapshot',
            'roomId': self.room_id,
            'rulesetId': RULESET_ID,
            'matchLength': self.match_length,
            'matchFinished': self.match_finished,
            'seating': {
                # table seat → slot；轮空位单独给
                'table': [slot if slot >= 0 else None for slot in self.rotation[:TABLE_SEATS]],
                'sittingOut': self.rotation[TABLE_SEATS]
                if self.rotation[TABLE_SEATS] >= 0 else None,
            },
            'slots': [
                None if state is None else {
                    'slot': state.slot,
                    'nickname': state.nickname,
                    'avatar': state.avatar,
                    'ready': state.ready,
                    'connected': self.conn.is_connected(state.slot),
                }
                for state in self.slots
            ],
            'totalScores': {str(slot): score for slot, score in self.total_scores.items()},
        }
        if self.state is not None:
            payload.update(project_view(self.state, viewer))
        else:
            payload.update({'phase': 'LOBBY', 'round': 0})
        return payload

    async def broadcast_snapshots(self) -> None:
        for slot in self.occupied_slots():
            await self.conn.send_to_seat(slot, self.snapshot_for(slot))

    async def _broadcast_events(self, events: tuple[GameEvent, ...], *,
                                force_snapshot: bool = False) -> None:
        public: list[dict] = []
        for event in events:
            if event.type == 'DISCARD':
                public.append({'kind': 'discard_bc', 'seat': event.seat, 'tile': event.tile})
            elif event.type == 'PENG':
                public.append({'kind': 'meld_bc', 'seat': event.seat,
                               'meldKind': 'PENG', 'tile': event.tile})
            elif event.type == 'GANG':
                public.append({'kind': 'meld_bc', 'seat': event.seat,
                               'meldKind': event.gang_kind, 'tile': event.tile})
            elif event.type == 'DRAW':
                # 摸到的牌只有本人可见 —— 逐座位下发，绝不进公共广播。
                slot = self._table_slot(event.seat) if event.seat is not None else None
                if slot is not None and event.tile is not None:
                    await self.conn.send_to_seat(
                        slot, {'kind': 'draw', 'tile': event.tile, 'seat': event.seat})
            elif event.type in ('HU', 'QIANG_GANG_HU'):
                public.append({
                    'kind': 'hu_result',
                    'winners': [{'seat': winner.seat, 'zimo': winner.zimo,
                                 'tags': list(winner.tags)} for winner in event.winners],
                    'loserSeat': event.loser_seat,
                    'gangSeat': event.gang_seat,
                })
            elif event.type == 'SETTLE':
                public.append({'kind': 'settle', 'deltas': list(event.deltas),
                               'detail': [
                                   {'seat': item.seat, 'tags': list(item.tags),
                                    'zimo': item.zimo, 'gangShang': item.gang_shang,
                                    'fan': item.fan, 'unit': item.unit,
                                    'income': item.income}
                                   for item in event.detail]})
            elif event.type == 'HUANG_ZHUANG':
                public.append({'kind': 'huang_zhuang'})

        for message in public:
            self.conn.broadcast(message)
        if public or force_snapshot:
            await self.broadcast_snapshots()

    # ── 结算 / 换座 / 整场推进 ──────────────────────────

    async def _after_state_change(self, events: tuple[GameEvent, ...]) -> None:
        if self.state is None:
            return
        if not any(event.type == 'SETTLE' for event in events):
            return
        settle_event = next(event for event in events if event.type == 'SETTLE')
        # 1) 累计分按连接位记账（座位号会变，分数不能跟着座位走）
        for seat in range(TABLE_SEATS):
            slot = self.rotation[seat]
            if slot >= 0:
                self.total_scores[slot] = self.total_scores.get(slot, 0) + \
                    settle_event.deltas[seat]
        # 2) 落库本局
        self._persist_round(settle_event)
        # 3) 整场是否结束
        if self.round_index >= self.match_length:
            await self._finish_match()
            return
        # 4) 换座 + 开下一局
        outcome = self.state.last_outcome
        if outcome is None:
            return
        seating = next_round_seating(self.state, outcome)
        self._rotate(seating['sitting_out'])
        new_dealer = seating['dealer']
        if self.pace:
            await asyncio.sleep(self.pace)
        await self._announce_seating()
        await self._begin_round(new_dealer)

    def _rotate(self, sitting_out_table_seat: int) -> None:
        """换座：本局 ``sitting_out_table_seat`` 的人下场，原轮空者顶上这个位置。"""
        bench = self.rotation[TABLE_SEATS]
        if bench < 0:
            return  # 只有 4 个人，没人轮换
        outgoing = self.rotation[sitting_out_table_seat]
        self.rotation[sitting_out_table_seat] = bench
        self.rotation[TABLE_SEATS] = outgoing
        logger.bind(room_id=self.room_id).info(
            f"换座 座位{sitting_out_table_seat} 下场 → 轮空位={outgoing}，"
            f'新轮换={self.rotation}')

    async def _announce_seating(self) -> None:
        self.conn.broadcast({
            'kind': 'seating_changed',
            'table': [slot if slot >= 0 else None for slot in self.rotation[:TABLE_SEATS]],
            'sittingOut': self.rotation[TABLE_SEATS]
            if self.rotation[TABLE_SEATS] >= 0 else None,
        })

    async def _finish_match(self) -> None:
        self.status = 'finished'
        self.match_finished = True
        if self._deadline_task is not None:
            self._cancel_deadline()
        self.conn.broadcast({
            'kind': 'match_finished',
            'totalScores': {str(slot): score for slot, score in self.total_scores.items()},
        })
        if self.storage is not None and self.match_id is not None:
            final = [{'slot': slot, 'score': score}
                     for slot, score in sorted(self.total_scores.items())]
            try:
                self.storage.finish_match(self.match_id, final)
                self.storage.update_room_status(self.room_id, 'finished')
            except Exception:
                logger.bind(room_id=self.room_id).exception('整场落库失败')
        await self.broadcast_snapshots()

    def _persist_round(self, settle_event: GameEvent) -> None:
        if self.storage is None or self.match_id is None:
            return
        payload = {
            'round': self.round_index,
            'rulesetId': RULESET_ID,
            'deltas': list(settle_event.deltas),
            # 座位每局会换，所以按玩家 key 记一份，统计不随换座漂移。
            'deltasByPlayer': {
                self._player_key(self.rotation[seat]): settle_event.deltas[seat]
                for seat in range(TABLE_SEATS) if self.rotation[seat] >= 0
            },
            'winnerPlayers': [
                self._player_key(self.rotation[item.seat])
                for item in settle_event.detail if self.rotation[item.seat] >= 0
            ],
            'detail': [
                {'seat': item.seat, 'tags': list(item.tags), 'zimo': item.zimo,
                 'gangShang': item.gang_shang, 'fan': item.fan,
                 'unit': item.unit, 'income': item.income}
                for item in settle_event.detail
            ],
        }
        try:
            self.storage.insert_round_result(self.match_id, payload)
        except Exception:
            logger.bind(room_id=self.room_id).exception('本局结算落库失败')

    def _persist_seat(self, state: SeatState) -> None:
        if self.storage is None:
            return
        try:
            self.storage.upsert_room_seat(
                self.room_id, state.slot, state.nickname,
                state.rejoin_code, state.player_id)
        except Exception:
            logger.bind(room_id=self.room_id).exception('座位落库失败')

    # ── 连接事件 ────────────────────────────────────────

    def on_connect(self, slot: int) -> None:
        self._forfeited_slots.discard(slot)

    def on_disconnect(self, slot: int) -> None:
        logger.bind(room_id=self.room_id).info(f'连接位 {slot} 断线，转自动代打')
        if self.state is not None and self.status == 'playing':
            self._schedule_deadline()

    def close(self) -> None:
        self.status = 'closed'
        self._cancel_deadline()
        if self._round_task is not None and not self._round_task.done():
            self._round_task.cancel()

    def force_finish(self, reason: str = 'stalled') -> bool:
        if self._forced or self.status != 'playing':
            return False
        self._forced = True
        logger.bind(room_id=self.room_id).warning(f'强制收尾对局 {reason}')
        self.status = 'finished'
        self.match_finished = True
        self._cancel_deadline()
        return True

    async def finalize_forced(self) -> None:
        self.conn.broadcast({'kind': 'match_finished', 'forced': True,
                             'totalScores': {str(slot): score
                                             for slot, score in self.total_scores.items()}})
        if self.storage is not None:
            try:
                self.storage.update_room_status(self.room_id, 'finished')
            except Exception:
                logger.bind(room_id=self.room_id).exception('强制收尾落库失败')


def match_id_of(room: RoomSession) -> Optional[str]:
    return room.match_id


def match_finished_of(room: RoomSession) -> bool:
    return room.match_finished


def match_phase_of(room: RoomSession) -> str:
    if room.status != 'playing':
        return room.status
    return room.state.phase if room.state is not None else 'playing'


def build_snapshot(room: RoomSession, slot: int) -> dict:
    """旧接口名保留：WS 层与测试都按这个名字取快照。"""
    return room.snapshot_for(slot)


def is_match_stalled(room: RoomSession, now: Optional[float] = None) -> bool:
    if room.status != 'playing' or room.match_started_at is None:
        return False
    current = now if now is not None else time.monotonic()
    return current - room.match_started_at > ROOM_MATCH_MAX


# ── 房间注册表 ──────────────────────────────────────────

class RoomRegistry:
    """内存房间注册表（REST 创建、WS 读取；测试通过它注入/清理房间）。"""

    def __init__(self) -> None:
        self._rooms: dict[str, RoomSession] = {}
        self._last_sweep = 0.0
        self._sweep_interval = 60.0

    def create(self, room_id: str, **kwargs) -> RoomSession:
        self._maybe_sweep()
        if room_id in self._rooms:
            raise RoomError('ROOM_EXISTS')
        room = RoomSession(room_id, **kwargs)
        self._rooms[room_id] = room
        return room

    def get(self, room_id: str) -> Optional[RoomSession]:
        self._maybe_sweep()
        return self._rooms.get(room_id)

    def peek(self, room_id: str) -> Optional[RoomSession]:
        return self._rooms.get(room_id)

    def count(self, ruleset_id: Optional[str] = None) -> int:
        if ruleset_id is None:
            return len(self._rooms)
        return sum(room.ruleset_id == ruleset_id for room in list(self._rooms.values()))

    def find_room_by_player(self, player_id: str) -> Optional[RoomSession]:
        for room in self._rooms.values():
            for state in room.slots:
                if state is not None and state.player_id == player_id:
                    return room
        return None

    def remove(self, room_id: str) -> None:
        room = self._rooms.pop(room_id, None)
        if room is not None:
            room.close()

    def clear(self) -> None:
        for room_id in list(self._rooms):
            self.remove(room_id)

    def _maybe_sweep(self) -> None:
        now = time.monotonic()
        if now - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = now
        self.sweep_expired(now)

    def sweep_expired(self, now: Optional[float] = None) -> list[str]:
        current = now if now is not None else time.monotonic()
        expired = [room_id for room_id, room in list(self._rooms.items())
                   if room.is_expired(current)]
        for room_id in expired:
            logger.bind(room_id=room_id).info('房间到期回收')
            self.remove(room_id)
        return expired

    def sweep_stalled(self, now: Optional[float] = None, *,
                      allow_cancel: bool = False) -> list[str]:
        finished: list[str] = []
        for room_id, room in list(self._rooms.items()):
            if not is_match_stalled(room, now):
                continue
            if room.force_finish('stalled'):
                finished.append(room_id)
        return finished


room_registry = RoomRegistry()


async def _room_watchdog_loop(registry: RoomRegistry) -> None:
    logger.info(f'房间看门狗启动 interval={ROOM_WATCHDOG_INTERVAL}s '
                f'match_max={ROOM_MATCH_MAX}s')
    while True:
        await asyncio.sleep(ROOM_WATCHDOG_INTERVAL)
        try:
            for room_id in registry.sweep_stalled():
                room = registry.peek(room_id)
                if room is not None:
                    await room.finalize_forced()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('房间看门狗清扫异常（已跳过，继续运行）')


def start_room_watchdog(registry: Optional[RoomRegistry] = None) -> Optional[asyncio.Task]:
    if ROOM_WATCHDOG_INTERVAL <= 0:
        logger.info('房间看门狗未启动（ROOM_WATCHDOG_INTERVAL<=0）')
        return None
    return asyncio.create_task(_room_watchdog_loop(registry or room_registry))
