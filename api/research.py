from flask import Blueprint, jsonify, request

from services.deep_research_service import (
    confirm_source,
    create_and_run_research_task,
    get_research_task,
    list_reports,
)


bp = Blueprint("research", __name__)


def _serialize_bundle(bundle):
    task = bundle["task"]
    report = bundle.get("report")
    return {
        "task": task,
        "report": report,
        "sources": bundle.get("sources") or [],
    }


@bp.route("/projects/<int:project_id>/research-tasks", methods=["POST"])
def create_research_task(project_id):
    data = request.get_json(silent=True) or {}
    try:
        bundle = create_and_run_research_task(project_id, data, created_by=data.get("userId"))
        return jsonify(_serialize_bundle(bundle)), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"Research task failed: {str(exc)}"}), 500


@bp.route("/research-tasks/<int:task_id>", methods=["GET"])
def get_research_task_status(task_id):
    bundle = get_research_task(task_id)
    if not bundle.get("task"):
        return jsonify({"error": "Research task not found."}), 404
    return jsonify(_serialize_bundle(bundle))


@bp.route("/projects/<int:project_id>/research-reports", methods=["GET"])
def list_research_reports(project_id):
    return jsonify({"items": list_reports(project_id)})


@bp.route("/research-sources/<int:source_id>/confirm", methods=["POST"])
def confirm_research_source(source_id):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(confirm_source(source_id, confirmed_by=data.get("userId")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
