from celery import Celery
from app.config import REDIS_URL

celery_app = Celery(
    "tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.indexing"]
)

celery_app.conf.task_routes = {
    "app.tasks.indexing.*": {"queue": "indexing"}
}