from rest_framework.pagination import PageNumberPagination

class ProductsPagination(PageNumberPagination):  
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class OrderPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100