"""WebSocket 游戏端点 —— ``/ws/room/{room_id}?rejoin_code=...``

流程：
1. 握手鉴权：query 携带 ``rejoin_code``（REST join 签发）→ ``resume_by_code`` 恢复连接位；
2. 绑定连接位：注册出站队列 + 发送任务，下发 ``rejoin_ok`` + 全量快照；
3. 开局由 REST ``POST /api/rooms/{id}/start`` 显式触发；
4. 接收循环：客户端动作 → ``handle_client_message``（服务端权威校验）→ 拒绝回错误；
5. 断线：标记 + 自动代打；发送任务随连接关闭终止。

发送采用「出站队列 + 后台发送任务」：广播/请求只入队，慢/断客户端不阻塞对局主循环。
"""

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.game.nanfeng_room import (
    PLAYER_SLOTS,
    RoomError,
    match_id_of,
    room_registry,
)

router = APIRouter()


async def _sender(queue: asyncio.Queue, websocket: WebSocket, room_id: str, seat: int) -> None:
    """后台发送任务：从出站队列取消息真正 send_json；连接断开即结束。"""
    while True:
        message = await queue.get()
        await websocket.send_json(message)


@router.websocket('/ws/room/{room_id}')
async def game_ws(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    start = time.perf_counter()

    rejoin_code = (websocket.query_params.get('rejoin_code') or '').strip()

    room = room_registry.get(room_id)
    if room is None:
        logger.bind(room_id=room_id).warning('WS 握手拒绝 ROOM_NOT_FOUND')
        await websocket.send_json({'kind': 'rejoin_err', 'code': 'ROOM_NOT_FOUND'})
        await websocket.close()
        return
    if not rejoin_code:
        logger.bind(room_id=room_id).warning('WS 握手拒绝 REJOIN_CODE_REQUIRED')
        await websocket.send_json({'kind': 'rejoin_err', 'code': 'REJOIN_CODE_REQUIRED'})
        await websocket.close()
        return
    # 重进码限速：30s 窗口内同一码最多 5 次握手（防重连风暴 / 顶号刷码）
    if not room.check_rejoin_rate(rejoin_code):
        logger.bind(room_id=room_id).warning('WS 握手拒绝 REJOIN_RATE_LIMITED')
        await websocket.send_json({'kind': 'rejoin_err', 'code': 'REJOIN_RATE_LIMITED'})
        await websocket.close()
        return
    try:
        seat, state = room.resume_by_code(rejoin_code)
    except RoomError as exc:
        room.note_rejoin_failure(rejoin_code)
        logger.bind(room_id=room_id).warning(f'WS 握手拒绝 {exc}')
        await websocket.send_json({'kind': 'rejoin_err', 'code': str(exc)})
        await websocket.close()
        return
    room.reset_rejoin_rate(rejoin_code)  # 成功恢复连接位：清零该码失败计数

    queue: asyncio.Queue = asyncio.Queue()
    sender = asyncio.create_task(_sender(queue, websocket, room_id, seat))
    previous_socket = room.conn.register(seat, queue, sender, websocket)
    room.on_connect(seat)
    if previous_socket is not None:
        try:
            await previous_socket.close()
        except Exception:
            # 旧连接可能已被浏览器关闭；新连接已经成为唯一有效连接。
            pass
    logger.bind(room_id=room_id, seat=seat).info(f'WS 连接 昵称={state.nickname}')

    await room.conn.send_to_seat(seat, {
        'kind': 'rejoin_ok',
        'seat': seat,
        'rejoin': True,
        'roomId': room.room_id,
        'rulesetId': room.ruleset_id,
        'matchLength': room.match_length,
        'matchId': match_id_of(room),
        'nickname': state.nickname,
        'avatar': state.avatar,
        'rejoinCode': state.rejoin_code,
        'slots': PLAYER_SLOTS,
    })
    await room.conn.send_to_seat(seat, room.snapshot_for(seat))

    try:
        while True:
            message = await websocket.receive_json()
            if not room.conn.is_current_connection(seat, queue):
                await websocket.close()
                break
            ok, err = await room.handle_client_message(seat, message)
            if not ok:
                logger.bind(room_id=room_id, seat=seat).warning(f'消息被拒 {err}')
                await room.conn.send_to_seat(seat, {'kind': 'error', 'code': err})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        duration = time.perf_counter() - start
        logger.bind(room_id=room_id, seat=seat).info(f'WS 断开 连接时长={duration:.1f}s')
        if room.conn.is_current_connection(seat, queue):
            room.on_disconnect(seat)
            room.conn.unregister(seat, queue)
        if not sender.done():
            sender.cancel()
