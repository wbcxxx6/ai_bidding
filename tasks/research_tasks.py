import logging

from core.celery_app import celery_app

LOGGER = logging.getLogger(__name__)


@celery_app.task(name="tasks.research_tasks.run_research_async", bind=True, max_retries=2)
def run_research_async(self, task_id):
    from services.deep_research_service import run_research_task

    LOGGER.info("celery research task started task_id=%s", task_id)
    try:
        result = run_research_task(task_id)
        return {"status": "succeeded", "task_id": task_id, "report_id": (result.get("report") or {}).get("id")}
    except Exception as exc:
        LOGGER.exception("celery research task failed task_id=%s", task_id)
        raise self.retry(exc=exc, countdown=10)
