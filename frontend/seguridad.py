"""Sesión, control de acceso por rol y encabezados de seguridad.

El decorador de rol protege las pantallas; NO sustituye la validación de la
API: cada Lambda vuelve a revisar el token y el rol.
"""
import time
from functools import wraps

from flask import abort, current_app, flash, redirect, request, session, url_for

from constantes import MSG_SESION_INVALIDA, ROL_ADMINISTRADOR, ROL_COMPRADOR, ROL_VENDEDOR

# Pantalla de inicio de cada rol después del login (DFR 1.2: "según el rol").
# Se irá ajustando al construir las etapas de Vendedor y Administrador.
DESTINO_POR_ROL = {
    ROL_COMPRADOR: "catalogo.inicio",
    ROL_VENDEDOR: "vendedor.productos",
    ROL_ADMINISTRADOR: "catalogo.inicio",
}


# --- Sesión --------------------------------------------------------------------
def iniciar_sesion(sesion_dto):
    """Guarda la sesión del servidor con un id nuevo (evita fijación de sesión)."""
    session.clear()
    session.permanent = True
    session["token"] = sesion_dto.token
    session["expira"] = int(time.time()) + sesion_dto.expira_en
    session["id_usuario"] = sesion_dto.id_usuario
    session["nombre"] = sesion_dto.nombre
    session["apellido"] = sesion_dto.apellido
    session["rol"] = sesion_dto.rol
    # Después de llenarla: Flask-Session no regenera una sesión vacía.
    current_app.session_interface.regenerate(session)


def cerrar_sesion(mensaje=None):
    session.clear()
    if mensaje:
        flash(mensaje, "error")


def hay_sesion():
    """True si hay token y no ha vencido. Si venció, limpia la sesión."""
    if not session.get("token"):
        return False
    if int(time.time()) >= session.get("expira", 0):
        cerrar_sesion(MSG_SESION_INVALIDA)
        return False
    return True


def destino_por_rol():
    return url_for(DESTINO_POR_ROL.get(session.get("rol"), "catalogo.inicio"))


def ruta_interna(ruta):
    """Solo rutas de este sitio ("/x"), nunca "//otro.com" ni "\\": evita
    redirecciones abiertas."""
    return (isinstance(ruta, str) and ruta.startswith("/") and not ruta.startswith("//")
            and "\\" not in ruta and all(32 < ord(c) < 127 for c in ruta))


def recordar_destino(ruta):
    """Página a la que se vuelve después de iniciar sesión."""
    if ruta_interna(ruta):
        session["volver_a"] = ruta


def tomar_destino():
    """Saca de la sesión la página guardada (antes de iniciar_sesion, que la limpia)."""
    ruta = session.pop("volver_a", None)
    return ruta if ruta_interna(ruta) else None


def mandar_a_login():
    """DFR 5.1: sin sesión se redirige a la pantalla de inicio de sesión."""
    if request.method == "GET":
        recordar_destino(request.path)
    return redirect(url_for("auth.login"))


# --- Decoradores -----------------------------------------------------------------
def login_requerido(f):
    """Sin sesión válida -> pantalla de inicio de sesión (DFR 5.1)."""
    @wraps(f)
    def envoltura(*args, **kwargs):
        if not hay_sesion():
            return mandar_a_login()
        return f(*args, **kwargs)
    return envoltura


def rol_requerido(*roles):
    """Sesión válida y rol permitido; si no, "Acceso restringido" (403)."""
    def decorador(f):
        @wraps(f)
        @login_requerido
        def envoltura(*args, **kwargs):
            if session.get("rol") not in roles:
                abort(403)
            return f(*args, **kwargs)
        return envoltura
    return decorador


# --- Encabezados -----------------------------------------------------------------
# Sin scripts ni estilos inline ni de terceros. Las imágenes de producto
# vienen de URLs http/https externas (DynamoDB URLImagen).
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' https: http:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def agregar_encabezados(resp):
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if resp.mimetype == "text/html":
        # Que "Atrás" después de cerrar sesión no muestre datos guardados.
        resp.headers["Cache-Control"] = "no-store"
    return resp
