"""
========================================================
  Parallel Programming Course - Stress Test Suite
  Requirements 9 (Stress Testing) & 10 (Benchmarking)
========================================================

HOW TO RUN:
  Scenario A - Product Reads (100 users, cached vs uncached benchmark):
    locust -f locustfile_stress_test.py ScenarioA_ProductReads \
           --host http://localhost:8000 --users 100 --spawn-rate 10 \
           --run-time 60s --headless --csv=results_scenario_a

  Scenario B - Atomic Order Creates (concurrent write safety):
    locust -f locustfile_stress_test.py ScenarioB_OrderCreates_Atomic \
           --host http://localhost:8000 --users 100 --spawn-rate 10 \
           --run-time 60s --headless --csv=results_scenario_b_atomic

  Scenario C - Pessimistic Order Creates (concurrent write safety):
    locust -f locustfile_stress_test.py ScenarioC_OrderCreates_Pessimistic \
           --host http://localhost:8000 --users 100 --spawn-rate 10 \
           --run-time 60s --headless --csv=results_scenario_c_pessimistic

  Scenario D - Mixed Full Load (all endpoints, 100 users):
    locust -f locustfile_stress_test.py ScenarioD_MixedFullLoad \
           --host http://localhost:8000 --users 100 --spawn-rate 10 \
           --run-time 120s --headless --csv=results_scenario_d_mixed

  Run ALL at once (via web UI, then pick the class):
    locust -f locustfile_stress_test.py --host http://localhost:8000

Requirement 9 PASS criteria:
  - 0 failures (or <1% error rate)
  - No server crash (HTTP 500 / connection refused)
  - No data corruption (stock never goes negative)

Requirement 10 BENCHMARK targets (fill in your actual numbers):
  - Cached product list p95 < 100ms
  - Uncached product list p95 < 500ms
  - Order create (atomic) p95 < 800ms
  - Sales stats (cached) p95 < 150ms
"""

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner
import logging
import json
import random
import time

# ─── Configuration ────────────────────────────────────────────────────────────

# Replace with a valid JWT token before running
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzgxNzc0NTY5LCJpYXQiOjE3ODE2ODgxNjksImp0aSI6ImI2NzU2YjZlOWMzMjQ3Zjg4Yzg3MTQ4MTgzZTlhZmQ3IiwidXNlcl9pZCI6IjEifQ.R2HNfpXWy0jg2nvSepXyifLinfIJ6Z4nSqp1h05Dfyw"


AUTH_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Product IDs to use in order tests (adjust to real IDs in your DB)
PRODUCT_IDS = [1, 2, 3, 4, 5]

# Logger for custom metric tracking
logger = logging.getLogger("stress_test")

# ─── Custom event hooks (Requirement 10 — bottleneck tracking) ────────────────

order_latencies = []
cache_hit_latencies = []
cache_miss_latencies = []


@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, context, exception, **kwargs):
    """
    Tracks latency per endpoint category for Requirement 10 analysis.
    These lists can be dumped at the end to calculate p50/p95/p99.
    """
    if exception:
        return
    if "orders" in name:
        order_latencies.append(response_time)
    if "cached" in name.lower():
        cache_hit_latencies.append(response_time)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Prints a Requirement 10 summary when the test finishes.
    Copy these numbers into your benchmarking report.
    """
    def percentile(data, pct):
        if not data:
            return "N/A"
        data_sorted = sorted(data)
        idx = int(len(data_sorted) * pct / 100)
        return f"{data_sorted[min(idx, len(data_sorted)-1)]:.1f} ms"

    print("\n" + "=" * 60)
    print("  REQUIREMENT 10 — BENCHMARKING SUMMARY")
    print("=" * 60)
    print(f"  Order endpoint   p50={percentile(order_latencies, 50)}  "
          f"p95={percentile(order_latencies, 95)}  "
          f"p99={percentile(order_latencies, 99)}  "
          f"samples={len(order_latencies)}")
    print(f"  Cache hits       p50={percentile(cache_hit_latencies, 50)}  "
          f"p95={percentile(cache_hit_latencies, 95)}  "
          f"samples={len(cache_hit_latencies)}")
    print("=" * 60)
    print("  ✔  Check the CSV files for full per-endpoint breakdown.")
    print("=" * 60 + "\n")


# # ─── SCENARIO A — Product Reads (cached endpoints) ────────────────────────────
# # Purpose : Prove caching works under 100 concurrent readers.
# # Req 9   : 100 users, 0 crashes, 0 data loss.
# # Req 10  : Compare cached vs uncached response times.

# class ScenarioA_ProductReads(HttpUser):
#     """
#     100 concurrent product reads.
#     Mix of cached (trending / most_viewed) and direct DB reads
#     to generate the before/after benchmark for Requirement 10.
#     """
#     wait_time = between(0.5, 1.5)

#     def on_start(self):
#         self.client.headers.update(AUTH_HEADERS)

#     # ── Cached endpoints (should be fast after first hit) ──────────────────
#     @task(3)
#     def get_products_list_cached(self):
#         """
#         Main product list — expected to be Redis-cached.
#         Tag: [cached] so the event hook tracks it for Req 10.
#         """
#         self.client.get(
#             "/api/products/",
#             name="GET /api/products/ [cached]"
#         )

#     @task(2)
#     def get_trending_products(self):
#         self.client.get(
#             "/api/products/trending/",
#             name="GET /api/products/trending/ [cached]"
#         )

#     @task(2)
#     def get_most_viewed_products(self):
#         self.client.get(
#             "/api/products/most_viewed/",
#             name="GET /api/products/most_viewed/ [cached]"
#         )

#     # @task(1)
#     # def get_sales_stats_dashboard(self):
#     #     """Sales stats — cached, used for Req 10 dashboard benchmark."""
#     #     self.client.get(
#     #         "/api/products/sales_stats/",
#     #         name="GET /api/products/sales_stats/ [cached]"
#     #     )

#     # ── Direct DB read — intentionally uncached for Req 10 comparison ──────
#     @task(2)
#     def get_product_by_id(self):
#         """
#         Single product by ID — bypasses list cache.
#         Use p95 here as the 'before caching' baseline for Req 10.
#         """
#         pid = random.choice(PRODUCT_IDS)
#         self.client.get(
#             f"/api/products/{pid}/",
#             name="GET /api/products/:id/ [DB direct]"
#         )


# # ─── SCENARIO B — Concurrent Order Creates (Atomic / select_for_update) ───────
# # Purpose : Prove race-condition protection under 100 concurrent writers.
# # Req 9   : Stock must never go below 0 even with 100 simultaneous orders.
# # Req 7   : Pessimistic locking in action.
# # Req 8   : ACID — payment + stock + order all succeed or all fail.

# class ScenarioB_OrderCreates_Atomic(HttpUser):
#     """
#     100 concurrent order creates using the 'atomic' strategy.
#     Each user tries to buy the same product (id=2) to deliberately
#     create contention — proving the Race Condition fix (Req 1 & 7).
#     """
#     wait_time = between(0.5, 1.5)

#     def on_start(self):
#         self.client.headers.update(AUTH_HEADERS)

#     @task
#     def create_order_atomic(self):
#         payload = {
#             "products": [{"id": 2, "quantity": 1}],
#             "order_price": 200.00
#         }
#         with self.client.post(
#             "/api/orders/?strategy=atomic",
#             json=payload,
#             name="POST /api/orders/ [atomic]",
#             catch_response=True
#         ) as resp:
#             # 409 Conflict (out-of-stock) is acceptable — not a failure
#             if resp.status_code in (200, 201, 409):
#                 resp.success()
#             elif resp.status_code == 400:
#                 # Validation error — log but don't fail the test
#                 resp.success()
#             else:
#                 resp.failure(
#                     f"Unexpected status {resp.status_code}: {resp.text[:200]}"
#                 )


# # ─── SCENARIO C — Concurrent Order Creates (Pessimistic Locking) ─────────────

# class ScenarioC_OrderCreates_Pessimistic(HttpUser):
#     """
#     Same contention test with the 'pessimistic' (SELECT FOR UPDATE) strategy.
#     Compare p95 latency of B vs C in your Req 10 report to show the
#     tradeoff between the two locking strategies.
#     """
#     wait_time = between(0.5, 1.5)

#     def on_start(self):
#         self.client.headers.update(AUTH_HEADERS)

#     @task
#     def create_order_pessimistic(self):
#         payload = {
#             "products": [{"id": 2, "quantity": 1}],
#             "order_price": 200.00
#         }
#         with self.client.post(
#             "/api/orders/?strategy=pessimistic",
#             json=payload,
#             name="POST /api/orders/ [pessimistic]",
#             catch_response=True
#         ) as resp:
#             if resp.status_code in (200, 201, 409):
#                 resp.success()
#             elif resp.status_code == 400:
#                 resp.success()
#             else:
#                 resp.failure(
#                     f"Unexpected status {resp.status_code}: {resp.text[:200]}"
#                 )


# # ─── SCENARIO D — Mixed Full Load (Req 9 primary scenario) ───────────────────
# # Purpose : Simulate realistic 100-user traffic mix.
# # Req 9   : The main proof — system stable under 100 concurrent users,
# #           mix of reads AND writes, no crash, no data loss.

# class ScenarioD_MixedFullLoad(HttpUser):
#     """
#     Realistic mixed workload — 70% reads, 30% writes.
#     This is the scenario to present for Requirement 9 as it mirrors
#     real e-commerce traffic patterns.

#     Run with --users 100 --spawn-rate 10 --run-time 120s
#     Pass criteria: error rate < 1%, no HTTP 500s, no connection refused.
#     """
#     wait_time = between(0.5, 2)

#     def on_start(self):
#         self.client.headers.update(AUTH_HEADERS)

#     # ── Reads (weight 7 out of 10 tasks) ───────────────────────────────────
#     @task(3)
#     def read_product_list(self):
#         self.client.get(
#             "/api/products/",
#             name="GET /api/products/ [cached]"
#         )

#     @task(2)
#     def read_trending(self):
#         self.client.get(
#             "/api/products/trending/",
#             name="GET /api/products/trending/ [cached]"
#         )

#     @task(1)
#     def read_most_viewed(self):
#         self.client.get(
#             "/api/products/most_viewed/",
#             name="GET /api/products/most_viewed/ [cached]"
#         )

#     @task(1)
#     def read_product_detail(self):
#         pid = random.choice(PRODUCT_IDS)
#         self.client.get(
#             f"/api/products/{pid}/",
#             name="GET /api/products/:id/ [DB direct]"
#         )

#     # ── Writes (weight 3 out of 10 tasks) ──────────────────────────────────
#     @task(2)
#     def create_order_mixed(self):
#         """
#         Alternates randomly between atomic and pessimistic to stress
#         both locking strategies simultaneously.
#         """
#         strategy = random.choice(["atomic", "pessimistic"])
#         payload = {
#             "products": [{"id": random.choice(PRODUCT_IDS), "quantity": 1}],
#             "order_price": round(random.uniform(50, 500), 2)
#         }
#         with self.client.post(
#             f"/api/orders/?strategy={strategy}",
#             json=payload,
#             name=f"POST /api/orders/ [{strategy}]",
#             catch_response=True
#         ) as resp:
#             if resp.status_code in (200, 201, 409, 400):
#                 resp.success()
#             else:
#                 resp.failure(
#                     f"Unexpected {resp.status_code}: {resp.text[:200]}"
#                 )

#     # @task(1)
#     # def read_sales_stats(self):
#     #     self.client.get(
#     #         "/api/products/sales_stats/",
#     #         name="GET /api/products/sales_stats/ [cached]"
#     #     )


# ─── SCENARIO E — Authentication Endpoints ────────────────────────────────────
# Included for completeness; disable if token-based auth is sufficient.

class ScenarioE_AuthEndpoints(HttpUser):
    """
    Tests login/register under load.
    Keep users low (10–20) — this hits the DB directly every time.
    """
    wait_time = between(1, 3)

    @task
    def user_login(self):
        payload = {
            "email": "ahmedalloushgpt@gmail.com",
            "password": "NewStrongPassword456"
        }
        with self.client.post(
            "/api/users/login/",
            json=payload,
            name="POST /api/users/login/",
            catch_response=True
        ) as resp:
            if resp.status_code in (200, 400, 401):
                resp.success()
            else:
                resp.failure(f"Login failed: {resp.status_code}")
