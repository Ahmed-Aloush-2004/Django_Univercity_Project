import os
import psutil
import threading
import logging
import time

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger("apps.middleware")
process = psutil.Process(os.getpid())

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










# # الإعدادات الثابتة للسعة
# MAX_CONCURRENT_REQUESTS = 100  # السعة الإجمالية للـ Cluster كاملة
# REDIS_COUNTER_KEY = "capacity_control_active_requests"
# LOCK_TIMEOUT = 30  # أمان لمنع حجز السعة للأبد في حال انهار طلب ما مفاجأة (30 ثانية)

# class DistributedCapacityControlMiddleware:
#     """
#     Requirement 2 — Resource Management & Capacity Control (Distributed).

#     يستخدم الكاش الموزع (Redis) لفرض حد أقصى على عدد الطلبات المتزامنة
#     التي تعالجها كافة سيرفرات Django (8001, 8002, 8003) في نفس الوقت.
#     """

#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         # 1. زيادة العداد الذري داخل Redis للتحقق من السعة الحالية
#         # ملاحظة: بعض بيئات Redis تدعم الـ INCR بشكل ذري مريح جداً
#         try:
#             # نقوم بزيادة العداد
#             current_active = cache.incr(REDIS_COUNTER_KEY, delta=1)
#         except ValueError:
#             # في حال لم يكن المفتاح موجوداً في Redis مسبقاً، نقوم بتهيئته
#             cache.set(REDIS_COUNTER_KEY, 1, timeout=None)
#             current_active = 1

#         # 2. التحقق مما إذا كنا قد تخطينا السعة المسموحة
#         if current_active > MAX_CONCURRENT_REQUESTS:
#             logger.warning(
#                 "Distributed capacity limit reached (%d/%d concurrent requests). Returning 503.",
#                 current_active,
#                 MAX_CONCURRENT_REQUESTS,
#             )
#             # بما أننا تجاوزنا السعة، يجب أن ننقص العداد فوراً لأننا سنرفض الطلب
#             cache.decr(REDIS_COUNTER_KEY, delta=1)
            
#             return JsonResponse(
#                 {
#                     "error": "Server cluster is at full capacity. Please retry in a moment.",
#                     "max_concurrent_requests": MAX_CONCURRENT_REQUESTS,
#                 },
#                 status=503,
#             )

#         # 3. معالجة الطلب في حال وجود سعة متاحة
#         try:
#             response = self.get_response(request)
#             return response
#         finally:
#             # 4. دائماً وأبداً يتم إنقاص العداد عند خروج الطلب لتفريغ مساحة للطلب التالي
#             try:
#                 cache.decr(REDIS_COUNTER_KEY, delta=1)
#             except Exception as e:
#                 logger.error("Failed to decrement capacity counter in Redis: %s", str(e))










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

# class RequestRateMonitorMiddleware:
#     """
#     Requirement 10 — Benchmarking & Bottleneck Analysis.

#     Aspect-Oriented Programming (AOP) applied to performance monitoring:
#     this middleware is a cross-cutting concern — it wraps every request
#     without modifying any view, measuring response time and request rate
#     in one place.

#     What it records per request:
#       - Response time (ms) logged at DEBUG level.
#       - Per-second request counter stored in Redis (key: req_rate:<unix_ts>).
#         Each key expires after 5 minutes, keeping Redis memory usage bounded.
#       - Slow-request warning logged at WARNING level for responses > 500 ms.

#     How to query the rate:
#         from redis import Redis
#         r = Redis()
#         r.get(f"req_rate:{int(time.time())}")   # requests in this second

#     Synchronization point: Redis INCR is atomic — safe across all Gunicorn
#     workers and all Nginx-balanced Django instances simultaneously.
#     """

#     SLOW_THRESHOLD_MS = 500

#     def __init__(self, get_response):
#         self.get_response = get_response
#         try:
#             from redis import Redis
#             self._redis = Redis(
#                 host='127.0.0.1', port=6379, db=0,
#                 socket_connect_timeout=1,
#                 socket_timeout=1,
#             )
#         except Exception:
#             self._redis = None

#     def __call__(self, request):
#         start = time.perf_counter()

#         response = self.get_response(request)

#         elapsed_ms = (time.perf_counter() - start) * 1000

#         # Log response time for every request (AOP cross-cutting concern)
#         logger.debug(
#             "AOP | %s %s → %d | %.1f ms",
#             request.method, request.path, response.status_code, elapsed_ms,
#         )

#         # Warn on slow requests so bottlenecks surface in the log
#         if elapsed_ms > self.SLOW_THRESHOLD_MS:
#             logger.warning(
#                 "SLOW REQUEST | %s %s → %d | %.1f ms (threshold: %d ms)",
#                 request.method, request.path, response.status_code,
#                 elapsed_ms, self.SLOW_THRESHOLD_MS,
#             )

#         # Atomic per-second counter in Redis (safe across all workers)
#         if self._redis:
#             try:
#                 key = f"req_rate:{int(time.time())}"
#                 self._redis.incr(key)
#                 self._redis.expire(key, 300)   # auto-expire after 5 minutes
#             except Exception:
#                 pass  # never let monitoring break the response

#         return response
    
    


class RequestMonitoringMiddleware:

    SLOW_REQUEST_THRESHOLD_MS = 500

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        start_time = time.perf_counter()

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # cpu_percent = process.cpu_percent()
        cpu_percent = psutil.cpu_percent(interval=None)

        memory_mb = (
            process.memory_info().rss
            / 1024
            / 1024
        )

        with _count_lock:
            active_requests = _active_count

        logger.info(
            "REQUEST | %s %s | STATUS=%d | "
            "TIME=%.2fms | CPU=%.2f%% | RAM=%.2fMB | ACTIVE=%d",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            cpu_percent,
            memory_mb,
            active_requests,
        )

        if duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "SLOW REQUEST | %s %s | %.2fms",
                request.method,
                request.path,
                duration_ms,
            )

        return response
    
    
    
    
    
    
    
    
    
    
    
    
    
    