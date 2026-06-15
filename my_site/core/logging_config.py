# my_site/logging_config.py
import os

def get_logging_config(base_dir):
    LOG_DIR = os.path.join(base_dir, "logs")
    os.makedirs(LOG_DIR, exist_ok=True)

    APPS = ["products", "middleware", "orders", "carts", "users"]

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "errors_file": {
            "class": "logging.FileHandler",
            "filename": os.path.join(LOG_DIR, "errors.log"),
            "formatter": "verbose",
            "level": "ERROR",
        },
    }

    for app in APPS:
        handlers[f"{app}_file"] = {
            "class": "logging.FileHandler",
            "filename": os.path.join(LOG_DIR, f"{app}.log"),
            "formatter": "verbose",
        }

    loggers = {}
    for app in APPS:
        loggers[f"apps.{app}"] = {
            "handlers": ["console", f"{app}_file", "errors_file"],
            "level": "DEBUG",
            "propagate": False,
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "[{asctime}] {levelname} {name} {message}",
                "style": "{",
            },
        },
        "handlers": handlers,
        "loggers": loggers,
    }