"""Pantallas del Comprador: carrito (5.1-5.4), direcciones (9.1-9.3) y compra (6.1).

Todas exigen sesión de Comprador (decorador) y la API lo vuelve a revisar.
Los formularios que cambian datos son POST con CSRF; las llamadas que la
API define como PUT/DELETE/PATCH las hace Flask del lado del servidor.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

import api
from constantes import (
    MSG_CARRITO_VACIO,
    MSG_COMPRA_REALIZADA,
    MSG_ERROR_INTERNO,
    MSG_PRODUCTO_NO_DISPONIBLE,
    MSG_STOCK_INSUFICIENTE,
    ROL_COMPRADOR,
)
from dtos import (
    AgregarCarritoDTO,
    CantidadCarritoDTO,
    CarritoDTO,
    CompraDTO,
    CompraRespuestaDTO,
    DireccionDTO,
    DireccionFormDTO,
    ErrorRespuesta,
    ErrorValidacion,
    QuitarCarritoDTO,
)
from seguridad import hay_sesion, recordar_destino, rol_requerido

bp = Blueprint("comprador", __name__)

# Páginas a las que se puede volver desde "Mis direcciones" (lista cerrada).
_VOLVER_DESDE_DIRECCIONES = {"compra": "comprador.compra"}


def _mensaje(exc):
    return getattr(exc, "mensaje", None) or str(exc)


def _consultar_carrito():
    return CarritoDTO.from_api(api.llamar("GET", "/carrito"))


def _consultar_direcciones():
    return DireccionDTO.lista_from_api(api.llamar("GET", "/direcciones"))


def _avisos(carrito):
    """Por qué no se puede comprar, por renglón (textos del DFR 6.1)."""
    avisos = {}
    for item in carrito.items:
        if not item.disponible:
            avisos[item.id_variante] = MSG_PRODUCTO_NO_DISPONIBLE.format(nombre=item.nombre)
        elif not item.stock_suficiente:
            avisos[item.id_variante] = MSG_STOCK_INSUFICIENTE.format(nombre=item.nombre)
    return avisos


# =============================================================================
# 5.1 Agregar al carrito (formulario en el detalle del producto)
# =============================================================================
@bp.route("/carrito/agregar", methods=["POST"])
def agregar():
    try:
        dto = AgregarCarritoDTO.from_form(request.form)
    except ErrorValidacion as exc:
        flash(_mensaje(exc), "error")
        # Con id_producto válido se vuelve al producto; si no, al catálogo.
        producto = request.form.get("id_producto", "")
        if producto.isascii() and producto.isdigit():
            return redirect(url_for("catalogo.detalle", id_producto=int(producto)))
        return redirect(url_for("catalogo.inicio"))
    detalle = url_for("catalogo.detalle", id_producto=dto.id_producto)

    # DFR 5.1: sin sesión -> inicio de sesión, y después vuelve al producto.
    if not hay_sesion():
        recordar_destino(detalle)
        return redirect(url_for("auth.login"))
    if session.get("rol") != ROL_COMPRADOR:
        abort(403)

    try:
        datos = api.llamar("POST", "/carrito/items", json=dto.to_dict())
        flash(datos.get("mensaje") or "Producto agregado al carrito", "exito")
    except api.ApiError as exc:
        flash(exc.mensaje, "error")
    return redirect(detalle)


# =============================================================================
# 5.2 Consultar carrito / 5.3 Modificar cantidad / 5.4 Quitar
# =============================================================================
@bp.route("/carrito")
@rol_requerido(ROL_COMPRADOR)
def carrito():
    try:
        datos = _consultar_carrito()
    except api.ApiError as exc:
        return render_template("carrito.html", carrito=None, error=exc.mensaje)
    except ErrorRespuesta:
        return render_template("carrito.html", carrito=None, error=MSG_ERROR_INTERNO)
    return render_template("carrito.html", carrito=datos, avisos=_avisos(datos),
                           msg_vacio=MSG_CARRITO_VACIO, error=None)


@bp.route("/carrito/<int:id_variante>/cantidad", methods=["POST"])
@rol_requerido(ROL_COMPRADOR)
def cambiar_cantidad(id_variante):
    try:
        dto = CantidadCarritoDTO.from_form(request.form)
        if dto.cantidad == 0:
            # Acuerdo con Ian: el DFR 5.3 exige cantidad > 0, así que poner 0
            # en la pantalla quita el producto con la 5.4.
            datos = api.llamar("DELETE", "/carrito/items",
                               json=QuitarCarritoDTO.de_una(id_variante).to_dict())
        else:
            datos = api.llamar("PUT", f"/carrito/items/{id_variante}", json=dto.to_dict())
        flash(datos.get("mensaje") or "Carrito actualizado correctamente", "exito")
    except (ErrorValidacion, api.ApiError) as exc:
        flash(_mensaje(exc), "error")
    return redirect(url_for("comprador.carrito"))


@bp.route("/carrito/quitar", methods=["POST"])
@rol_requerido(ROL_COMPRADOR)
def quitar():
    try:
        dto = QuitarCarritoDTO.from_form(request.form)
        datos = api.llamar("DELETE", "/carrito/items", json=dto.to_dict())
        flash(datos.get("mensaje") or "Producto/s eliminado/s del carrito", "exito")
    except (ErrorValidacion, api.ApiError) as exc:
        flash(_mensaje(exc), "error")
    return redirect(url_for("comprador.carrito"))


# =============================================================================
# 9.1 Registrar / 9.2 Consultar / 9.3 Desactivar direcciones
# =============================================================================
def _volver_valido(valor):
    return valor if valor in _VOLVER_DESDE_DIRECCIONES else ""


@bp.route("/direcciones", methods=["GET", "POST"])
@rol_requerido(ROL_COMPRADOR)
def direcciones():
    volver = _volver_valido(request.values.get("volver", ""))
    previo = {}
    if request.method == "POST":
        try:
            dto = DireccionFormDTO.from_form(request.form)
            datos = api.llamar("POST", "/direcciones", json=dto.to_dict())
            flash(datos.get("mensaje") or "Dirección registrada correctamente", "exito")
            if volver:
                return redirect(url_for(_VOLVER_DESDE_DIRECCIONES[volver]))
            return redirect(url_for("comprador.direcciones"))
        except (ErrorValidacion, api.ApiError) as exc:
            flash(_mensaje(exc), "error")
            previo = {c: request.form.get(c, "").strip() for c in
                      ("calle", "numero", "colonia", "ciudad", "estado", "codigo_postal")}

    lista, mensaje_lista, error = [], None, None
    try:
        datos = api.llamar("GET", "/direcciones")
        lista = DireccionDTO.lista_from_api(datos)
        mensaje_lista = datos.get("mensaje") if not lista else None
    except api.ApiError as exc:
        error = exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO
    return render_template("direcciones.html", direcciones=lista, mensaje_lista=mensaje_lista,
                           error=error, previo=previo, volver=volver)


@bp.route("/direcciones/<int:id_direccion>/desactivar", methods=["POST"])
@rol_requerido(ROL_COMPRADOR)
def desactivar_direccion(id_direccion):
    try:
        datos = api.llamar("PATCH", f"/direcciones/{id_direccion}/desactivar")
        flash(datos.get("mensaje") or "Dirección desactivada correctamente", "exito")
    except api.ApiError as exc:
        flash(exc.mensaje, "error")
    return redirect(url_for("comprador.direcciones"))


# =============================================================================
# 6.1 Confirmar compra (sp_RegistrarCompra)
# =============================================================================
@bp.route("/compra", methods=["GET", "POST"])
@rol_requerido(ROL_COMPRADOR)
def compra():
    if request.method == "POST":
        id_direccion = request.form.get("id_direccion", "")
        try:
            dto = CompraDTO.from_form(request.form)
            respuesta = CompraRespuestaDTO.from_api(
                api.llamar("POST", "/compras", json=dto.to_dict()))
            del dto   # la tarjeta no se conserva más allá de esta petición
            # Patrón PRG: solo el número de orden y el total pasan a la sesión.
            session["ultima_compra"] = {"id_pedido": respuesta.id_pedido, "total": respuesta.total}
            return redirect(url_for("comprador.compra_realizada"))
        except (ErrorValidacion, api.ApiError) as exc:
            flash(_mensaje(exc), "error")
        except ErrorRespuesta:
            flash(MSG_ERROR_INTERNO, "error")
        # Se vuelve a mostrar el formulario sin los datos de la tarjeta.
        return _pantalla_compra(id_direccion)
    return _pantalla_compra("")


def _pantalla_compra(id_direccion_elegida):
    try:
        carrito = _consultar_carrito()
        direcciones = _consultar_direcciones()
    except api.ApiError as exc:
        flash(exc.mensaje, "error")
        return redirect(url_for("comprador.carrito"))
    except ErrorRespuesta:
        flash(MSG_ERROR_INTERNO, "error")
        return redirect(url_for("comprador.carrito"))

    if not carrito.items:
        flash(MSG_CARRITO_VACIO, "error")
        return redirect(url_for("comprador.carrito"))
    if not carrito.puede_comprar:
        # El SP compra todo o nada: primero hay que corregir el carrito.
        for aviso in _avisos(carrito).values():
            flash(aviso, "error")
        return redirect(url_for("comprador.carrito"))

    elegida = id_direccion_elegida if any(
        str(d.id_direccion) == id_direccion_elegida for d in direcciones) else ""
    if not elegida and direcciones:
        elegida = str(direcciones[0].id_direccion)   # la 9.2 ya ordena la principal primero
    return render_template("compra.html", carrito=carrito, direcciones=direcciones, elegida=elegida)


@bp.route("/compra/realizada")
@rol_requerido(ROL_COMPRADOR)
def compra_realizada():
    ultima = session.pop("ultima_compra", None)
    if not ultima:
        return redirect(url_for("comprador.carrito"))
    return render_template("compra_realizada.html", mensaje=MSG_COMPRA_REALIZADA,
                           id_pedido=ultima["id_pedido"], total=ultima["total"])
