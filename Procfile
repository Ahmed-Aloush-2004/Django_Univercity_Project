


web1: waitress-serve --listen=127.0.0.1:8001 my_site.wsgi:application
web2: waitress-serve --listen=127.0.0.1:8002 my_site.wsgi:application
web3: waitress-serve --listen=127.0.0.1:8003 my_site.wsgi:application
#worker: celery -A my_site worker -l info -P gevent
worker: celery -A my_site worker -l info --pool=solo
nginx: C:\nginx\nginx.exe -p C:\nginx\ -c C:\Users\NITRO\Desktop\my_django_project\nginx.conf


#web1: opentelemetry-instrument waitress-serve --listen=127.0.0.1:8001 my_site.wsgi:application
#web2: opentelemetry-instrument waitress-serve --listen=127.0.0.1:8002 my_site.wsgi:application
#web3: opentelemetry-instrument waitress-serve --listen=127.0.0.1:8003 my_site.wsgi:application
#worker: opentelemetry-instrument celery -A my_site worker -l info --pool=solo
#nginx: C:\nginx\nginx.exe -p C:\nginx\ -c C:\Users\NITRO\Desktop\my_django_project\nginx.conf