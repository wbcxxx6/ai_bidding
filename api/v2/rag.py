from flask import Blueprint, jsonify, request

from services.v2.context_builder import build_context


bp = Blueprint("v2_rag", __name__, url_prefix="/rag")


@bp.route("/search", methods=["POST"])
def search():
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    project_id = data.get("projectId") or data.get("project_id")
    if not query:
        return jsonify({"error": "query is required."}), 400
    if not project_id:
        return jsonify({"error": "projectId is required."}), 400
    result = build_context(
        query,
        project_id=int(project_id),
        chapter_id=data.get("chapterId") or data.get("chapter_id"),
        limit=int(data.get("limit") or 5),
    )
    return jsonify(result)
