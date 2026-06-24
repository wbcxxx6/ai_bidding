from flask import Blueprint, jsonify, request

from services.v2.agent_task_service import create_task, get_task, list_events
from services.v2.project_generation_service import create_export_task, create_project_task


bp = Blueprint("v2_agent_tasks", __name__, url_prefix="/agent-tasks")


@bp.route("", methods=["POST"])
def create_agent_task():
    data = request.get_json(silent=True) or {}
    task_type = data.get("taskType") or data.get("task_type")
    project_id = data.get("projectId") or data.get("project_id")
    chapter_id = data.get("chapterId") or data.get("chapter_id")
    created_by = data.get("userId") or data.get("user_id")
    if task_type == "chapter_generate":
        if not project_id or not chapter_id:
            return jsonify({"error": "projectId and chapterId are required."}), 400
        task = create_task(
            project_id=int(project_id),
            chapter_id=int(chapter_id),
            task_type=task_type,
            input_json=data.get("input") or {},
            created_by=created_by,
        )
    elif task_type == "project_generate":
        if not project_id:
            return jsonify({"error": "projectId is required."}), 400
        task = create_project_task(
            project_id=int(project_id),
            created_by=created_by,
            include_existing=bool(data.get("includeExisting") or data.get("include_existing")),
        )
    elif task_type == "project_export":
        if not project_id:
            return jsonify({"error": "projectId is required."}), 400
        task = create_export_task(project_id=int(project_id), created_by=created_by)
    else:
        return jsonify({"error": "Unsupported taskType."}), 400
    return jsonify({"task": task}), 201


@bp.route("/<int:task_id>", methods=["GET"])
def get_agent_task(task_id):
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found."}), 404
    return jsonify({"task": task, "events": list_events(task_id)})
