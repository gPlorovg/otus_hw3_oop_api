import time

import redis


class RedisStore:
    """Redis-backed store with retry logic and timeouts

    Provides two access modes:
    - ``get`` / ``set``: persistent storage — raises on unavailability
    - ``cache_get`` / ``cache_set``: best-effort cache — silently ignores errors
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        timeout: float = 3.0,
        max_retries: int = 3,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: redis.Redis | None = None

    def _connect(self) -> None:
        self._client = redis.Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            socket_timeout=self.timeout,
            socket_connect_timeout=self.timeout,
        )

    def _execute(self, method: str, *args, **kwargs):
        """Run a Redis command with retry on connection errors"""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if self._client is None:
                    self._connect()
                return getattr(self._client, method)(*args, **kwargs)
            except (redis.ConnectionError, redis.TimeoutError) as exc:
                last_exc = exc
                self._client = None
                if attempt < self.max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
        raise last_exc

    @staticmethod
    def _decode(value) -> str | None:
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else value

    def get(self, key: str) -> str | None:
        """Persistent get — raises if the store is unreachable"""
        return self._decode(self._execute("get", key))

    def set(self, key: str, value, ttl: int | None = None) -> None:
        """Persistent set — raises if the store is unreachable"""
        if ttl:
            self._execute("setex", key, int(ttl), str(value))
        else:
            self._execute("set", key, str(value))

    def cache_get(self, key: str) -> str | None:
        """Cache get — returns None on any error"""
        try:
            return self._decode(self._execute("get", key))
        except Exception:
            return None

    def cache_set(self, key: str, value, ttl: int) -> None:
        """Cache set — silently ignores errors"""
        try:
            self._execute("setex", key, int(ttl), str(value))
        except Exception:
            pass
