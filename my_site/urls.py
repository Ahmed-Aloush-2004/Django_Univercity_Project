"""
URL configuration for my_site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from health_check.views import HealthCheckView

from apps.reports.views import GenerateDailyReportAPIView, GenerateWeeklyReportAPIView


def trigger_error(request):
    division_by_zero = 1 / 0

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/products/', include('apps.products.urls')), 
    path('api/orders/', include('apps.orders.urls')), 
    path('api/users/', include('apps.users.urls')),    
    path('api/cart/', include('apps.carts.urls')),
    
    path('api/reports/daily/', GenerateDailyReportAPIView.as_view(), name='trigger-daily-report'),
    path('api/reports/weekly/', GenerateWeeklyReportAPIView.as_view(), name='trigger-weekly-report'),

    
    path('prometheus/', include('django_prometheus.urls')),      
    path('sentry-debug/', trigger_error),
    
    path('health/', HealthCheckView.as_view(
        checks=[
            "health_check.Database",
            "health_check.Cache",
            "health_check.Storage",
        ]
    )),     
    

]