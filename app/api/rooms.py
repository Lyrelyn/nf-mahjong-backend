"""房间 REST API —— 南丰麻将房间生命周期（创建 / 加入 / 离开 / 准备 / 开局 / 关闭）。

与旧版（莲花）的差别：单一玩法（``nanfeng``）、**5 个连接位**（4 人打 + 1 人轮空买码）、
没有大模型座位预留、没有二次元角色。

认证（首版轻量）：座位级操作带 ``rejoinCode`` 校验，防止误操作他人座位。
路由全部定义为同步函数 → FastAPI 自动放线程池，不阻塞事件循环；只有 ``start`` 是 async，
因为它要创建对局任务并绑定事件循环。
"""

import os
import secrets
from threading import Lock
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from app.api.deps import AuthenticatedUser, require_wakudemo_login
from app.game.nanfeng_room import (
    PLAYER_SLOTS,
    RULESET_ID,
    RoomError,
    RoomSession,
    match_finished_of,
    match_id_of,
    match_phase_of,
    room_registry,
)
from app.storage.db import storage

router = APIRouter(prefix='/api/rooms', tags=['rooms'])

#: 同时存在的房间数上限（单一玩法，环境变量覆盖）。
MAX_ROOMS = int(os.environ.get('ROOM_MAX', '4'))
# REST 同步路由在线程池执行：限额检查与注册必须串行，防止并发建房超额。
_room_creation_lock = Lock()

#: 6 位房间码字母表：去掉易混淆字符（0/O、1/I、U）
_ROOM_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def _new_room_id() -> str:
    while True:
        code = ''.join(secrets.choice(_ROOM_ALPHABET) for _ in range(6))
        if room_registry.get(code) is None:
            return code


def _room_or_404(room_id: str) -> RoomSession:
    room = room_registry.get(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail={'code': 'ROOM_NOT_FOUND'})
    return room


def _safe_avatar_url(value: str | None) -> str:
    """只接受 http(s) 头像 URL（防御性校验）。"""
    if not value or len(value) > 2048:
        return ''
    if not value.startswith(('https://', 'http://')):
        return ''
    return value


def _verify_seat(room: RoomSession, seat: int, rejoin_code: str) -> None:
    """座位级操作身份校验：该连接位存在且重进码匹配。"""
    state = room.slots[seat] if 0 <= seat < PLAYER_SLOTS else None
    if state is None:
        raise HTTPException(status_code=404, detail={'code': 'SEAT_EMPTY'})
    if state.rejoin_code != rejoin_code:
        raise HTTPException(status_code=403, detail={'code': 'INVALID_REJOIN_CODE'})


def _room_response(room: RoomSession) -> dict:
    sitting_out = room.rotation[PLAYER_SLOTS - 1]
    return {
        'roomId': room.room_id,
        'mode': room.mode,
        'rulesetId': room.ruleset_id,
        'matchLength': room.match_length,
        'capacity': room.capacity,
        'status': room.status,
        'matchId': match_id_of(room),
        'matchFinished': match_finished_of(room),
        'phase': match_phase_of(room),
        'creatorSeat': room.creator_slot,
        'timeLimitSeconds': room.lifetime,
        'seats': [
            None if state is None else {
                'seat': state.slot,
                'nickname': state.nickname,
                'avatar': state.avatar,
                'ready': state.ready,
                'connected': room.conn.is_connected(state.slot),
            }
            for state in room.slots
        ],
        'sittingOutSeat': sitting_out if sitting_out >= 0 else None,
        'totalScores': {str(slot): score for slot, score in room.total_scores.items()},
    }


# ─── 请求模型 ────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    mode: Literal['east', 'hanchan'] = 'east'
    # 连接位固定 5 个（4 打 + 1 轮空）；旧客户端可能传 2/3/4，一律按 5 处理。
    capacity: int = Field(default=PLAYER_SLOTS, ge=2, le=PLAYER_SLOTS)
    # 场次长度（庄数）：4 / 8 / 16。
    matchLength: Literal[4, 8, 16] = 4
    # 只接受南丰；旧客户端的 lotus*/yaotong 会被 409 拒绝。
    rulesetId: str = RULESET_ID
    playerId: Optional[str] = Field(default=None, max_length=64)  # 已废弃：身份由登录会话推导


class JoinRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=20)
    playerId: Optional[str] = Field(default=None, max_length=64)
    avatar: Optional[str] = Field(default=None, max_length=2048)


class SeatActionRequest(BaseModel):
    seat: int = Field(ge=0, le=PLAYER_SLOTS - 1)
    rejoinCode: str
    ready: Optional[bool] = None


# ─── 路由 ────────────────────────────────────────────────

@router.post('')
def create_room(body: CreateRoomRequest,
                user: AuthenticatedUser = Depends(require_wakudemo_login)) -> dict:
    """创建房间（需登录）：签发 6 位房间码。

    防重复占房：该登录身份已在某个房间占座 → ``ALREADY_IN_ROOM``。
    """
    if body.rulesetId not in (RULESET_ID, ''):
        raise HTTPException(status_code=409, detail={'code': 'UNKNOWN_RULESET'})
    if room_registry.find_room_by_player(user.player_id) is not None:
        raise HTTPException(status_code=409, detail={'code': 'ALREADY_IN_ROOM'})
    room_registry.sweep_expired()
    room_registry.sweep_stalled()
    room_registry.sweep_expired()
    with _room_creation_lock:
        if room_registry.count(RULESET_ID) >= MAX_ROOMS:
            raise HTTPException(status_code=409, detail={'code': 'ROOM_LIMIT_REACHED'})
        room_id = _new_room_id()
        try:
            room = room_registry.create(
                room_id, mode=body.mode, storage=storage,
                match_length=body.matchLength)
        except RoomError as exc:
            logger.bind(room_id=room_id).warning(f'创建房间失败 {exc}')
            raise HTTPException(status_code=409, detail={'code': str(exc)})
    storage.create_room(room_id, body.mode, PLAYER_SLOTS, RULESET_ID, body.matchLength)
    storage.update_room_status(room_id, 'lobby')
    logger.bind(room_id=room_id).info(
        f"创建房间 mode={body.mode} matchLength={body.matchLength}")
    return _room_response(room)


@router.get('/meta')
def get_room_meta(_: AuthenticatedUser = Depends(require_wakudemo_login)) -> dict:
    """房间容量（需登录）：``active`` 在册房间数、``max`` 上限。"""
    room_registry.sweep_expired()
    return {'active': room_registry.count(RULESET_ID), 'max': MAX_ROOMS,
            'rulesetId': RULESET_ID, 'slots': PLAYER_SLOTS}


@router.get('/{room_id}')
def get_room(room_id: str,
             _: AuthenticatedUser = Depends(require_wakudemo_login)) -> dict:
    return _room_response(_room_or_404(room_id))


@router.post('/{room_id}/join')
def join_room(room_id: str, body: JoinRequest,
              user: AuthenticatedUser = Depends(require_wakudemo_login)) -> dict:
    """加入：占第一个空连接位并签发 ``rejoinCode``。

    同一账号回到原房间时取回原连接位与重进码；跨房占座 → ``ALREADY_IN_ROOM``。
    """
    room = _room_or_404(room_id)
    occupied_room = room_registry.find_room_by_player(user.player_id)
    if occupied_room is not None and occupied_room is not room:
        raise HTTPException(status_code=409, detail={'code': 'ALREADY_IN_ROOM'})
    if room.status not in ('lobby', 'finished') and not (
            occupied_room is room and room.status == 'playing'):
        raise HTTPException(status_code=409, detail={'code': 'ROOM_CLOSED'})
    try:
        seat, is_rejoin, state = room.join_or_rejoin(
            body.nickname, player_id=user.player_id,
            avatar=_safe_avatar_url(body.avatar) or _safe_avatar_url(user.avatar_url))
    except RoomError as exc:
        logger.bind(room_id=room_id).warning(f'加入房间失败 {exc}')
        raise HTTPException(status_code=409, detail={'code': str(exc)})
    logger.bind(room_id=room_id, seat=seat).info(
        f'加入房间 昵称={state.nickname} 重进={is_rejoin} player_id={state.player_id}')
    return {
        'roomId': room.room_id,
        'seat': seat,
        'nickname': state.nickname,
        'avatar': state.avatar,
        'rejoinCode': state.rejoin_code,
        'playerId': state.player_id,
        'rejoin': is_rejoin,
    }


@router.post('/{room_id}/leave')
def leave_room(room_id: str, body: SeatActionRequest) -> dict:
    """离开：释放连接位（带 rejoinCode 身份校验）。

    对局中释放 = 该位转「自动代打」，对局继续；全员离开则解散房间。
    """
    room = _room_or_404(room_id)
    _verify_seat(room, body.seat, body.rejoinCode)
    room.release_seat(body.seat)
    if not room.has_humans():
        room_registry.remove(room_id)
    logger.bind(room_id=room_id, seat=body.seat).info('离开房间')
    return {'roomId': room.room_id, 'seat': body.seat, 'left': True}


@router.post('/{room_id}/ready')
def ready_room(room_id: str, body: SeatActionRequest) -> dict:
    """准备 / 取消准备：返回该连接位当前准备态。"""
    room = _room_or_404(room_id)
    _verify_seat(room, body.seat, body.rejoinCode)
    try:
        ready = room.ready_seat(body.seat, body.ready)
    except RoomError as exc:
        raise HTTPException(status_code=409, detail={'code': str(exc)})
    logger.bind(room_id=room_id, seat=body.seat).debug(f'准备态 ready={ready}')
    return {'roomId': room.room_id, 'seat': body.seat, 'ready': ready}


@router.post('/{room_id}/start')
async def start_room(room_id: str,
                     user: AuthenticatedUser = Depends(require_wakudemo_login)) -> dict:
    """开局：房主触发，要求至少 4 个连接位且都已准备。

    async 以便对局任务创建在事件循环线程（与 WS 处理器一致）。
    """
    room = _room_or_404(room_id)
    creator = room.slots[room.creator_slot] if room.creator_slot is not None else None
    if creator is None or creator.player_id != user.player_id:
        raise HTTPException(status_code=403, detail={'code': 'NOT_CREATOR'})
    try:
        await room.start()
    except RoomError as exc:
        logger.bind(room_id=room_id).warning(f'开局失败 {exc}')
        raise HTTPException(status_code=409, detail={'code': str(exc)})
    logger.bind(room_id=room_id).info(f'开局触发 status={room.status}')
    return {'roomId': room.room_id, 'status': room.status}


@router.delete('/{room_id}')
def close_room(room_id: str, body: SeatActionRequest) -> dict:
    """关闭房间：仅创建者可执行（带 rejoinCode 身份校验）。"""
    room = _room_or_404(room_id)
    _verify_seat(room, body.seat, body.rejoinCode)
    if room.creator_slot != body.seat:
        raise HTTPException(status_code=403, detail={'code': 'NOT_CREATOR'})
    if room.status == 'playing':
        raise HTTPException(status_code=409, detail={'code': 'ROOM_PLAYING'})
    logger.bind(room_id=room_id, seat=body.seat).info('关闭房间')
    room_registry.remove(room_id)
    return {'roomId': room_id, 'closed': True}
