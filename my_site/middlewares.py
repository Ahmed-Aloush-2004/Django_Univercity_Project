from django.http import JsonResponse
import logging

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