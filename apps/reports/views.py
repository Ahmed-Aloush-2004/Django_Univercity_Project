from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.core.cache import cache
import logging

from rest_framework import status, permissions


from apps.common.tasks import daily_sales_batch_processing, generate_weekly_report


logger = logging.getLogger("apps.orders")

class GenerateDailyReportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
            flag_key = "daily_report_is_running"
            is_first_click = cache.add(flag_key, "true", timeout=3600)
            
            if not is_first_click:
                logger.warning("Double-click prevented: Daily report already running.")
                return Response(
                    {"error": "The daily report is already being generated. Please check your background tasks."},
                    status=429
                )
            
            daily_sales_batch_processing.delay()
            
            logger.info("Daily report task dispatched by Admin: %s", request.user.username)
            return Response(
                {"success": "Daily report generation has started in the background."},
                status=202
            )




class GenerateWeeklyReportAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

        
    def post(self, request):
        flag_key = "weekly_report_is_running"
        
        is_first_click = cache.add(flag_key, "true", timeout=3600)
        
        if not is_first_click:
            logger.warning("Double-click prevented: Weekly report already running.")
            return Response(
                {"error": "The weekly report is already being generated and emailed. Please wait."},
                status=429
            )
        
        generate_weekly_report.delay()
        
        logger.info("Weekly report task dispatched by Admin: %s", request.user.username)
        return Response(
            {"success": "Weekly report generation started. It will be emailed shortly."},
            status=202
        )           
            
            