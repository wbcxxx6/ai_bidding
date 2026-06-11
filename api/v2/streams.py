import json

from flask import Blueprint, Response

from services.v2.chapter_generation_service import stream_chapter_generation
from services.v2.project_generation_service import run_project_export, stream_project_generation
from services.v2.agent_task_service import get_task


bp = Blueprint("v2_streams", __name__, url_prefix="/streams")


def sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@bp.route("/tasks/<int:task_id>", methods=["GET"])
def stream_task(task_id):
    def generate():
        task = get_task(task_id)
        if not task:
            yield sse({"type": "error", "error": "Task not found."})
            return
        task_type = task.get("taskType")
        if task_type == "chapter_generate":
            iterator = stream_chapter_generation(task_id)
        elif task_type == "project_generate":
            iterator = stream_project_generation(task_id)
        elif task_type == "project_export":
            iterator = run_project_export(task_id)
        else:
            iterator = iter([{"type": "error", "error": f"Unsupported taskType: {task_type}"}])
        for event in iterator:
            yield sse(event)

    return Response(
        generate(),
        mimetype="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
