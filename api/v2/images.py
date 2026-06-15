from flask import Blueprint, jsonify, request

from services.v2.image_asset_service import create_image_asset, list_image_assets
from services.v2.wan_image_service import create_section_image_generation, query_wan_image_task, sync_generated_asset_result


bp = Blueprint("v2_images", __name__, url_prefix="/images")


@bp.route("/assets", methods=["GET"])
def image_assets():
    allowed = request.args.get("allowedForBid")
    allowed_for_bid = None
    if allowed is not None:
        allowed_for_bid = allowed.lower() not in {"0", "false", "no"}
    return jsonify(
        {
            "items": list_image_assets(
                project_id=request.args.get("projectId", type=int),
                image_type=request.args.get("imageType"),
                review_status=request.args.get("reviewStatus"),
                allowed_for_bid=allowed_for_bid,
                limit=request.args.get("limit", default=50, type=int),
            )
        }
    )


@bp.route("/assets", methods=["POST"])
def create_asset():
    data = request.get_json(silent=True) or {}
    try:
        asset = create_image_asset(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"item": asset}), 201


@bp.route("/generate", methods=["POST"])
def generate_image():
    data = request.get_json(silent=True) or {}
    try:
        result = create_section_image_generation(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result), 202


@bp.route("/generation-tasks/<task_id>", methods=["GET"])
def image_generation_task(task_id):
    try:
        result = query_wan_image_task(task_id)
        asset_id = request.args.get("assetId", type=int)
        if asset_id:
            result["asset"] = sync_generated_asset_result(asset_id, result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)
