"""
smavib_common.py: código compartido por las Lambdas de SMAVIB (Layer 2).

Ubicación dentro del zip de la Layer:  python/smavib_common.py
Requiere la Layer 1 (PyMySQL, bcrypt, PyJWT).

Variables de entorno que lee (solo cuando se usan):
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME   -> obtener_conexion()
    JWT_SECRET                               -> emitir_token() / validar_token()
"""
import base64
import datetime
import functools
import json
import os
import re
import traceback
from decimal import Decimal

import jwt
import pymysql
import pymysql.cursors

# ---------------------------------------------------------------------------
# Mensajes comunes (DFR + mensajes adicionales aprobados por Ian)
# ---------------------------------------------------------------------------
MSG_ERROR_INTERNO = "Ocurrió un error interno. Intenta más tarde"
MSG_SESION_INVALIDA = "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"
MSG_ACCESO_RESTRINGIDO = "Acceso restringido"
MSG_CAMPOS_OBLIGATORIOS = "Debe completar los campos obligatorios"
MSG_SIN_REGISTROS = "No se encontraron registros"
MSG_CORREO_REGISTRADO = "El correo electrónico ya está registrado"
MSG_CORREO_FORMATO = "El formato del correo electrónico no es válido"  # aprobado por Ian
MSG_PASSWORD_INVALIDA = (
    "La contraseña debe tener mínimo 8 caracteres, una mayúscula, "
    "un número y un carácter especial"
)
MSG_NOMBRE_LARGO = "El nombre y el apellido no pueden superar 80 caracteres"  # aprobado por Ian

# Roles (tabla rol)
ROL_ADMINISTRADOR = "Administrador"
ROL_VENDEDOR = "Vendedor"
ROL_COMPRADOR = "Comprador"

# Configuración del token
JWT_ALGORITMO = "HS256"
SESION_HORAS = 2

# errno de MySQL para SIGNAL SQLSTATE '45000' (ER_SIGNAL_EXCEPTION) en los SP
ERRNO_SIGNAL = 1644

HEADERS = {"Content-Type": "application/json; charset=utf-8"}


# ---------------------------------------------------------------------------
# Errores de negocio
# ---------------------------------------------------------------------------
class ErrorNegocio(Exception):
    """Error controlado que se devuelve al usuario con un status y un mensaje."""

    def __init__(self, status, mensaje):
        super().__init__(mensaje)
        self.status = status
        self.mensaje = mensaje


# ---------------------------------------------------------------------------
# Respuestas para API Gateway (integración proxy)
# ---------------------------------------------------------------------------
class SmavibEncoder(json.JSONEncoder):
    """Serializa Decimal (DynamoDB y DECIMAL de MySQL) y fechas."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            # Decimal('20') -> 20 ; Decimal('199.99') / Decimal('100.00') -> float
            return int(obj) if obj.as_tuple().exponent >= 0 else float(obj)
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super().default(obj)


def respuesta(status, cuerpo):
    return {
        "statusCode": status,
        "headers": HEADERS,
        "body": json.dumps(cuerpo, cls=SmavibEncoder, ensure_ascii=False),
    }


def ok(mensaje, status=200, **datos):
    """Éxito: {'mensaje': ..., <datos extra>}"""
    cuerpo = {"mensaje": mensaje}
    cuerpo.update(datos)
    return respuesta(status, cuerpo)


def error(status, mensaje):
    """Error: {'error': ...}"""
    return respuesta(status, {"error": mensaje})


# ---------------------------------------------------------------------------
# Lectura del evento
# ---------------------------------------------------------------------------
def leer_body(event):
    """Devuelve el body como dict (números con punto como Decimal)."""
    cuerpo = event.get("body")
    if not cuerpo:
        return {}
    if event.get("isBase64Encoded"):
        cuerpo = base64.b64decode(cuerpo).decode("utf-8")
    try:
        datos = json.loads(cuerpo, parse_float=Decimal)
    except (ValueError, TypeError):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if not isinstance(datos, dict):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    return datos


def path_param(event, nombre):
    return (event.get("pathParameters") or {}).get(nombre)


def query_params(event):
    return event.get("queryStringParameters") or {}


def campo_texto(datos, nombre):
    """Texto sin espacios a los lados; '' si falta o no es texto."""
    valor = datos.get(nombre)
    return valor.strip() if isinstance(valor, str) else ""


def campo_password(datos, nombre):
    """Contraseña tal cual (no se recorta: los espacios son parte de ella)."""
    valor = datos.get(nombre)
    return valor if isinstance(valor, str) else ""


# ---------------------------------------------------------------------------
# Validaciones de usuario (DFR 1.1, 1.3 y 1.5)
# ---------------------------------------------------------------------------
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX = 150  # usuario.email VARCHAR(150)
NOMBRE_MAX = 80  # usuario.nombre y usuario.apellido VARCHAR(80)


def nombre_valido(nombre, apellido):
    return len(nombre) <= NOMBRE_MAX and len(apellido) <= NOMBRE_MAX


# ---------------------------------------------------------------------------
# Validación de textos libres (regla de Ian, 2026-11-13). Se aplica a nombres,
# descripciones, calles, etc. NO se aplica a correos, contraseñas ni URLs.
# El texto llega ya recortado con campo_texto(): si era solo espacios queda ''
# y la Lambda responde "Debe completar los campos obligatorios" (DFR).
# ---------------------------------------------------------------------------
_RE_ESPACIOS_SEGUIDOS = re.compile(r"[ \t]{2,}")
_RE_ENTERO = re.compile(r"[0-9]+")
MAX_ESPECIALES_SEGUIDOS = 2


def _racha_especiales(texto):
    """Mayor cantidad de caracteres especiales seguidos (ni letra, ni número, ni espacio)."""
    mayor = actual = 0
    for c in texto:
        if not c.isalnum() and not c.isspace():
            actual += 1
            mayor = max(mayor, actual)
        else:
            actual = 0
    return mayor


def validar_texto(texto, etiqueta, permitir_solo_numeros=False):
    """
    Lanza ErrorNegocio(400) si el texto:
      - tiene dos o más espacios en blanco seguidos
      - tiene más de dos caracteres especiales seguidos
      - contiene solo números (salvo permitir_solo_numeros=True, p. ej. número exterior)
    'etiqueta' es el nombre del campo con artículo, p. ej. "El nombre".
    """
    if _RE_ESPACIOS_SEGUIDOS.search(texto):
        raise ErrorNegocio(400, f"{etiqueta} no puede tener espacios en blanco seguidos")
    if _racha_especiales(texto) > MAX_ESPECIALES_SEGUIDOS:
        raise ErrorNegocio(400, f"{etiqueta} no puede tener más de dos caracteres especiales seguidos")
    if not permitir_solo_numeros and texto.replace(" ", "").isdigit():
        raise ErrorNegocio(400, f"{etiqueta} no puede contener solo números")


def entero_positivo(valor):
    """Devuelve el entero > 0 que viene como int o texto ('12'); si no, None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
        return numero if numero > 0 else None
    return None


def email_valido(email):
    return len(email) <= EMAIL_MAX and bool(_RE_EMAIL.match(email))


def password_valida(password):
    """Mínimo 8 caracteres, una mayúscula, un número y un carácter especial."""
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.isdigit() for c in password)
        and any(not c.isalnum() and not c.isspace() for c in password)
    )


# ---------------------------------------------------------------------------
# Hash de contraseñas con bcrypt (Layer 1)
# ---------------------------------------------------------------------------
def _password_bytes(password):
    # bcrypt solo usa los primeros 72 bytes; se recorta igual al generar y al
    # verificar (las versiones nuevas de bcrypt lanzan error si se pasa de 72).
    return password.encode("utf-8")[:72]


def hashear_password(password):
    import bcrypt  # import diferido: solo lo cargan las Lambdas que lo usan

    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verificar_password(password, password_hash):
    import bcrypt

    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("ascii"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Conexión a MySQL (una sola, reutilizada entre invocaciones)
# ---------------------------------------------------------------------------
_conexion = None


def _crear_conexion():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        port=3306,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        # autocommit=True: cada SELECT ve datos frescos aunque la conexión se
        # reutilice. Las transacciones en Python (3.1, 3.6) usan
        # conexion.begin() + commit()/rollback(). Los SP manejan su propia
        # transacción (START TRANSACTION / COMMIT).
        autocommit=True,
        # Hora de México (UTC-6 fijo, sin horario de verano desde 2022). Así
        # NOW() y CURRENT_TIMESTAMP (también dentro de los SP) guardan la hora
        # local, y sp_HistorialVentas compara fechas en el mismo horario.
        # Se aplica también al reconectar (ping). Decisión de Ian, 2026-11-14.
        init_command="SET time_zone = '-06:00'",
        connect_timeout=5,
        read_timeout=15,
        write_timeout=15,
    )


def obtener_conexion():
    """Devuelve la conexión viva; si se cayó, reconecta (un reintento)."""
    global _conexion
    try:
        if _conexion is None or not _conexion.open:
            _conexion = _crear_conexion()
        else:
            _conexion.ping(reconnect=True)
    except pymysql.err.OperationalError as e:
        print(f"Reintentando conexión a MySQL: {e!r}")
        _conexion = _crear_conexion()
    return _conexion


def _deshacer_transaccion_pendiente():
    """Si quedó una transacción abierta por un error, la deshace."""
    if _conexion is not None and _conexion.open:
        try:
            _conexion.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# JWT (emitido por 1.2, validado en cada Lambda)
# ---------------------------------------------------------------------------
def emitir_token(id_usuario, rol):
    ahora = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(id_usuario),  # PyJWT exige que 'sub' sea texto
        "rol": rol,
        "iat": ahora,
        "exp": ahora + datetime.timedelta(hours=SESION_HORAS),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITMO)


def _leer_token(event):
    headers = event.get("headers") or {}
    for clave, valor in headers.items():
        if clave.lower() == "authorization" and valor:
            partes = valor.split()
            if len(partes) == 2 and partes[0].lower() == "bearer":
                return partes[1]
    return None


def validar_token(event, roles=None):
    """
    Valida 'Authorization: Bearer <token>' y devuelve
    {'id_usuario': int, 'rol': str}.
    - Token ausente, inválido o vencido -> 401 MSG_SESION_INVALIDA
    - Rol no permitido (si se indica 'roles') -> 403 MSG_ACCESO_RESTRINGIDO
    """
    token = _leer_token(event)
    if not token:
        raise ErrorNegocio(401, MSG_SESION_INVALIDA)
    try:
        claims = jwt.decode(
            token,
            os.environ["JWT_SECRET"],
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        usuario = {"id_usuario": int(claims["sub"]), "rol": claims.get("rol")}
    except (jwt.PyJWTError, ValueError, TypeError):
        raise ErrorNegocio(401, MSG_SESION_INVALIDA)

    if roles and usuario["rol"] not in roles:
        raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)
    return usuario


# ---------------------------------------------------------------------------
# Manejo de errores común (decorador para lambda_handler)
# ---------------------------------------------------------------------------
def manejar_errores(funcion):
    """
    - ErrorNegocio            -> su status y su mensaje
    - Error de SP (errno 1644) -> 400 con el mensaje exacto del SP
    - Cualquier otro error     -> 500 MSG_ERROR_INTERNO (se registra con print)
    """

    @functools.wraps(funcion)
    def envoltura(event, context):
        try:
            return funcion(event, context)
        except ErrorNegocio as e:
            _deshacer_transaccion_pendiente()
            return error(e.status, e.mensaje)
        except pymysql.err.MySQLError as e:
            _deshacer_transaccion_pendiente()
            if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL:
                return error(400, e.args[1])
            print(f"Error de MySQL: {e!r}")
            print(traceback.format_exc())
            return error(500, MSG_ERROR_INTERNO)
        except Exception as e:
            _deshacer_transaccion_pendiente()
            print(f"Error inesperado: {e!r}")
            print(traceback.format_exc())
            return error(500, MSG_ERROR_INTERNO)

    return envoltura
