from datetime import datetime

from flask import Blueprint, jsonify, request

from core.db import get_db


bp = Blueprint("users", __name__)


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


@bp.route("/identify", methods=["POST"])
def identify_user():
    data = request.get_json(silent=True) or {}
    fingerprint_id = data.get("fingerprintId")

    if not fingerprint_id:
        return jsonify({"error": "Fingerprint ID is required."}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE fingerprint_id = ?", (fingerprint_id,))
        user = cursor.fetchone()

        if user:
            conn.close()
            return jsonify({"userId": user["id"], "isNew": False})

        now = _now()
        cursor.execute(
            """
            INSERT INTO users (tenant_id, fingerprint_id, display_name, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, fingerprint_id, f"用户{fingerprint_id[-6:]}", "active", now, now),
        )
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT IGNORE INTO user_roles (user_id, role_id, tenant_id, created_at) VALUES (?, 1, 1, ?)",
            (user_id, now),
        )
        conn.commit()
        conn.close()
        return jsonify({"userId": user_id, "isNew": True}), 201
    except Exception as exc:
        print(f"[ERROR] User identification failed: {str(exc)}")
        return jsonify({"error": "Failed to identify or create user."}), 500
