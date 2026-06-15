from flask import Blueprint, jsonify


bp = Blueprint("v2_health", __name__)


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "version": "v2", "phase": "p0"})
