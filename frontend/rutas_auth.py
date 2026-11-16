"""DFR 1.1 Registro de usuario y DFR 1.2 Inicio de sesión."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

import api
from constantes import MSG_ERROR_INTERNO, MSG_REGISTRO_EXITOSO
from dtos import (
    ErrorRespuesta,
    ErrorValidacion,
    LoginDTO,
    RegistroDTO,
    RegistroRespuestaDTO,
    SesionDTO,
)
from seguridad import cerrar_sesion, destino_por_rol, hay_sesion, iniciar_sesion

bp = Blueprint("auth", __name__)


def _iniciar_con_api(login_dto):
    """POST /auth/login y guarda la sesión. Lanza ApiError si la API rechaza."""
    datos = api.llamar("POST", "/auth/login", json=login_dto.to_dict(), token=None)
    try:
        sesion = SesionDTO.from_api(datos)
    except ErrorRespuesta:
        raise api.ApiError(500, MSG_ERROR_INTERNO) from None
    iniciar_sesion(sesion)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if hay_sesion():
        return redirect(destino_por_rol())

    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        try:
            _iniciar_con_api(LoginDTO.from_form(request.form))
            return redirect(destino_por_rol())
        except (ErrorValidacion, api.ApiError) as exc:
            flash(getattr(exc, "mensaje", str(exc)), "error")
    # La contraseña nunca se devuelve al formulario.
    return render_template("login.html", email=email)


@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if hay_sesion():
        return redirect(destino_por_rol())

    previo = {}
    if request.method == "POST":
        previo = {c: request.form.get(c, "").strip() for c in ("nombre", "apellido", "email")}
        try:
            dto = RegistroDTO.from_form(request.form)
            datos = api.llamar("POST", "/usuarios/registro", json=dto.to_dict(), token=None)
            RegistroRespuestaDTO.from_api(datos)
        except (ErrorValidacion, api.ApiError) as exc:
            flash(getattr(exc, "mensaje", str(exc)), "error")
            return render_template("registro.html", previo=previo)
        except ErrorRespuesta:
            flash(MSG_ERROR_INTERNO, "error")
            return render_template("registro.html", previo=previo)

        # DFR 1.1: "Registro exitoso", redirigiendo a la pantalla principal.
        # La 1.1 no devuelve token, así que se inicia sesión con la 1.2.
        try:
            _iniciar_con_api(LoginDTO(email=dto.email, password=dto.password))
        except api.ApiError:
            flash(MSG_REGISTRO_EXITOSO, "exito")
            return redirect(url_for("auth.login"))
        flash(MSG_REGISTRO_EXITOSO, "exito")
        return redirect(url_for("inicio"))

    return render_template("registro.html", previo=previo)


@bp.route("/logout", methods=["POST"])
def logout():
    cerrar_sesion()
    return redirect(url_for("auth.login"))
