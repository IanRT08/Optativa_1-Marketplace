"""DFR 4.1 Buscar y filtrar productos (pantalla principal) y DFR 4.2 Detalle.

Ambas rutas son abiertas, igual que las Lambdas. Con sesión se manda el token
a la 4.2 para que la API devuelva el stock exacto (regla de Ian).
"""
import time

from flask import Blueprint, abort, current_app, render_template, request

import api
from constantes import BUSQUEDA_MAX_LLAMADAS, CATEGORIAS_CACHE_S, MSG_ERROR_INTERNO, MSG_SIN_PRODUCTOS
from dtos import BusquedaDTO, CategoriaDTO, ErrorRespuesta, PaginaProductosDTO, ProductoDetalleDTO

bp = Blueprint("catalogo", __name__)

_cache_categorias = {"hasta": 0.0, "lista": []}


def _categorias():
    """Lista para el filtro. Se guarda unos minutos para no llamar a la 2.2
    (RDS) en cada página. Si falla, el catálogo sigue sin el filtro."""
    if time.monotonic() < _cache_categorias["hasta"]:
        return _cache_categorias["lista"]
    try:
        lista = CategoriaDTO.lista_from_api(api.llamar("GET", "/categorias", token=None))
    except (api.ApiError, ErrorRespuesta):
        current_app.logger.warning("No se pudieron cargar las categorías del filtro")
        # Reintento en 1 min: si RDS está caído, cada visita no espera el timeout.
        _cache_categorias["hasta"] = time.monotonic() + 60
        return _cache_categorias["lista"]
    lista.sort(key=lambda c: c.etiqueta.lower())
    _cache_categorias.update(hasta=time.monotonic() + CATEGORIAS_CACHE_S, lista=lista)
    return lista


@bp.route("/")
def inicio():
    busqueda = BusquedaDTO.from_form(request.args)
    pagina, error = None, None
    try:
        # 4.1 es pública: no se manda el token. La Lambda revisa hasta 2,000
        # ítems por llamada; si no encontró nada pero hay cursor, se sigue
        # buscando (con tope) para no mostrar una página vacía a medias.
        params = busqueda.to_dict()
        for _ in range(BUSQUEDA_MAX_LLAMADAS):
            pagina = PaginaProductosDTO.from_api(
                api.llamar("GET", "/productos", params=params, token=None))
            if pagina.productos or not pagina.siguiente_cursor:
                break
            params = {**busqueda.filtros(), "cursor": pagina.siguiente_cursor}
    except api.ApiError as exc:
        error = exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO

    return render_template(
        "catalogo.html",
        busqueda=busqueda,
        categorias=_categorias(),
        pagina=pagina,
        error=error,
        msg_sin_productos=MSG_SIN_PRODUCTOS,
        es_primera_pagina=not busqueda.cursor,
    )


@bp.route("/productos/<int:id_producto>")
def detalle(id_producto):
    try:
        producto = ProductoDetalleDTO.from_api(
            api.llamar("GET", f"/productos/{id_producto}"))
    except api.ApiError as exc:
        # 404: "El producto no existe" / "Este producto ya no está disponible"
        return render_template("error.html", mensaje=exc.mensaje), exc.status if exc.status in (400, 404) else 500
    except ErrorRespuesta:
        abort(500)
    return render_template("producto.html", producto=producto)
