"""Catálogos de apoyo para filtros y formularios, con caché corta.

Categorías (2.2), marcas (A1) y atributos (A2) son públicos y cambian poco:
se guardan unos minutos para no llamar a RDS en cada página. Si la API
falla, se devuelve la última lista conocida (o vacía) y se reintenta en 1 min,
así una página no espera el timeout en cada visita.
"""
import time

from flask import current_app

import api
from constantes import CATEGORIAS_CACHE_S
from dtos import AtributoDTO, CategoriaDTO, ErrorRespuesta, MarcaDTO

_REINTENTO_S = 60
_cache = {}


def _obtener(ruta, convertir, orden):
    entrada = _cache.get(ruta, {"hasta": 0.0, "lista": []})
    if time.monotonic() < entrada["hasta"]:
        return entrada["lista"]
    try:
        lista = sorted(convertir(api.llamar("GET", ruta, token=None)), key=orden)
        _cache[ruta] = {"hasta": time.monotonic() + CATEGORIAS_CACHE_S, "lista": lista}
    except (api.ApiError, ErrorRespuesta):
        current_app.logger.warning("No se pudo cargar el catálogo %s", ruta)
        _cache[ruta] = {"hasta": time.monotonic() + _REINTENTO_S, "lista": entrada["lista"]}
    return _cache[ruta]["lista"]


def categorias():
    return _obtener("/categorias", CategoriaDTO.lista_from_api, lambda c: c.etiqueta.lower())


def marcas():
    return _obtener("/marcas", MarcaDTO.lista_from_api, lambda m: m.nombre.lower())


def atributos():
    # La A2 ya ordena los valores por id (tallas en orden de carga).
    return _obtener("/atributos", AtributoDTO.lista_from_api, lambda a: a.nombre.lower())


def olvidar():
    """Vacía la caché (p. ej. después de crear o editar categorías en la etapa 5)."""
    _cache.clear()
