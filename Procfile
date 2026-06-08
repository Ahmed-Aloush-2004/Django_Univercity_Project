


web1: waitress-serve --listen=127.0.0.1:8001 my_site.wsgi:application
web2: waitress-serve --listen=127.0.0.1:8002 my_site.wsgi:application
web3: waitress-serve --listen=127.0.0.1:8003 my_site.wsgi:application
worker: celery -A my_site worker -l info -P gevent
nginx: C:\nginx\nginx.exe -p C:\nginx\ -c C:\Users\NITRO\Desktop\my_django_project\nginx.conf
