import os

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "")

celery_app = None

try:
    from celery import Celery

    if CELERY_BROKER_URL:
        celery_app = Celery(
            "ai_bidding",
            broker=CELERY_BROKER_URL,
            backend=CELERY_RESULT_BACKEND or "redis://127.0.0.1:6379/1",
        )

        celery_app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="Asia/Shanghai",
            enable_utc=True,
            task_track_started=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
            task_soft_time_limit=300,
            task_time_limit=600,
            task_default_queue="default",
            task_routes={
                "tasks.research_tasks.*": {"queue": "research"},
            },
        )

        celery_app.autodiscover_tasks(["tasks"])
except ImportError:
    pass


def is_async_enabled():
    return celery_app is not None and bool(CELERY_BROKER_URL)
