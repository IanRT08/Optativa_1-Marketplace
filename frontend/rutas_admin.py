"""Pantallas del Administrador: usuarios (1.3-1.6), categorías (2.1-2.4),
pedidos (A3, 7.2, 7.3) y reporte de ventas por vendedor (8.2).

Todas exigen sesión de Administrador (decorador); cada Lambda lo vuelve a
revisar ("Acceso restringido", DFR 1.3 / 7.3 / 8.2).
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

import api
import catalogos
from constantes import (
    ESTADOS_PEDIDO,
    ESTADOS_USUARIO,
    MSG_CATEGORIA_NO_EXISTE,
    MSG_ERROR_INTERNO,
    MSG_USUARIO_NO_EXISTE,
    ROL_ADMINISTRADOR,
    ROL_VENDEDOR,
    ROLES,
    TRANSICIONES_PEDIDO,
    VENDEDORES_MAX_PAGINAS,
)
from dtos import (
    CategoriaDTO,
    CategoriaFormDTO,
    EditarUsuarioDTO,
    ErrorRespuesta,
    ErrorValidacion,
    EstadoPedidoDTO,
    FiltroPedidosDTO,
    FiltroUsuariosDTO,
    FiltroVentasAdminDTO,
    PaginaPedidosDTO,
    PaginaUsuariosDTO,
    PedidoDetalleDTO,
    ReporteVentasDTO,
    UsuarioNuevoDTO,
)
from seguridad import rol_requerido, ruta_interna

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _mensaje(exc):
    return getattr(exc, "mensaje", None) or str(exc)


def _volver(por_defecto, prefijo):
    """Regresa a la página del listado (con filtros) solo si es interna."""
    volver = request.form.get("volver", "")
    if ruta_interna(volver) and volver.startswith(prefijo):
        return redirect(volver)
    return redirect(por_defecto)


def _es_propio(id_usuario):
    return session.get("id_usuario") == id_usuario


# =============================================================================
# 1.4 Consultar usuarios / 1.3 Crear / 1.5 Editar / 1.6 Eliminar (baja lógica)
# =============================================================================
@bp.route("/usuarios")
@rol_requerido(ROL_ADMINISTRADOR)
def usuarios():
    filtro = FiltroUsuariosDTO.from_form(request.args)
    pagina, error = None, None
    try:
        pagina = PaginaUsuariosDTO.from_api(api.llamar("GET", "/admin/usuarios", params=filtro.to_dict()))
    except api.ApiError as exc:
        error = exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO
    return render_template("admin/usuarios.html", filtro=filtro, pagina=pagina, error=error,
                           roles=ROLES, estados=ESTADOS_USUARIO, id_propio=session.get("id_usuario"))


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def usuario_nuevo():
    previo = {}
    if request.method == "POST":
        previo = {c: request.form.get(c, "").strip() for c in ("nombre", "apellido", "email", "rol")}
        try:
            dto = UsuarioNuevoDTO.from_form(request.form)
            datos = api.llamar("POST", "/admin/usuarios", json=dto.to_dict())
            flash(datos.get("mensaje") or "Usuario creado exitosamente", "exito")
            return redirect(url_for("admin.usuarios"))
        except (ErrorValidacion, api.ApiError) as exc:
            flash(_mensaje(exc), "error")
    return render_template("admin/usuario_form.html", nuevo=True, valores=previo, roles=ROLES,
                           estados=ESTADOS_USUARIO, es_propio=False, id_usuario=None)


def _buscar_usuario(id_usuario):
    """No hay ruta para un solo usuario: la 1.4 pagina por id_usuario
    (WHERE id > cursor), así que con cursor = id - 1 el primer renglón es él."""
    datos = api.llamar("GET", "/admin/usuarios", params={"cursor": str(id_usuario - 1)})
    pagina = PaginaUsuariosDTO.from_api(datos)
    return next((u for u in pagina.usuarios if u.id_usuario == id_usuario), None)


@bp.route("/usuarios/<int:id_usuario>/editar", methods=["GET", "POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def usuario_editar(id_usuario):
    es_propio = _es_propio(id_usuario)
    if request.method == "POST":
        valores = {c: request.form.get(c, "").strip() for c in ("nombre", "apellido", "rol", "estado")}
        try:
            dto = EditarUsuarioDTO.from_form(request.form, es_propio=es_propio)
            datos = api.llamar("PUT", f"/admin/usuarios/{id_usuario}", json=dto.to_dict())
            flash(datos.get("mensaje") or "Usuario actualizado correctamente", "exito")
            if es_propio:
                # El saludo de la barra usa el nombre de la sesión.
                session["nombre"], session["apellido"] = dto.nombre, dto.apellido
            return redirect(url_for("admin.usuarios"))
        except (ErrorValidacion, api.ApiError) as exc:
            flash(_mensaje(exc), "error")
    else:
        try:
            usuario = _buscar_usuario(id_usuario)
        except api.ApiError as exc:
            flash(exc.mensaje, "error")
            return redirect(url_for("admin.usuarios"))
        except ErrorRespuesta:
            flash(MSG_ERROR_INTERNO, "error")
            return redirect(url_for("admin.usuarios"))
        if usuario is None:
            flash(MSG_USUARIO_NO_EXISTE, "error")
            return redirect(url_for("admin.usuarios"))
        valores = {"nombre": usuario.nombre, "apellido": usuario.apellido, "rol": usuario.rol,
                   "estado": usuario.estado, "email": usuario.email}
    return render_template("admin/usuario_form.html", nuevo=False, valores=valores, roles=ROLES,
                           estados=ESTADOS_USUARIO, es_propio=es_propio, id_usuario=id_usuario)


@bp.route("/usuarios/<int:id_usuario>/desactivar", methods=["POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def usuario_desactivar(id_usuario):
    try:
        datos = api.llamar("PATCH", f"/admin/usuarios/{id_usuario}/desactivar")
        flash(datos.get("mensaje") or "Usuario eliminado correctamente", "exito")
    except api.ApiError as exc:
        flash(exc.mensaje, "error")
    return _volver(url_for("admin.usuarios"), url_for("admin.usuarios"))


# =============================================================================
# 2.2 Consultar / 2.1 Crear / 2.3 Editar / 2.4 Eliminar categorías
# =============================================================================
def _lista_categorias():
    """Sin caché: el administrador ve siempre el estado actual."""
    datos = api.llamar("GET", "/categorias", token=None)
    lista = CategoriaDTO.lista_from_api(datos)
    lista.sort(key=lambda c: c.etiqueta.lower())
    return lista, (datos.get("mensaje") if not lista else None)


@bp.route("/categorias", methods=["GET", "POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def categorias():
    previo = {}
    if request.method == "POST":
        previo = {c: request.form.get(c, "").strip() for c in ("nombre", "descripcion", "id_categoria_padre")}
        try:
            dto = CategoriaFormDTO.from_form(request.form)
            datos = api.llamar("POST", "/categorias", json=dto.to_dict())
            catalogos.olvidar()
            flash(datos.get("mensaje") or "Categoría creada correctamente", "exito")
            return redirect(url_for("admin.categorias"))
        except (ErrorValidacion, api.ApiError) as exc:
            flash(_mensaje(exc), "error")
    lista, mensaje_lista, error = [], None, None
    try:
        lista, mensaje_lista = _lista_categorias()
    except api.ApiError as exc:
        error = exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO
    return render_template("admin/categorias.html", categorias=lista, mensaje_lista=mensaje_lista,
                           error=error, valores=previo)


@bp.route("/categorias/<int:id_categoria>/editar", methods=["GET", "POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def categoria_editar(id_categoria):
    try:
        lista, _ = _lista_categorias()
    except (api.ApiError, ErrorRespuesta) as exc:
        flash(getattr(exc, "mensaje", MSG_ERROR_INTERNO), "error")
        return redirect(url_for("admin.categorias"))
    actual = next((c for c in lista if c.id_categoria == id_categoria), None)
    if actual is None:
        flash(MSG_CATEGORIA_NO_EXISTE, "error")
        return redirect(url_for("admin.categorias"))

    valores = {"nombre": actual.nombre, "descripcion": actual.descripcion,
               "id_categoria_padre": str(actual.id_categoria_padre or "")}
    if request.method == "POST":
        valores = {c: request.form.get(c, "").strip() for c in ("nombre", "descripcion", "id_categoria_padre")}
        try:
            dto = CategoriaFormDTO.from_form(request.form)
            datos = api.llamar("PUT", f"/categorias/{id_categoria}", json=dto.to_dict())
            catalogos.olvidar()
            flash(datos.get("mensaje") or "Categoría actualizada correctamente", "exito")
            return redirect(url_for("admin.categorias"))
        except (ErrorValidacion, api.ApiError) as exc:
            flash(_mensaje(exc), "error")
    # Se ofrece toda la lista como padre (incluida ella misma): la Lambda
    # responde los mensajes del DFR 2.3 si la elección no es válida.
    return render_template("admin/categoria_form.html", categoria=actual, valores=valores, categorias=lista)


@bp.route("/categorias/<int:id_categoria>/eliminar", methods=["POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def categoria_eliminar(id_categoria):
    try:
        datos = api.llamar("DELETE", f"/categorias/{id_categoria}")
        catalogos.olvidar()
        flash(datos.get("mensaje") or "Categoría eliminada correctamente", "exito")
    except api.ApiError as exc:
        flash(exc.mensaje, "error")
    return redirect(url_for("admin.categorias"))


# =============================================================================
# A3 Pedidos / 7.2 Detalle (vista reducida) / 7.3 Actualizar estado
# =============================================================================
@bp.route("/pedidos")
@rol_requerido(ROL_ADMINISTRADOR)
def pedidos():
    # Regla de Ian: la pantalla abre con estado=Pendiente; "Todos" lo quita.
    filtro = FiltroPedidosDTO.from_form(request.args, estado_por_defecto="Pendiente")
    pagina, error = None, None
    try:
        pagina = PaginaPedidosDTO.from_api(api.llamar("GET", "/admin/pedidos", params=filtro.to_dict()))
    except api.ApiError as exc:
        error = exc.mensaje
    except ErrorRespuesta:
        error = MSG_ERROR_INTERNO
    return render_template("admin/pedidos.html", filtro=filtro, pagina=pagina, error=error,
                           estados=ESTADOS_PEDIDO)


@bp.route("/pedidos/<int:id_pedido>")
@rol_requerido(ROL_ADMINISTRADOR)
def pedido(id_pedido):
    try:
        detalle = PedidoDetalleDTO.from_api(api.llamar("GET", f"/pedidos/{id_pedido}"))
    except api.ApiError as exc:
        return render_template("error.html", mensaje=exc.mensaje), exc.status if exc.status in (400, 404) else 500
    except ErrorRespuesta:
        return render_template("error.html", mensaje=MSG_ERROR_INTERNO), 500
    return render_template("pedido_detalle.html", pedido=detalle, es_admin=True,
                           siguientes=TRANSICIONES_PEDIDO.get(detalle.estado, ()),
                           volver=url_for("admin.pedidos"))


@bp.route("/pedidos/<int:id_pedido>/estado", methods=["POST"])
@rol_requerido(ROL_ADMINISTRADOR)
def pedido_estado(id_pedido):
    try:
        dto = EstadoPedidoDTO.from_form(request.form)
        datos = api.llamar("PATCH", f"/admin/pedidos/{id_pedido}/estado", json=dto.to_dict())
        flash(datos.get("mensaje") or "Estado del pedido actualizado correctamente", "exito")
    except (ErrorValidacion, api.ApiError) as exc:
        flash(_mensaje(exc), "error")
    return redirect(url_for("admin.pedido", id_pedido=id_pedido))


# =============================================================================
# 8.2 Reporte de ventas por vendedor (sp_HistorialVentas)
# =============================================================================
def _vendedores():
    """Selector con la 1.4 (rol=Vendedor), Activos e Inactivos (su historial
    sigue siendo válido). Hasta VENDEDORES_MAX_PAGINAS páginas de 20."""
    lista, params = [], {"rol": ROL_VENDEDOR}
    for _ in range(VENDEDORES_MAX_PAGINAS):
        pagina = PaginaUsuariosDTO.from_api(api.llamar("GET", "/admin/usuarios", params=params))
        lista.extend(pagina.usuarios)
        if pagina.siguiente_cursor is None:
            break
        params = {"rol": ROL_VENDEDOR, "cursor": str(pagina.siguiente_cursor)}
    return sorted(lista, key=lambda u: u.nombre_completo.lower())


@bp.route("/ventas")
@rol_requerido(ROL_ADMINISTRADOR)
def ventas():
    fechas = {c: request.args.get(c, "").strip() for c in ("id_vendedor", "fecha_inicio", "fecha_fin")}
    reporte, error, vendedores = None, None, []
    try:
        vendedores = _vendedores()
    except (api.ApiError, ErrorRespuesta) as exc:
        error = getattr(exc, "mensaje", MSG_ERROR_INTERNO)
    if any(fechas.values()) and not error:
        try:
            dto = FiltroVentasAdminDTO.from_form(request.args)
            reporte = ReporteVentasDTO.from_api(api.llamar("GET", "/admin/ventas", params=dto.to_dict()))
        except (ErrorValidacion, api.ApiError) as exc:
            error = _mensaje(exc)
        except ErrorRespuesta:
            error = MSG_ERROR_INTERNO
    return render_template("admin/ventas.html", titulo="Ventas por vendedor", accion=url_for("admin.ventas"),
                           fechas=fechas, reporte=reporte, error=error, vendedores=vendedores)
