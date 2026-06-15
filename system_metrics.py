# my_site/system_metrics.py
import os
import psutil
process = psutil.Process(os.getpid())
def get_process_metrics():
    return {
        "cpu_percent": process.cpu_percent(),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "threads": process.num_threads(),
    }