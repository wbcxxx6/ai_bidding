import json

from flask import Blueprint, Response

from services.v2.chapter_generation_service import stream_chapter_generation


bp = Blueprint("v2_streams", __name__, url_prefix="/streams")


def sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@bp.route("/tasks/<int:task_id>", methods=["GET"])
def stream_task(task_id):
    def generate():
        for event in stream_chapter_generation(task_id):
            yield sse(event)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
