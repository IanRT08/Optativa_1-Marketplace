"""DFR 4.1 Buscar y filtrar productos (pantalla principal) y DFR 4.2 Detalle.

Ambas rutas son abiertas, igual que las Lambdas. Con sesión se manda el token
a la 4.2 para que la API devuelva el stock exacto (regla de Ian).
"""
from dataclasses import replace

from flask import Blueprint, abort, g, render_template, request, session, url_for

import api
import catalogos
from constantes import BUSQUEDA_MAX_LLAMADAS, MSG_ERROR_INTERNO, MSG_SIN_PRODUCTOS
from dtos import BusquedaDTO, ErrorRespuesta, PaginaProductosDTO, ProductoDetalleDTO

from errores_campo import asignar

bp = Blueprint("catalogo", __name__)


def _buscar(busqueda):
    """4.1 es pública: no se manda el token. La Lambda revisa hasta 2,000
    ítems por llamada; si no encontró nada pero hay cursor, se sigue
    buscando (con tope) para no mostrar una página vacía a medias."""
    params = busqueda.to_dict()
    pagina = None
    for _ in range(BUSQUEDA_MAX_LLAMADAS):
        pagina = PaginaProductosDTO.from_api(
            api.llamar("GET", "/productos", params=params, token=None))
        if pagina.productos or not pagina.siguiente_cursor:
            break
        params = {**busqueda.filtros(), "cursor": pagina.siguiente_cursor}
    return pagina


@bp.route("/")
def inicio():
    busqueda = BusquedaDTO.from_form(request.args)
    vigente = busqueda   # filtros que sí se aplicaron (para los enlaces)
    pagina, error = None, None
    try:
        pagina = _buscar(busqueda)
    except api.ApiError as exc:
        if asignar(exc.mensaje, "filtro_catalogo", request.args):
            # Filtro inválido: el error va debajo del campo y, en lugar de
            # dejar la pantalla vacía, se muestran los productos con los
            # filtros válidos. El rango de precio se quita completo.
            quitar = set(g.errores)
            if quitar & {"precio_min", "precio_max"}:
                quitar |= {"precio_min", "precio_max"}
            vigente = replace(busqueda, cursor="", **{c: "" for c in quitar})
            try:
                pagina = _buscar(vigente)
            except (api.ApiError, ErrorRespuesta):
                pagina = None
        else:
            error = exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO

    # "Volver al catálogo" en el detalle regresa a esta misma búsqueda y página.
    # Solo se guardan los filtros que sí se aplicaron (campos de BusquedaDTO).
    if vigente.to_dict():
        session["catalogo_volver"] = vigente.to_dict()
    else:
        session.pop("catalogo_volver", None)

    return render_template(
        "catalogo.html",
        busqueda=busqueda,
        filtros=vigente.filtros(),
        categorias=catalogos.categorias(),
        pagina=pagina,
        error=error,
        msg_sin_productos=MSG_SIN_PRODUCTOS,
        es_primera_pagina=not vigente.cursor,
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
    volver = url_for("catalogo.inicio", **BusquedaDTO.from_form(session.get("catalogo_volver") or {}).to_dict())
    return render_template("producto.html", producto=producto, volver=volver)
