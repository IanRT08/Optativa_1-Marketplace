"""DFR 4.1 Buscar y filtrar productos (pantalla principal) y DFR 4.2 Detalle.

Ambas rutas son abiertas, igual que las Lambdas. Con sesión se manda el token
a la 4.2 para que la API devuelva el stock exacto (regla de Ian).
"""
from flask import Blueprint, abort, render_template, request

import api
import catalogos
from constantes import BUSQUEDA_MAX_LLAMADAS, MSG_ERROR_INTERNO, MSG_SIN_PRODUCTOS
from dtos import BusquedaDTO, ErrorRespuesta, PaginaProductosDTO, ProductoDetalleDTO

from errores_campo import asignar

bp = Blueprint("catalogo", __name__)


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
        error = None if asignar(exc.mensaje, "filtro_catalogo", request.args) else exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO

    return render_template(
        "catalogo.html",
        busqueda=busqueda,
        categorias=catalogos.categorias(),
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
