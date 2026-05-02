

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')
app = Celery('my_site')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()












# import os
# from celery import Celery, bootsteps
# import kombu


# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')

# app = Celery('my_site')

# app.config_from_object('django.conf:settings', namespace='CELERY')

# app.autodiscover_tasks()

    
    
# with app.pool.acquire(block=True) as conn:
#         exchange = kombu.Exchange(
#             name='myexchange',
#             type='direct',
#             durable=True,
#             channel=conn
#         )
#         exchange.declare()
        
#         queue = kombu.Queue(
#             name='myqueue',
#             exchange=exchange,
#             routing_key='mykey',
#             channel=conn,
#             message_ttl=600,
#             queue_arguments = {
#                     'x-queue-type':'classic',
#             },
#             durable=True
#         )
#         queue.declare()
        
        


# class MyConsumerStep(bootsteps.ConsumerStep):

#     def get_consumers(self, channel):
#         return [kombu.Consumer(
#             channel,
#             queues=[queue],
#             callbacks=[self.handle_message],
#             accept=['json']
#         )]

#     def handle_message(self, body, message):
#         print(f"Received message: {body}")
#         message.ack()
        
        
# app.steps['consumer'].add(MyConsumerStep)    


# # @app.task(bind=True)
# # def debug_task(self):
# #     print(f'Request: {self.request!r}')