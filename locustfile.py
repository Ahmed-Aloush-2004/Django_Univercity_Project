from locust import HttpUser, task, between

class ECommerceUser(HttpUser):
    wait_time = between(1, 3) 

    @task
    def view_products(self):
        self.client.get("/api/products/")
    

# from locust import HttpUser, task, between

# class ImminentBuyersUser(HttpUser):
#     wait_time = between(0.01, 0.1)

#     @task
#     def buy_same_product(self):
#         token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzgxNjM4ODM4LCJpYXQiOjE3ODE1NTI0MzgsImp0aSI6IjExYTBhZTFmMzA5YzRkNThhYjk2OTFhOGM4NTY0YjQ5IiwidXNlcl9pZCI6IjIifQ.vYZDNJR9NKRWK-3G7xfKLi61egEmXfV6e2iUQ04H5Sw"
        
#         headers = {
#             "Content-Type": "application/json",
#             "Authorization": f"Bearer {token}"
#         }
        
#         payload = {
#             "products": [
#                 {"id": 3157, "quantity": 1},
#                 {"id":  3158, "quantity": 1}
#             ],
#             "order_price": 4.00,
#             "status": "pending"
#         }
        
#         self.client.post("/api/orders/", json=payload, headers=headers)