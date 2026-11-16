"""Cliente único de API Gateway.

Flask nunca se conecta a RDS ni a DynamoDB: todo pasa por aquí.
Nunca se registran tokens, bodies ni respuestas de la API; al usuario solo le
llega el texto de "error" de la Lambda (mensaje del DFR) o el error interno.
"""
import requests
from flask import current_app, session

from constantes import API_TIMEOUT_S, MSG_ACCESO_RESTRINGIDO, MSG_ERROR_INTERNO

# Una sesión HTTP reutilizada (conexiones keep-alive hacia API Gateway).
_http = requests.Session()


class ApiError(Exception):
    """Error que se muestra al usuario con su mensaje tal cual."""

    def __init__(self, status, mensaje):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


class _ErrorDeSesion(Exception):
    """No hereda de ApiError a propósito: las rutas atrapan ApiError para
    mostrar mensajes, y estos dos deben llegar siempre a los manejadores
    globales de app.py (cerrar sesión / página de acceso restringido)."""

    def __init__(self, status, mensaje):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


class SesionExpirada(_ErrorDeSesion):
    """401 en una ruta con token: se cierra la sesión y se manda al login."""


class AccesoRestringido(_ErrorDeSesion):
    """403 "Acceso restringido": se muestra la página de acceso restringido."""


def llamar(metodo, ruta, *, json=None, params=None, token="sesion"):
    """Llama a API Gateway y devuelve el body (dict) de una respuesta 2xx.

    token="sesion": manda el JWT de la sesión si existe (rutas protegidas y 4.2).
    token=None: no manda Authorization (registro y login).
    Lanza ApiError / SesionExpirada / AccesoRestringido en cualquier otro caso.
    """
    headers = {"Accept": "application/json"}
    jwt = session.get("token") if token == "sesion" else None
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"

    url = current_app.config["API_BASE_URL"] + ruta
    try:
        resp = _http.request(metodo, url, json=json, params=params,
                             headers=headers, timeout=API_TIMEOUT_S)
    except requests.RequestException as exc:
        # Solo el tipo de error y la ruta: nunca headers ni body.
        current_app.logger.warning("Sin respuesta de la API en %s %s (%s)",
                                   metodo, ruta, type(exc).__name__)
        raise ApiError(503, MSG_ERROR_INTERNO) from None

    try:
        datos = resp.json()
    except ValueError:
        datos = None
    if not isinstance(datos, dict):
        datos = {}

    if 200 <= resp.status_code < 300:
        return datos

    # Las Lambdas responden {"error": "..."}; API Gateway responde
    # {"message": "..."} (en inglés) y eso se traduce a error interno.
    mensaje = datos.get("error")
    if not isinstance(mensaje, str) or not mensaje:
        mensaje = MSG_ERROR_INTERNO
    if resp.status_code >= 500:
        current_app.logger.warning("La API respondió %s en %s %s",
                                   resp.status_code, metodo, ruta)
        mensaje = MSG_ERROR_INTERNO

    # 401/403 de la 1.2 (contraseña incorrecta, cuenta inactiva) no llevan
    # token: son mensajes del DFR para el formulario, no cierres de sesión.
    if jwt and resp.status_code == 401:
        raise SesionExpirada(401, mensaje)
    if jwt and resp.status_code == 403 and mensaje == MSG_ACCESO_RESTRINGIDO:
        raise AccesoRestringido(403, mensaje)
    raise ApiError(resp.status_code, mensaje)
