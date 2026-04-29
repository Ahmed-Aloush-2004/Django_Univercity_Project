from django.http import JsonResponse
import logging
import time
from redis import Redis


logger = logging.getLogger(__name__)

class GlobalExceptionHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # الكود هنا ينفذ قبل الـ View
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        # يتم استدعاء هذه الدالة فقط عند حدوث Exception في الـ View
        logger.error(f"Unhandled Exception: {str(exception)}", exc_info=True)
        
        return JsonResponse({
            'error': 'Internal Server Error',
            'message': str(exception) if True else "Something went wrong" # اجعلها False في الإنتاج
        }, status=500)
        
        
        


# تأكد من تشغيل Redis سيرفر
redis_client = Redis(host='localhost', port=6379, db=0)

class RequestCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # الحصول على الوقت الحالي بالثواني
        current_time = int(time.time())
        key = f"total_requests:{current_time}"
        
        # زيادة العداد في Redis
        redis_client.incr(key)
        # جعل المفتاح ينتهي بعد 5 دقائق (300 ثانية) لتوفير المساحة
        redis_client.expire(key, 300)
        
        # طباعة العدد في الـ Terminal للمراقبة (اختياري)
        count = redis_client.get(key)
        print(f"Requests per second ({current_time}): {count.decode('utf-8')}")

        response = self.get_response(request)
        return response       