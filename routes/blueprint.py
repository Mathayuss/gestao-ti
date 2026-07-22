"""Blueprint compartilhado para rotas migradas gradualmente do app principal."""
from flask import Blueprint


bp = Blueprint("main_routes", __name__)
