"""Extensoes Flask compartilhadas pela aplicacao.

Mantem a instancia das extensoes fora do app principal para permitir importar
modelos, rotas e testes sem criar ciclos de importacao.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

try:
    from flask_migrate import Migrate
except ImportError:  # pragma: no cover - dependencia opcional em alguns ambientes
    Migrate = None


db = SQLAlchemy()
csrf = CSRFProtect()
lm = LoginManager()
migrate = Migrate() if Migrate else None
MIGRATE_OK = Migrate is not None
