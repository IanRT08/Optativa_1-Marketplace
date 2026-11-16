"""DTOs de la interfaz web.

- Solicitud: from_form() valida solo la forma (obligatorios, tipos y longitudes
  iguales a las de las Lambdas) y to_dict() arma el body para API Gateway.
  Las reglas de negocio (formato de correo, fuerza de la contraseña,
  correo duplicado...) las valida la Lambda; Flask muestra su mensaje exacto.
- Respuesta: from_api() normaliza lo que devuelve la API para las plantillas.

Los campos sensibles (contraseñas, token) llevan repr=False para que nunca
aparezcan si un DTO se imprime o termina en un log.
"""
from dataclasses import asdict, dataclass, field

from constantes import (
    EMAIL_MAX,
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_CORREO_FORMATO,
    MSG_NOMBRE_LARGO,
    NOMBRE_MAX,
    ROLES,
)


class ErrorValidacion(ValueError):
    """Dato con forma inválida. El texto es el mensaje para el usuario."""


class ErrorRespuesta(ValueError):
    """La API respondió con una forma inesperada (se muestra error interno)."""


# --- Utilidades de lectura ----------------------------------------------------
def _texto(form, campo):
    """Texto sin espacios a los lados ('' si falta)."""
    valor = form.get(campo)
    return valor.strip() if isinstance(valor, str) else ""


def _password(form, campo):
    """Contraseña tal cual: los espacios son parte de ella (igual que la Lambda)."""
    valor = form.get(campo)
    return valor if isinstance(valor, str) else ""


def _obligatorios(*valores):
    if any(v == "" for v in valores):
        raise ErrorValidacion(MSG_CAMPOS_OBLIGATORIOS)


def _entero(datos, campo):
    valor = datos.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorRespuesta(campo)
    return valor


def _cadena(datos, campo, obligatorio=True):
    valor = datos.get(campo)
    if isinstance(valor, str) and (valor or not obligatorio):
        return valor
    if valor is None and not obligatorio:
        return ""
    raise ErrorRespuesta(campo)


# =============================================================================
# DFR 1.1 Registro de usuario (Comprador) -> POST /usuarios/registro
# =============================================================================
@dataclass(frozen=True)
class RegistroDTO:
    nombre: str
    apellido: str
    email: str
    password: str = field(repr=False)
    confirmar_password: str = field(repr=False)

    @classmethod
    def from_form(cls, form):
        dto = cls(
            nombre=_texto(form, "nombre"),
            apellido=_texto(form, "apellido"),
            email=_texto(form, "email"),
            password=_password(form, "password"),
            confirmar_password=_password(form, "confirmar_password"),
        )
        _obligatorios(dto.nombre, dto.apellido, dto.email,
                      dto.password, dto.confirmar_password)
        if len(dto.nombre) > NOMBRE_MAX or len(dto.apellido) > NOMBRE_MAX:
            raise ErrorValidacion(MSG_NOMBRE_LARGO)
        if len(dto.email) > EMAIL_MAX:
            # La Lambda responde lo mismo con un correo de más de 150.
            raise ErrorValidacion(MSG_CORREO_FORMATO)
        return dto

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class RegistroRespuestaDTO:
    mensaje: str
    id_usuario: int

    @classmethod
    def from_api(cls, datos):
        return cls(mensaje=_cadena(datos, "mensaje"),
                   id_usuario=_entero(datos, "id_usuario"))

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 1.2 Inicio de sesión -> POST /auth/login
# =============================================================================
@dataclass(frozen=True)
class LoginDTO:
    email: str
    password: str = field(repr=False)

    @classmethod
    def from_form(cls, form):
        dto = cls(email=_texto(form, "email"), password=_password(form, "password"))
        _obligatorios(dto.email, dto.password)
        if len(dto.email) > EMAIL_MAX:
            # Ese correo no puede existir en la BD (VARCHAR(150)).
            raise ErrorValidacion(MSG_CORREO_FORMATO)
        return dto

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class SesionDTO:
    """Respuesta 200 de la 1.2. Lo que se guarda en la sesión del servidor."""
    token: str = field(repr=False)
    expira_en: int
    id_usuario: int
    nombre: str
    apellido: str
    rol: str

    @classmethod
    def from_api(cls, datos):
        dto = cls(
            token=_cadena(datos, "token"),
            expira_en=_entero(datos, "expira_en"),
            id_usuario=_entero(datos, "id_usuario"),
            nombre=_cadena(datos, "nombre"),
            apellido=_cadena(datos, "apellido"),
            rol=_cadena(datos, "rol"),
        )
        if dto.rol not in ROLES or dto.expira_en <= 0:
            raise ErrorRespuesta("rol")
        return dto

    def to_dict(self):
        return asdict(self)
