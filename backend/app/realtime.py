from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator, Dict, List

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from .config import get_settings

settings = get_settings()
CHANNEL_PREFIX = "automation-events"
_local_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None


def register_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _channel_for_tenant(tenant_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{tenant_id}"


def publish_tenant_event(tenant_id: str, event_type: str, payload: dict) -> None:
    message = json.dumps({"type": event_type, "payload": payload})
    channel = _channel_for_tenant(tenant_id)
    try:
        Redis.from_url(settings.redis_url).publish(channel, message)
    except RedisError:
        if not _loop or not _local_subscribers[channel]:
            return
        for queue in list(_local_subscribers[channel]):
            _loop.call_soon_threadsafe(queue.put_nowait, json.loads(message))


async def _local_event_stream(channel: str) -> AsyncGenerator[dict, None]:
    queue: asyncio.Queue = asyncio.Queue()
    _local_subscribers[channel].append(queue)
    try:
        while True:
            payload = await queue.get()
            yield payload
    finally:
        _local_subscribers[channel].remove(queue)


async def stream_tenant_events(tenant_id: str) -> AsyncGenerator[dict, None]:
    channel = _channel_for_tenant(tenant_id)
    try:
        redis = AsyncRedis.from_url(settings.redis_url)
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            yield json.loads(data)
    except RedisError:
        async for payload in _local_event_stream(channel):
            yield payload
    finally:
        if "pubsub" in locals():
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        if "redis" in locals():
            await redis.close()
