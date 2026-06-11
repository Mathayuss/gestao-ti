"""Entrada WSGI para servidores como Gunicorn/uWSGI."""
from app import create_app


app = create_app()
