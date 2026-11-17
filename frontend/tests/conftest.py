"""Pruebas de la interfaz Flask con la API simulada (no llaman a AWS).

Ejecutar desde la carpeta frontend/:   python -m pytest
"""
import html
import os
import re
import sys
import time
from pathlib import Path

import pytest

CARPETA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CARPETA))
# Valores de prueba: la app exige estas variables, pero la API se simula.
os.environ.setdefault("API_BASE_URL", "https://api-simulada.invalid")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-locales-0123456789")
os.environ["COOKIE_SECURE"] = "false"

import api  # noqa: E402
from app import app as aplicacion  # noqa: E402

aplicacion.config.update(TESTING=True, WTF_CSRF_ENABLED=False)


class ApiSimulada:
    """Respuestas por (método, ruta) o por ruta. Registra cada llamada."""

    def __init__(self):
        self.respuestas = {}
        self.llamadas = []

    def __setitem__(self, clave, valor):
        self.respuestas[clave] = valor

    def __call__(self, metodo, ruta, **kw):
        self.llamadas.append((metodo, ruta, kw.get("params")))
        r = self.respuestas.get((metodo, ruta), self.respuestas.get(ruta, {"mensaje": "Consulta realizada"}))
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def R(monkeypatch):
    simulada = ApiSimulada()
    monkeypatch.setattr(api, "llamar", simulada)
    return simulada


@pytest.fixture
def cliente():
    def crear(rol=None):
        c = aplicacion.test_client()
        if rol:
            with c.session_transaction() as s:
                s.update(token="token-de-prueba", expira=int(time.time()) + 3600, rol=rol,
                         nombre="Ana", id_usuario=9007)
        return c
    return crear


# --- Ayudas para revisar el HTML -------------------------------------------
def bajo(h, idcampo, msg):
    """El mensaje está debajo del campo y el campo tiene aria-invalid."""
    m = re.search(r'id="%s-error"[^>]*>.*?<span>(.*?)</span>' % re.escape(idcampo), h, re.S)
    inp = re.search(r'id="%s"[^>]*aria-invalid="true"' % re.escape(idcampo), h, re.S)
    return bool(m and html.unescape(m.group(1)) == msg and inp)


def grupo(h, clave, msg):
    m = re.search(r'id="error-%s"[^>]*>.*?<span>(.*?)</span>' % re.escape(clave), h, re.S)
    return bool(m and html.unescape(m.group(1)) == msg)


def arriba(h, msg):
    return 'class="alerta alerta-error"' in h and msg in html.unescape(h)
