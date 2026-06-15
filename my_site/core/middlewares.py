import os
import psutil
import threading
import logging
import time

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger("apps.middleware")
process = psutil.Process(os.getpid())

MAX_CONCURRENT_REQUESTS = 100

_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)
_active_count = 0
_count_lock = threading.Lock()



class CapacityControlMiddleware:

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



# class RequestMonitoringMiddleware:
#     SLOW_REQUEST_THRESHOLD_MS = 500
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):

#         start_time = time.perf_counter()
#         response = self.get_response(request)
#         duration_ms = (time.perf_counter() - start_time) * 1000
#         cpu_percent = psutil.cpu_percent(interval=None)
#         memory_mb = (
#             process.memory_info().rss
#             / 1024
#             / 1024
#         )
#         with _count_lock:
#             active_requests = _active_count

#         logger.info(
#             "REQUEST | %s %s | STATUS=%d | "
#             "TIME=%.2fms | CPU=%.2f%% | RAM=%.2fMB | ACTIVE=%d",
#             request.method,
#             request.path,
#             response.status_code,
#             duration_ms,
#             cpu_percent,
#             memory_mb,
#             active_requests,
#         )

#         if duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
#             logger.warning(
#                 "SLOW REQUEST | %s %s | %.2fms",
#                 request.method,
#                 request.path,
#                 duration_ms,
#             )

#         return response

import time
import logging
from django.http import JsonResponse
from system_metrics import get_process_metrics 

logger = logging.getLogger("apps.middleware")

class RequestMonitoringMiddleware:
    # عتبة الطلبات البطيئة: نصف ثانية (500 ملي ثانية)
    SLOW_REQUEST_THRESHOLD_MS = 500 

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. نقطة البداية (AOP Before Advice): بدء حساب الوقت
        start_time = time.perf_counter()
        
        # تمرير الطلب للـ View الأساسي ليشتغل
        response = self.get_response(request)
        
        # 2. نقطة النهاية (AOP After Advice): حساب الوقت المستغرق
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # استدعاء المقاييس المركزية من ملف system_metrics.py
        metrics = get_process_metrics()
        
        # تسجيل البيانات الشاملة بنبض السيرفر
        logger.info(
            "REQUEST | %s %s | STATUS=%d | TIME=%.2fms | CPU=%.2f%% | RAM=%.2fMB | THREADS=%d",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            metrics["cpu_percent"],
            metrics["memory_mb"],
            metrics["threads"]
        )

        # إطلاق جرس إنذار إذا تبين أن الطلب مخنوق وبطيء (تحديد الاختناقات)
        if duration_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "🚨 SLOW REQUEST DETECTED | %s %s | Took: %.2fms",
                request.method,
                request.path,
                duration_ms,
            )

        return response