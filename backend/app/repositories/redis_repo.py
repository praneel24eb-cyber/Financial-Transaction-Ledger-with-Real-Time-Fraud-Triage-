import logging
import time
from typing import List, Optional
import redis
from backend.app.config import settings

logger = logging.getLogger(__name__)

class RedisRepository:
    def __init__(self):
        self.enabled = False
        try:
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True,
                socket_timeout=1.0
            )
            self.client.ping()
            self.enabled = True
            logger.info("Connected to Redis 7+")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}). Using in-memory fallback for velocity counters.")
            self._memory_counters = {}
            self._memory_sets = {}

    def increment_velocity(self, account_id: int, window_seconds: int = 3600) -> int:
        key = f"velocity:{account_id}:{window_seconds}s"
        if self.enabled:
            try:
                val = self.client.incr(key)
                if val == 1:
                    self.client.expire(key, window_seconds)
                return val
            except Exception as e:
                logger.warning(f"Redis incr error: {e}")

        # In-memory fallback
        now = time.time()
        if key not in self._memory_counters:
            self._memory_counters[key] = []
        # Filter timestamps within window
        self._memory_counters[key] = [t for t in self._memory_counters[key] if now - t <= window_seconds]
        self._memory_counters[key].append(now)
        return len(self._memory_counters[key])

    def get_velocity(self, account_id: int, window_seconds: int = 3600) -> int:
        key = f"velocity:{account_id}:{window_seconds}s"
        if self.enabled:
            try:
                val = self.client.get(key)
                return int(val) if val else 0
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

        # In-memory fallback
        now = time.time()
        if key not in self._memory_counters:
            return 0
        timestamps = [t for t in self._memory_counters[key] if now - t <= window_seconds]
        return len(timestamps)

    def add_recent_device(self, account_id: int, device_id: int):
        key = f"device:recent:{account_id}"
        if self.enabled:
            try:
                self.client.sadd(key, device_id)
                self.client.expire(key, 86400)
                return
            except Exception as e:
                logger.warning(f"Redis sadd error: {e}")

        # In-memory fallback
        if key not in self._memory_sets:
            self._memory_sets[key] = set()
        self._memory_sets[key].add(device_id)

    def is_known_device(self, account_id: int, device_id: int) -> bool:
        key = f"device:recent:{account_id}"
        if self.enabled:
            try:
                return bool(self.client.sismember(key, device_id))
            except Exception as e:
                logger.warning(f"Redis sismember error: {e}")

        # In-memory fallback
        return device_id in self._memory_sets.get(key, set())

redis_repo = RedisRepository()
