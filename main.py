from dotenv import load_dotenv
from flask import Flask, send_from_directory
from flask_cors import CORS

from api import bidding, files, generation, knowledge, research, settings, users, v2
from core.db import init_mysql


load_dotenv()

app = Flask(__name__)
CORS(app)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

init_mysql()

app.register_blueprint(bidding.bp, url_prefix="/api/bidding")
app.register_blueprint(users.bp, url_prefix="/api/users")
app.register_blueprint(settings.bp, url_prefix="/api/settings")
app.register_blueprint(knowledge.bp, url_prefix="/api")
app.register_blueprint(files.bp, url_prefix="/api")
app.register_blueprint(research.bp, url_prefix="/api")
app.register_blueprint(generation.bp, url_prefix="/api")
app.register_blueprint(v2.bp, url_prefix="/api/v2")


import os

DIST_DIR = os.path.join(os.path.dirname(__file__), "web", "dist")
USE_DIST = os.path.isdir(DIST_DIR)


@app.route("/")
def index():
    if USE_DIST:
        return send_from_directory(DIST_DIR, "index.html")
    return send_from_directory("frontend", "index.html")


@app.route("/admin")
def admin():
    if USE_DIST:
        return send_from_directory(DIST_DIR, "admin.html")
    return send_from_directory("frontend", "index.html")


@app.route("/assets/<path:filename>")
def dist_assets(filename):
    return send_from_directory(os.path.join(DIST_DIR, "assets"), filename)


@app.route("/project/<path:subpath>")
def user_spa_fallback(subpath):
    if USE_DIST:
        return send_from_directory(DIST_DIR, "index.html")
    return send_from_directory("frontend", "index.html")


@app.route("/app/<path:filename>")
def frontend_assets(filename):
    return send_from_directory("frontend", filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3012))
    app.run(host="0.0.0.0", port=port, debug=True)
