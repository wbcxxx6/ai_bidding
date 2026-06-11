from flask import Blueprint

from api.v2 import agent_tasks, chapters, health, images, rag, streams


bp = Blueprint("v2", __name__)
bp.register_blueprint(health.bp)
bp.register_blueprint(agent_tasks.bp)
bp.register_blueprint(chapters.bp)
bp.register_blueprint(images.bp)
bp.register_blueprint(rag.bp)
bp.register_blueprint(streams.bp)
