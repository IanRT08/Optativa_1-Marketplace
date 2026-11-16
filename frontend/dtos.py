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
from typing import Optional
from urllib.parse import urlsplit

from constantes import (
    BUSQUEDA_MAX,
    EMAIL_MAX,
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_CORREO_FORMATO,
    MSG_NOMBRE_LARGO,
    NOMBRE_MAX,
    ROLES,
    URL_IMAGEN_MAX,
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


def _numero(datos, campo):
    valor = datos.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorRespuesta(campo)
    return float(valor)


def _entero_opcional(datos, campo):
    valor = datos.get(campo)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def url_segura(url):
    """URL de imagen solo si es http(s) bien formada; si no, None (sin imagen)."""
    if not isinstance(url, str) or not url or len(url) > URL_IMAGEN_MAX:
        return None
    if any(c.isspace() or ord(c) < 32 for c in url):
        return None
    partes = urlsplit(url)
    if partes.scheme.lower() not in ("http", "https") or not partes.netloc:
        return None
    return url


def _mapa_texto(valor):
    """Objeto nombre -> valor de DynamoDB como {str: str} para las plantillas."""
    if not isinstance(valor, dict):
        return {}
    salida = {}
    for clave, dato in valor.items():
        if isinstance(clave, str) and isinstance(dato, (str, int, float)) and not isinstance(dato, bool):
            salida[clave] = str(dato)
    return salida


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


# =============================================================================
# DFR 2.2 Consultar categorías -> GET /categorias (filtro del catálogo)
# =============================================================================
@dataclass(frozen=True)
class CategoriaDTO:
    id_categoria: int
    nombre: str
    categoria_padre: str

    @property
    def etiqueta(self):
        return f"{self.nombre} ({self.categoria_padre})" if self.categoria_padre else self.nombre

    @classmethod
    def lista_from_api(cls, datos):
        filas = datos.get("categorias")
        if not isinstance(filas, list):
            raise ErrorRespuesta("categorias")
        return [cls(id_categoria=_entero(f, "id_categoria"),
                    nombre=_cadena(f, "nombre"),
                    categoria_padre=_cadena(f, "categoria_padre", obligatorio=False))
                for f in filas if isinstance(f, dict)]

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 4.1 Buscar y filtrar productos -> GET /productos
# =============================================================================
@dataclass(frozen=True)
class BusquedaDTO:
    """Filtros opcionales y combinables. El rango y el formato del precio los
    valida la Lambda ("El precio mínimo no puede ser mayor al máximo")."""
    q: str = ""
    id_categoria: str = ""
    precio_min: str = ""
    precio_max: str = ""
    cursor: str = ""

    @classmethod
    def from_form(cls, args):
        return cls(
            q=_texto(args, "q")[:BUSQUEDA_MAX],
            id_categoria=_texto(args, "id_categoria"),
            precio_min=_texto(args, "precio_min"),
            precio_max=_texto(args, "precio_max"),
            cursor=_texto(args, "cursor"),
        )

    def to_dict(self):
        """Solo los filtros con valor (query string de la 4.1)."""
        return {k: v for k, v in asdict(self).items() if v}

    def filtros(self):
        """Los filtros sin el cursor (para armar el enlace de la página siguiente)."""
        return {k: v for k, v in self.to_dict().items() if k != "cursor"}


@dataclass(frozen=True)
class ProductoResumenDTO:
    id_producto: int
    nombre: str
    precio: float
    marca: str
    categoria: str
    url_imagen: Optional[str]

    @classmethod
    def from_api(cls, datos):
        return cls(
            id_producto=_entero(datos, "id_producto"),
            nombre=_cadena(datos, "nombre"),
            precio=_numero(datos, "precio"),
            marca=_cadena(datos, "marca", obligatorio=False),
            categoria=_cadena(datos, "categoria", obligatorio=False),
            url_imagen=url_segura(datos.get("url_imagen")),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PaginaProductosDTO:
    mensaje: str
    productos: list
    siguiente_cursor: Optional[str]

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("productos")
        if not isinstance(filas, list):
            raise ErrorRespuesta("productos")
        cursor = datos.get("siguiente_cursor")
        return cls(
            mensaje=_cadena(datos, "mensaje", obligatorio=False),
            productos=[ProductoResumenDTO.from_api(f) for f in filas if isinstance(f, dict)],
            siguiente_cursor=cursor if isinstance(cursor, str) and cursor else None,
        )

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 4.2 Consultar detalle de producto -> GET /productos/{id}
# =============================================================================
@dataclass(frozen=True)
class VarianteDTO:
    id_variante: int
    sku: str
    atributos: dict
    disponible: bool
    stock: Optional[int]   # None para el visitante (solo ve disponible)

    @classmethod
    def from_api(cls, datos):
        return cls(
            id_variante=_entero(datos, "id_variante"),
            sku=_cadena(datos, "sku"),
            atributos=_mapa_texto(datos.get("atributos")),
            disponible=datos.get("disponible") is True,
            stock=_entero_opcional(datos, "stock"),
        )

    @property
    def es_estandar(self):
        return self.sku.endswith("-STD")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class LogisticaDTO:
    alto: str
    ancho: str
    profundidad: str
    peso_kg: str
    requiere_fragil: bool
    tipo_empaque: str

    @classmethod
    def from_api(cls, datos):
        """LogisticaEnvio de DynamoDB (estándar de Ian) o None si no viene."""
        if not isinstance(datos, dict):
            return None
        medidas = _mapa_texto(datos.get("DimensionesCm"))
        peso = _mapa_texto({"p": datos.get("PesoKg")}).get("p", "")
        return cls(
            alto=medidas.get("Alto", ""),
            ancho=medidas.get("Ancho", ""),
            profundidad=medidas.get("Profundidad", ""),
            peso_kg=peso,
            requiere_fragil=datos.get("RequiereFragil") is True,
            tipo_empaque=datos.get("TipoEmpaque") if isinstance(datos.get("TipoEmpaque"), str) else "",
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ProductoDetalleDTO:
    id_producto: int
    nombre: str
    descripcion: str
    detalles: dict
    precio: float
    marca: str
    categoria: str
    url_imagen: Optional[str]
    vendedor: str
    especificaciones: dict
    logistica: Optional[LogisticaDTO]
    disponible: bool
    stock: Optional[int]   # DFR 4.2 "stock disponible": exacto solo con sesión
    variantes: list

    @classmethod
    def from_api(cls, datos):
        p = datos.get("producto")
        if not isinstance(p, dict):
            raise ErrorRespuesta("producto")
        variantes = p.get("variantes") if isinstance(p.get("variantes"), list) else []
        return cls(
            id_producto=_entero(p, "id_producto"),
            nombre=_cadena(p, "nombre"),
            descripcion=_cadena(p, "descripcion", obligatorio=False),
            detalles=_mapa_texto(p.get("detalles")),
            precio=_numero(p, "precio"),
            marca=_cadena(p, "marca", obligatorio=False),
            categoria=_cadena(p, "categoria", obligatorio=False),
            url_imagen=url_segura(p.get("url_imagen")),
            vendedor=_cadena(p, "vendedor", obligatorio=False),
            especificaciones=_mapa_texto(p.get("especificaciones")),
            logistica=LogisticaDTO.from_api(p.get("logistica_envio")),
            disponible=p.get("disponible") is True,
            stock=_entero_opcional(p, "stock"),
            variantes=[VarianteDTO.from_api(v) for v in variantes if isinstance(v, dict)],
        )

    @property
    def tiene_variantes(self):
        """True si hay variantes además de la estándar (3.6)."""
        return any(not v.es_estandar for v in self.variantes)

    def to_dict(self):
        return asdict(self)
