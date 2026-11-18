"""Pantallas del Vendedor: productos (3.1-3.6) y reporte de ventas (8.1).

Todas exigen sesión de Vendedor (decorador); cada Lambda vuelve a revisar el
token y que el producto sea del vendedor ("Acceso restringido", DFR 3.3).
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

import api
import catalogos
from constantes import ESTADOS_PRODUCTO, MSG_ACCESO_RESTRINGIDO, MSG_ERROR_INTERNO, ROL_VENDEDOR
from dtos import (
    ErrorRespuesta,
    ErrorValidacion,
    EstadoProductoDTO,
    FiltroFechasDTO,
    FiltroMisProductosDTO,
    PaginaMisProductosDTO,
    ProductoDetalleDTO,
    ProductoFormDTO,
    ReporteVentasDTO,
    StockMasivoDTO,
    VarianteFormDTO,
    valores_form_desde_post,
    valores_form_producto,
)
from errores_campo import asignar, avisar
from seguridad import rol_requerido, ruta_interna

bp = Blueprint("vendedor", __name__, url_prefix="/vendedor")

# Renglones vacíos de especificaciones que ofrece el formulario.
ESPEC_RENGLONES_EXTRA = 3


def _mensaje(exc):
    return getattr(exc, "mensaje", None) or str(exc)


def _es_propio(id_producto):
    """¿El producto es del vendedor de la sesión? La 3.2 solo trae los productos
    del vendedor del token y pagina con id_producto > cursor: con cursor = id - 1,
    el primer renglón es ese producto solo si es suyo (una llamada, igual que 1.5)."""
    datos = api.llamar("GET", "/vendedor/productos", params={"cursor": id_producto - 1})
    filas = datos.get("productos")
    return (isinstance(filas, list) and bool(filas) and isinstance(filas[0], dict)
            and filas[0].get("id_producto") == id_producto)


def _detalle(id_producto):
    """4.2 con el token del vendedor: datos actuales para 3.3 y 3.6.
    Un producto ajeno no se muestra (regla 7: cada usuario solo ve lo suyo)."""
    if not _es_propio(id_producto):
        raise api.AccesoRestringido(403, MSG_ACCESO_RESTRINGIDO)
    return ProductoDetalleDTO.from_api(api.llamar("GET", f"/productos/{id_producto}"))


def _form_producto(plantilla_titulo, accion, valores, id_producto=None):
    especificaciones = list(valores.get("especificaciones") or [])
    especificaciones += [("", "")] * ESPEC_RENGLONES_EXTRA
    return render_template(
        "vendedor/producto_form.html",
        titulo=plantilla_titulo, accion=accion, valores=valores, id_producto=id_producto,
        especificaciones=especificaciones[:20],
        marcas=catalogos.marcas(), categorias=catalogos.categorias(),
    )


# =============================================================================
# 3.2 Consultar mis productos (pantalla de inicio del Vendedor)
# =============================================================================
@bp.route("/productos")
@rol_requerido(ROL_VENDEDOR)
def productos():
    filtro = FiltroMisProductosDTO.from_form(request.args)
    pagina, error = None, None
    try:
        pagina = PaginaMisProductosDTO.from_api(
            api.llamar("GET", "/vendedor/productos", params=filtro.to_dict()))
    except api.ApiError as exc:
        error = None if asignar(exc.mensaje, "filtro_productos", request.args) else exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO
    return render_template("vendedor/productos.html", filtro=filtro, pagina=pagina, error=error,
                           categorias=catalogos.categorias(), estados=ESTADOS_PRODUCTO)


# =============================================================================
# 3.1 Registrar producto
# =============================================================================
@bp.route("/productos/nuevo", methods=["GET", "POST"])
@rol_requerido(ROL_VENDEDOR)
def nuevo():
    accion = url_for("vendedor.nuevo")
    if request.method == "POST":
        try:
            dto = ProductoFormDTO.from_form(request.form)
            datos = api.llamar("POST", "/vendedor/productos", json=dto.to_dict())
            flash(datos.get("mensaje") or "Producto registrado correctamente", "exito")
            return redirect(url_for("vendedor.productos"))
        except (ErrorValidacion, api.ApiError) as exc:
            avisar(exc, "producto", request.form)
        return _form_producto("Registrar producto", accion, valores_form_desde_post(request.form))
    return _form_producto("Registrar producto", accion, {"con_logistica": False})


# =============================================================================
# 3.3 Editar producto
# =============================================================================
@bp.route("/productos/<int:id_producto>/editar", methods=["GET", "POST"])
@rol_requerido(ROL_VENDEDOR)
def editar(id_producto):
    accion = url_for("vendedor.editar", id_producto=id_producto)
    if request.method == "POST":
        try:
            dto = ProductoFormDTO.from_form(request.form)
            datos = api.llamar("PUT", f"/vendedor/productos/{id_producto}", json=dto.to_dict())
            flash(datos.get("mensaje") or "Producto actualizado correctamente", "exito")
            return redirect(url_for("vendedor.productos"))
        except (ErrorValidacion, api.ApiError) as exc:
            avisar(exc, "producto", request.form)
        return _form_producto("Editar producto", accion, valores_form_desde_post(request.form), id_producto)

    try:
        detalle = _detalle(id_producto)
    except api.ApiError as exc:
        # Inactivo: la 4.2 responde "Este producto ya no está disponible"
        # y la 3.3 solo edita productos Activos (primero se activa con 3.4).
        flash(exc.mensaje, "error")
        return redirect(url_for("vendedor.productos"))
    except ErrorRespuesta:
        flash(MSG_ERROR_INTERNO, "error")
        return redirect(url_for("vendedor.productos"))
    # La 4.2 trae el nombre de la marca; el formulario necesita su id (A1).
    id_marca = next((m.id_marca for m in catalogos.marcas() if m.nombre == detalle.marca), None)
    return _form_producto("Editar producto", accion, valores_form_producto(detalle, id_marca), id_producto)


# =============================================================================
# 3.4 Activar / desactivar producto
# =============================================================================
@bp.route("/productos/<int:id_producto>/estado", methods=["POST"])
@rol_requerido(ROL_VENDEDOR)
def estado(id_producto):
    try:
        dto = EstadoProductoDTO.from_form(request.form)
        datos = api.llamar("PATCH", f"/vendedor/productos/{id_producto}/estado", json=dto.to_dict())
        flash(datos.get("mensaje") or "Estado del producto actualizado correctamente", "exito")
    except (ErrorValidacion, api.ApiError) as exc:
        flash(_mensaje(exc), "error")
    # Vuelve a la misma página del listado (con sus filtros), solo si es interna.
    volver = request.form.get("volver", "")
    if ruta_interna(volver) and volver.startswith(url_for("vendedor.productos")):
        return redirect(volver)
    return redirect(url_for("vendedor.productos"))


# =============================================================================
# 3.6 Registrar variantes de un producto
# =============================================================================
@bp.route("/productos/<int:id_producto>/variantes", methods=["GET", "POST"])
@rol_requerido(ROL_VENDEDOR)
def variantes(id_producto):
    elegidos, stock = [], ""
    if request.method == "POST":
        elegidos = [v for v in request.form.getlist("valores") if v]
        stock = request.form.get("stock", "").strip()
        try:
            dto = VarianteFormDTO.from_form(request.form)
            datos = api.llamar("POST", f"/vendedor/productos/{id_producto}/variantes", json=dto.to_dict())
            flash(datos.get("mensaje") or "Variante registrada correctamente", "exito")
            return redirect(url_for("vendedor.variantes", id_producto=id_producto))
        except (ErrorValidacion, api.ApiError) as exc:
            avisar(exc, "variante", request.form)

    try:
        detalle = _detalle(id_producto)
    except api.ApiError as exc:
        flash(exc.mensaje, "error")
        return redirect(url_for("vendedor.productos"))
    except ErrorRespuesta:
        flash(MSG_ERROR_INTERNO, "error")
        return redirect(url_for("vendedor.productos"))
    return render_template("vendedor/variantes.html", producto=detalle, atributos=catalogos.atributos(),
                           elegidos=elegidos, stock=stock)


# =============================================================================
# 3.5 Actualizar stock de forma masiva (sp_ActualizarStockMasivo)
# =============================================================================
@bp.route("/stock-masivo", methods=["GET", "POST"])
@rol_requerido(ROL_VENDEDOR)
def stock_masivo():
    previo = {}
    if request.method == "POST":
        previo = {c: request.form.get(c, "").strip() for c in ("id_categoria", "cantidad")}
        try:
            dto = StockMasivoDTO.from_form(request.form)
            datos = api.llamar("POST", "/vendedor/stock-masivo", json=dto.to_dict())
            flash(datos.get("mensaje") or "Stock actualizado correctamente", "exito")
            return redirect(url_for("vendedor.stock_masivo"))
        except (ErrorValidacion, api.ApiError) as exc:
            avisar(exc, "stock_masivo", request.form)
    return render_template("vendedor/stock_masivo.html", categorias=catalogos.categorias(), previo=previo)


# =============================================================================
# 8.1 Reporte de ventas del vendedor (sp_HistorialVentas)
# =============================================================================
@bp.route("/ventas")
@rol_requerido(ROL_VENDEDOR)
def ventas():
    fechas = {c: request.args.get(c, "").strip() for c in ("fecha_inicio", "fecha_fin")}
    reporte, error = None, None
    if any(fechas.values()):   # la primera vez solo se muestra el formulario
        try:
            dto = FiltroFechasDTO.from_form(request.args)
            reporte = ReporteVentasDTO.from_api(
                api.llamar("GET", "/vendedor/ventas", params=dto.to_dict()))
        except (ErrorValidacion, api.ApiError) as exc:
            error = None if asignar(_mensaje(exc), "reporte", request.args) else _mensaje(exc)
        except ErrorRespuesta:
            error = MSG_ERROR_INTERNO
    return render_template("reporte_ventas.html", titulo="Mis ventas", accion=url_for("vendedor.ventas"),
                           fechas=fechas, reporte=reporte, error=error)
