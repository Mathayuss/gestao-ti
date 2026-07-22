"""Acesso centralizado as configuracoes persistidas da aplicacao."""
import json

from extensions import db
from models import Setting


def get_setting(key, default=None):
    setting = db.session.get(Setting, key)
    if setting is None:
        return default
    try:
        return json.loads(setting.value)
    except Exception:
        return setting.value


def set_setting(key, value):
    setting = db.session.get(Setting, key)
    raw = json.dumps(value, ensure_ascii=False)
    if setting:
        setting.value = raw
    else:
        db.session.add(Setting(key=key, value=raw))
