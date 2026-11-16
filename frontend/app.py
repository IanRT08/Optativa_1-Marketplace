"""Interfaz web SMAVIB (Flask). Solo habla con API Gateway.

Ejecutar desde esta carpeta:  python app.py   (debug siempre apagado)
"""
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from flask_wtf.csrf import CSRFError, CSRFProtect

import api
from config import Config
from constantes import MSG_ACCESO_RESTRINGIDO, MSG_ERROR_INTERNO, MSG_SESION_INVALIDA
from rutas_auth import bp as auth_bp
from rutas_catalogo import bp as catalogo_bp
from rutas_comprador import bp as comprador_bp
from seguridad import agregar_encabezados, cerrar_sesion, hay_sesion


def crear_app():
    app = Flask(__name__)
    app.config.from_object(Config())

    Session(app)
    CSRFProtect(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(comprador_bp)
    app.after_request(agregar_encabezados)

    @app.template_filter("moneda")
    def moneda(valor):
        return f"${valor:,.2f}"

    @app.context_processor
    def usuario_actual():
        # Solo nombre y rol para las plantillas; el token nunca sale de aquí.
        if hay_sesion():
            return {"usuario": {"nombre": session.get("nombre"), "rol": session.get("rol")}}
        return {"usuario": None}

    # --- Errores -----------------------------------------------------------
    @app.errorhandler(api.SesionExpirada)
    def sesion_expirada(exc):
        cerrar_sesion(exc.mensaje)
        return redirect(url_for("auth.login"))

    @app.errorhandler(api.AccesoRestringido)
    def acceso_restringido_api(exc):
        return render_template("error.html", mensaje=MSG_ACCESO_RESTRINGIDO), 403

    @app.errorhandler(403)
    def acceso_restringido(_exc):
        return render_template("error.html", mensaje=MSG_ACCESO_RESTRINGIDO), 403

    @app.errorhandler(CSRFError)
    def csrf_invalido(_exc):
        # Formulario vencido o enviado desde otro sitio: se vuelve a pedir.
        flash(MSG_SESION_INVALIDA, "error")
        return redirect(request.path)

    @app.errorhandler(404)
    def no_encontrada(_exc):
        return render_template("error.html", mensaje="La página no existe"), 404

    @app.errorhandler(413)
    def demasiado_grande(_exc):
        return render_template("error.html", mensaje=MSG_ERROR_INTERNO), 413

    @app.errorhandler(500)
    def error_interno(_exc):
        return render_template("error.html", mensaje=MSG_ERROR_INTERNO), 500

    return app


app = crear_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
