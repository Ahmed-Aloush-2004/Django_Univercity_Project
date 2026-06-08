import threading
import logging
import time

from django.http import JsonResponse

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Requirement 2 — Capacity Control (concurrent request limiter)      #
# ------------------------------------------------------------------ #

# Maximum number of requests processed simultaneously.
# Requests beyond this cap get HTTP 503 immediately — no queueing.
# This prevents DB connection pool exhaustion and memory collapse
# under traffic spikes ("not too much") while keeping the limit high
# enough that normal load is never throttled ("not too little").
MAX_CONCURRENT_REQUESTS = 50

_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)
_active_count = 0
_count_lock = threading.Lock()


class CapacityControlMiddleware:
    """
    Requirement 2 — Resource Management & Capacity Control.

    Uses a threading.Semaphore to cap parallel request processing.
    When all slots are taken the middleware returns HTTP 503 without
    reaching the view layer, protecting the DB connection pool.

    Synchronization point: threading.Semaphore (non-blocking acquire).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        acquired = _semaphore.acquire(blocking=False)

        if not acquired:
            logger.warning(
                "Capacity limit reached (%d concurrent requests). Returning 503.",
                MAX_CONCURRENT_REQUESTS,
            )
            return JsonResponse(
                {
                    "error": "Server is at full capacity. Please retry in a moment.",
                    "max_concurrent_requests": MAX_CONCURRENT_REQUESTS,
                },
                status=503,
            )

        global _active_count
        with _count_lock:
            _active_count += 1

        try:
            return self.get_response(request)
        finally:
            _semaphore.release()
            with _count_lock:
                _active_count -= 1


# ------------------------------------------------------------------ #
#  Global Exception Handler                                            #
# ------------------------------------------------------------------ #

class GlobalExceptionHandlerMiddleware:
    """
    Catches any unhandled exception that escapes the view layer and
    returns a structured JSON 500 response instead of Django's HTML page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        logger.error(
            "Unhandled exception on %s: %s", request.path, exception, exc_info=True
        )
        return JsonResponse(
            {"error": "Internal server error.", "detail": str(exception)},
            status=500,
        )


# ------------------------------------------------------------------ #
#  Requirement 10 — Request Rate Monitor (AOP-style performance probe) #
# ------------------------------------------------------------------ #

class RequestRateMonitorMiddleware:
    """
    Requirement 10 — Benchmarking & Bottleneck Analysis.

    Aspect-Oriented Programming (AOP) applied to performance monitoring:
    this middleware is a cross-cutting concern — it wraps every request
    without modifying any view, measuring response time and request rate
    in one place.

    What it records per request:
      - Response time (ms) logged at DEBUG level.
      - Per-second request counter stored in Redis (key: req_rate:<unix_ts>).
        Each key expires after 5 minutes, keeping Redis memory usage bounded.
      - Slow-request warning logged at WARNING level for responses > 500 ms.

    How to query the rate:
        from redis import Redis
        r = Redis()
        r.get(f"req_rate:{int(time.time())}")   # requests in this second

    Synchronization point: Redis INCR is atomic — safe across all Gunicorn
    workers and all Nginx-balanced Django instances simultaneously.
    """

    SLOW_THRESHOLD_MS = 500

    def __init__(self, get_response):
        self.get_response = get_response
        try:
            from redis import Redis
            self._redis = Redis(
                host='127.0.0.1', port=6379, db=0,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception:
            self._redis = None

    def __call__(self, request):
        start = time.perf_counter()

        response = self.get_response(request)

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Log response time for every request (AOP cross-cutting concern)
        logger.debug(
            "AOP | %s %s → %d | %.1f ms",
            request.method, request.path, response.status_code, elapsed_ms,
        )

        # Warn on slow requests so bottlenecks surface in the log
        if elapsed_ms > self.SLOW_THRESHOLD_MS:
            logger.warning(
                "SLOW REQUEST | %s %s → %d | %.1f ms (threshold: %d ms)",
                request.method, request.path, response.status_code,
                elapsed_ms, self.SLOW_THRESHOLD_MS,
            )

        # Atomic per-second counter in Redis (safe across all workers)
        if self._redis:
            try:
                key = f"req_rate:{int(time.time())}"
                self._redis.incr(key)
                self._redis.expire(key, 300)   # auto-expire after 5 minutes
            except Exception:
                pass  # never let monitoring break the response

        return response