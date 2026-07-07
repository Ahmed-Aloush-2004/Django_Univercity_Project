from locust import HttpUser, task, between

# User Defined Variables from JMeter
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzgxOTkyNDQ3LCJpYXQiOjE3ODE5MDYwNDcsImp0aSI6ImIzOGRiZjRmMTRiYjQyODVhNTI5YmEyMTFjYTkzODUzIiwidXNlcl9pZCI6IjIifQ.zkFfL2gPGoiYKfXN6ZcFAHTonuzh0AJO3y4-feCVsuY"

# class ScenarioA_ProductReads(HttpUser):
#     """Scenario A — 100 concurrent product reads"""
#     wait_time = between(1, 2) # Ramp-up buffer
    
#     def on_start(self):
#         # Set default headers for all requests in this scenario
#         self.client.headers.update({
#             "Authorization": f"Bearer {TOKEN}"
#         })

    # @task
    # def get_products(self):
    #     self.client.get("/api/products/", name="GET /api/products/ (cached)")

    # @task
    # def get_product_by_id(self):
    #     self.client.get("/api/products/2/", name="GET /api/products/id")

    # @task
    # def get_trending_products(self):
    #     self.client.get("/api/products/trending/", name="GET /api/products/trending")

    # @task
    # def get_most_viewed_products(self):
    #     self.client.get("/api/products/most_viewed/", name="GET /api/products/most_viewed")


class ScenarioB_OrderCreatesAtomic(HttpUser):
    """Scenario B — 100 concurrent order creates (Atomic strategy) - Disabled in JMX"""
    wait_time = between(1, 2)

    def on_start(self):
        self.client.headers.update({
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        })

    @task
    def create_order_atomic(self):
        payload = {"products": [{"id": 3159, "quantity": 1}], "order_price": 2.00}
        self.client.post("/api/orders/", json=payload, name="POST /api/orders/?strategy=atomic")


# class ScenarioC_OrderCreatesPessimistic(HttpUser):
#     """Scenario C — 100 concurrent order creates (Pessimistic strategy) - Disabled in JMX"""
#     wait_time = between(1, 2)

#     def on_start(self):
#         self.client.headers.update({
#             "Authorization": f"Bearer {TOKEN}",
#             "Content-Type": "application/json"
#         })

#     @task
#     def create_order_pessimistic(self):
#         payload = {"products": [{"id": 2, "quantity": 1}], "order_price": 200.00}
#         self.client.post("/api/orders/?strategy=pessimistic", json=payload, name="POST /api/orders/?strategy=pessimistic")


# class UsersGroup(HttpUser):
#     """Users Group - Disabled in JMX"""
#     wait_time = between(1, 2)

#     def on_start(self):
#         self.client.headers.update({
#             "Content-Type": "application/json",
#             "Accept": "application/json"
#         })

#     @task
#     def admin_login(self):
#         payload = {"email": "nouran@gmail.com", "password": "12345"}
#         # Note: JMeter had this pointing to port 8000, ensure your Locust --host matches the intended target
#         self.client.post("/api/users/login/", json=payload, name="Admin Login")

#     @task
#     def sign_up(self):
#         payload = {
#             "email": "ahmedalloushgpt@gmail.com",
#             "password": "passPassword456",
#             "username": "ahmedalloush2004"
#         }
#         self.client.post("/api/users/register/", json=payload, name="Sign Up")

#     @task
#     def user_login(self):
#         payload = {
#             "email": "ahmedalloushgpt@gmail.com",
#             "password": "NewStrongPassword456"
#         }
#         self.client.post("/api/users/login/", json=payload, name="Login")


# class GenerateReportsGroup(HttpUser):
#     """Generate Reports - Disabled in JMX"""
#     wait_time = between(1, 2)

#     def on_start(self):
#         self.client.headers.update({
#             "Content-Type": "application/json",
#             "Accept": "application/json",
#             "Authorization": f"Bearer {TOKEN}"
#         })

#     @task
#     def generate_daily_report(self):
#         self.client.post("/api/reports/daily/", name="Generate Daily Report")

#     @task
#     def generate_weekly_report(self):
#         self.client.post("/api/reports/weekly/", name="Generate Weekly Report")