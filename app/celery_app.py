from celery import Celery

from app.config import REDIS_URL

celery_app = Celery(
    "subspyder",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.enum_tasks",
        "app.tasks.resolve_tasks",
        "app.tasks.techdetect_tasks",
        "app.tasks.httpx_tasks",
        "app.tasks.finalize_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)
