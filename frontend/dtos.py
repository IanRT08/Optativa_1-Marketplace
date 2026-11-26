"""DTOs de la interfaz web.

- Solicitud: from_form() valida solo la forma (obligatorios, tipos y longitudes
  iguales a las de las Lambdas) y to_dict() arma el body para API Gateway.
  Las reglas de negocio (formato de correo, fuerza de la contraseña,
  correo duplicado...) las valida la Lambda; Flask muestra su mensaje exacto.
- Respuesta: from_api() normaliza lo que devuelve la API para las plantillas.

Los campos sensibles (contraseñas, token) llevan repr=False para que nunca
aparezcan si un DTO se imprime o termina en un log.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlsplit

from constantes import (
    BUSQUEDA_MAX,
    CALLE_MAX,
    CATEGORIA_DESCRIPCION_MAX,
    CATEGORIA_NOMBRE_MAX,
    CIUDAD_MAX,
    COLONIA_MAX,
    COMENTARIO_MAX,
    DESCRIPCION_MAX,
    EMAIL_MAX,
    EMPAQUE_MAX,
    ESPEC_MAX,
    ESPEC_NOMBRE_MAX,
    ESPEC_VALOR_MAX,
    ESTADO_MAX,
    ESTADOS_PEDIDO,
    ESTADOS_PRODUCTO,
    ESTADOS_USUARIO,
    MSG_CALIFICACION_NO_VALIDA,
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_CANTIDAD_ENTERA,
    MSG_COMENTARIO_LARGO,
    MSG_CORREO_FORMATO,
    MSG_DIRECCION_LARGA,
    MSG_CATEGORIA_LARGA,
    MSG_CATEGORIA_NO_EXISTE,
    MSG_CATEGORIA_PADRE_NO_EXISTE,
    MSG_COMBINACION_LARGA,
    MSG_DIRECCION_NO_VALIDA,
    MSG_ESPECIFICACIONES,
    MSG_ESTADO_NO_VALIDO,
    MSG_LOGISTICA,
    MSG_MARCA_NO_EXISTE,
    MSG_NOMBRE_LARGO,
    MSG_PRODUCTO_LARGO,
    MSG_PRODUCTO_NO_EXISTE,
    MSG_ROL_NO_VALIDO,
    MSG_STOCK_ENTERO,
    MSG_VALOR_NO_EXISTE,
    MSG_VARIANTE_NO_EXISTE,
    MSG_VENDEDOR_NO_EXISTE,
    NOMBRE_MAX,
    NUMERO_MAX,
    PRODUCTO_NOMBRE_MAX,
    ROLES,
    URL_IMAGEN_MAX,
    VALORES_VARIANTE_MAX,
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


def _entero_form(texto, mensaje):
    """Entero escrito en un formulario (solo dígitos ASCII, con signo opcional).
    El rango (mayor a cero, stock) lo valida la Lambda."""
    if not _RE_ENTERO.fullmatch(texto):
        raise ErrorValidacion(mensaje)
    return int(texto)


_RE_ENTERO = re.compile(r"[+-]?[0-9]{1,12}")


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
    descripcion: str = ""
    id_categoria_padre: Optional[int] = None

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
                    categoria_padre=_cadena(f, "categoria_padre", obligatorio=False),
                    descripcion=_cadena(f, "descripcion", obligatorio=False),
                    id_categoria_padre=_entero_opcional(f, "id_categoria_padre"))
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
    id_categoria: Optional[int]
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
            id_categoria=_entero_opcional(p, "id_categoria"),
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


# =============================================================================
# DFR 5.1 a 5.4 Carrito -> /carrito, /carrito/items
# =============================================================================
@dataclass(frozen=True)
class AgregarCarritoDTO:
    """5.1. id_variante es opcional: sin ella la Lambda usa la estándar."""
    id_producto: int
    cantidad: int
    id_variante: Optional[int] = None

    @classmethod
    def from_form(cls, form):
        producto, cantidad, variante = (_texto(form, c) for c in ("id_producto", "cantidad", "id_variante"))
        _obligatorios(producto, cantidad)
        return cls(
            id_producto=_entero_form(producto, MSG_PRODUCTO_NO_EXISTE),
            cantidad=_entero_form(cantidad, MSG_CANTIDAD_ENTERA),
            id_variante=_entero_form(variante, MSG_VARIANTE_NO_EXISTE) if variante else None,
        )

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class CantidadCarritoDTO:
    """5.3. La cantidad reemplaza a la actual. Con 0, Flask llama a la 5.4."""
    cantidad: int

    @classmethod
    def from_form(cls, form):
        cantidad = _texto(form, "cantidad")
        _obligatorios(cantidad)
        return cls(cantidad=_entero_form(cantidad, MSG_CANTIDAD_ENTERA))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class QuitarCarritoDTO:
    """5.4. Uno o varios id_variante (repetidos se cuentan una vez)."""
    variantes: tuple

    @classmethod
    def from_form(cls, form):
        valores = [v.strip() for v in form.getlist("variantes") if isinstance(v, str) and v.strip()]
        if not valores:
            raise ErrorValidacion(MSG_CAMPOS_OBLIGATORIOS)
        ids =tuple(dict.fromkeys(_entero_form(v, MSG_VARIANTE_NO_EXISTE) for v in valores))
        return cls(variantes=ids)

    @classmethod
    def de_una(cls, id_variante):
        return cls(variantes=(id_variante,))

    def to_dict(self):
        return {"variantes": list(self.variantes)}


@dataclass(frozen=True)
class ItemCarritoDTO:
    id_producto: int
    nombre: str
    id_variante: int
    sku: str
    atributos: dict
    precio: float
    cantidad: int
    subtotal: float
    url_imagen: Optional[str]
    disponible: bool
    stock: int
    stock_suficiente: bool

    @classmethod
    def from_api(cls, datos):
        return cls(
            id_producto=_entero(datos, "id_producto"),
            nombre=_cadena(datos, "nombre"),
            id_variante=_entero(datos, "id_variante"),
            sku=_cadena(datos, "sku", obligatorio=False),
            atributos=_mapa_texto(datos.get("atributos")),
            precio=_numero(datos, "precio"),
            cantidad=_entero(datos, "cantidad"),
            subtotal=_numero(datos, "subtotal"),
            url_imagen=url_segura(datos.get("url_imagen")),
            disponible=datos.get("disponible") is True,
            stock=_entero_opcional(datos, "stock") or 0,
            stock_suficiente=datos.get("stock_suficiente") is True,
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CarritoDTO:
    mensaje: str
    items: list
    total: float
    puede_comprar: bool

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("items")
        if not isinstance(filas, list):
            raise ErrorRespuesta("items")
        items = [ItemCarritoDTO.from_api(f) for f in filas if isinstance(f, dict)]
        return cls(
            mensaje=_cadena(datos, "mensaje", obligatorio=False),
            items=items,
            total=_numero(datos, "total"),
            # Se exige además que haya renglones: un carrito vacío no se compra.
            puede_comprar=datos.get("puede_comprar") is True and bool(items),
        )

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 9.1 a 9.3 Direcciones -> /direcciones
# =============================================================================
@dataclass(frozen=True)
class DireccionFormDTO:
    """9.1. El código postal va como texto (con número se pierde el 0 inicial);
    sus 5 dígitos los valida la Lambda."""
    calle: str
    numero: str
    colonia: str
    ciudad: str
    estado: str
    codigo_postal: str

    @classmethod
    def from_form(cls, form):
        dto = cls(**{c: _texto(form, c) for c in
                     ("calle", "numero", "colonia", "ciudad", "estado", "codigo_postal")})
        _obligatorios(*asdict(dto).values())
        if (len(dto.calle) > CALLE_MAX or len(dto.numero) > NUMERO_MAX
                or len(dto.colonia) > COLONIA_MAX or len(dto.ciudad) > CIUDAD_MAX
                or len(dto.estado) > ESTADO_MAX):
            raise ErrorValidacion(MSG_DIRECCION_LARGA)
        return dto

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DireccionDTO:
    id_direccion: int
    calle: str
    numero: str
    colonia: str
    ciudad: str
    estado: str
    codigo_postal: str

    @property
    def texto(self):
        return (f"{self.calle} {self.numero}, {self.colonia}, {self.ciudad}, "
                f"{self.estado}, C.P. {self.codigo_postal}")

    @classmethod
    def from_api(cls, datos):
        return cls(id_direccion=_entero(datos, "id_direccion"),
                   **{c: _cadena(datos, c, obligatorio=False) for c in
                      ("calle", "numero", "colonia", "ciudad", "estado", "codigo_postal")})

    @classmethod
    def lista_from_api(cls, datos):
        filas = datos.get("direcciones")
        if not isinstance(filas, list):
            raise ErrorRespuesta("direcciones")
        return [cls.from_api(f) for f in filas if isinstance(f, dict)]

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 6.1 Confirmar compra -> POST /compras (sp_RegistrarCompra)
# =============================================================================
@dataclass(frozen=True)
class CompraDTO:
    """Tarjeta y CVV: solo viajan en esta petición a la Lambda. No se guardan
    en la sesión, ni en cookies, ni en logs, ni vuelven al formulario. El
    formato (16 dígitos, CVV de 3) lo valida la Lambda: "Datos de pago no válidos"."""
    id_direccion: int
    numero_tarjeta: str = field(repr=False)
    cvv: str = field(repr=False)

    @classmethod
    def from_form(cls, form):
        direccion = _texto(form, "id_direccion")
        tarjeta = _texto(form, "numero_tarjeta")
        cvv = _texto(form, "cvv")
        _obligatorios(direccion, tarjeta, cvv)
        return cls(id_direccion=_entero_form(direccion, MSG_DIRECCION_NO_VALIDA),
                   numero_tarjeta=tarjeta, cvv=cvv)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CompraRespuestaDTO:
    mensaje: str
    id_pedido: int
    total: float

    @classmethod
    def from_api(cls, datos):
        return cls(mensaje=_cadena(datos, "mensaje"),
                   id_pedido=_entero(datos, "id_pedido"),
                   total=_numero(datos, "total"))

    def to_dict(self):
        return asdict(self)


# =============================================================================
# Catálogos de apoyo: A1 marcas, A2 atributos (formularios del Vendedor)
# =============================================================================
@dataclass(frozen=True)
class MarcaDTO:
    id_marca: int
    nombre: str

    @classmethod
    def lista_from_api(cls, datos):
        filas = datos.get("marcas")
        if not isinstance(filas, list):
            raise ErrorRespuesta("marcas")
        return [cls(_entero(f, "id_marca"), _cadena(f, "nombre")) for f in filas if isinstance(f, dict)]

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class AtributoDTO:
    id_atributo: int
    nombre: str
    valores: tuple   # ((id_valor, valor), ...)

    @classmethod
    def lista_from_api(cls, datos):
        filas = datos.get("atributos")
        if not isinstance(filas, list):
            raise ErrorRespuesta("atributos")
        salida = []
        for f in filas:
            if not isinstance(f, dict):
                continue
            valores = tuple((_entero(v, "id_valor"), _cadena(v, "valor"))
                            for v in (f.get("valores") or []) if isinstance(v, dict))
            salida.append(cls(_entero(f, "id_atributo"), _cadena(f, "nombre"), valores))
        return salida

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 3.1 Registrar / 3.3 Editar producto -> POST /vendedor/productos, PUT .../{id}
# =============================================================================
CAMPOS_PRODUCTO = ("nombre", "descripcion", "precio", "id_marca", "id_categoria", "url_imagen", "stock")
CAMPOS_LOGISTICA = ("alto", "ancho", "profundidad", "peso_kg", "tipo_empaque")


@dataclass(frozen=True)
class ProductoFormDTO:
    """Mismo body para 3.1 y 3.3 (en 3.3 es un PUT completo: sin
    especificaciones o logística, se quitan del catálogo). El precio va como
    texto: su formato, que sea mayor a cero y el rango los valida la Lambda."""
    nombre: str
    descripcion: str
    precio: str
    id_marca: int
    id_categoria: int
    url_imagen: str
    stock: int
    especificaciones: dict = field(default_factory=dict)
    logistica_envio: Optional[dict] = None

    @classmethod
    def from_form(cls, form):
        v = {c: _texto(form, c) for c in CAMPOS_PRODUCTO}
        _obligatorios(*v.values())
        if (len(v["nombre"]) > PRODUCTO_NOMBRE_MAX or len(v["descripcion"]) > DESCRIPCION_MAX
                or len(v["url_imagen"]) > URL_IMAGEN_MAX):
            raise ErrorValidacion(MSG_PRODUCTO_LARGO)
        return cls(
            nombre=v["nombre"],
            descripcion=v["descripcion"],
            precio=v["precio"],
            id_marca=_entero_form(v["id_marca"], MSG_MARCA_NO_EXISTE),
            id_categoria=_entero_form(v["id_categoria"], MSG_CATEGORIA_NO_EXISTE),
            url_imagen=v["url_imagen"],
            stock=_entero_form(v["stock"], MSG_STOCK_ENTERO),
            especificaciones=cls._especificaciones(form),
            logistica_envio=cls._logistica(form),
        )

    @staticmethod
    def _especificaciones(form):
        nombres = form.getlist("espec_nombre")
        valores = form.getlist("espec_valor")
        salida = {}
        for nombre, valor in zip(nombres, valores):
            nombre, valor = nombre.strip(), valor.strip()
            if not nombre and not valor:
                continue                      # renglón vacío del formulario
            _obligatorios(nombre, valor)      # renglón a medias
            if (nombre in salida or len(nombre) > ESPEC_NOMBRE_MAX
                    or len(valor) > ESPEC_VALOR_MAX or len(salida) >= ESPEC_MAX):
                raise ErrorValidacion(MSG_ESPECIFICACIONES)
            salida[nombre] = valor
        return salida

    @staticmethod
    def _logistica(form):
        if form.get("con_logistica") != "1":
            return None
        v = {c: _texto(form, f"log_{c}") for c in CAMPOS_LOGISTICA}
        _obligatorios(*v.values())
        if len(v["tipo_empaque"]) > EMPAQUE_MAX:
            raise ErrorValidacion(MSG_LOGISTICA)
        return {**v, "requiere_fragil": form.get("log_requiere_fragil") == "1"}

    def to_dict(self):
        datos = {c: getattr(self, c) for c in CAMPOS_PRODUCTO}
        if self.especificaciones:
            datos["especificaciones"] = dict(self.especificaciones)
        if self.logistica_envio:
            datos["logistica_envio"] = dict(self.logistica_envio)
        return datos


def valores_form_producto(detalle, id_marca):
    """Valores iniciales del formulario de 3.3 a partir del detalle (4.2)."""
    estandar = next((v for v in detalle.variantes if v.es_estandar), None)
    valores = {
        "nombre": detalle.nombre,
        "descripcion": detalle.descripcion,
        "precio": f"{detalle.precio:.2f}",
        "id_marca": str(id_marca or ""),
        "id_categoria": str(detalle.id_categoria or ""),
        "url_imagen": detalle.url_imagen or "",
        "stock": "" if estandar is None or estandar.stock is None else str(estandar.stock),
        "especificaciones": list(detalle.especificaciones.items()),
        "con_logistica": detalle.logistica is not None,
    }
    if detalle.logistica:
        lg = detalle.logistica
        valores.update(log_alto=lg.alto, log_ancho=lg.ancho, log_profundidad=lg.profundidad,
                       log_peso_kg=lg.peso_kg, log_tipo_empaque=lg.tipo_empaque,
                       log_requiere_fragil=lg.requiere_fragil)
    return valores


def valores_form_desde_post(form):
    """Lo que el vendedor escribió, para volver a mostrar el formulario con error."""
    valores = {c: _texto(form, c) for c in CAMPOS_PRODUCTO}
    valores["especificaciones"] = [(n.strip(), v.strip()) for n, v in
                                   zip(form.getlist("espec_nombre"), form.getlist("espec_valor"))
                                   if n.strip() or v.strip()]
    valores["con_logistica"] = form.get("con_logistica") == "1"
    valores.update({f"log_{c}": _texto(form, f"log_{c}") for c in CAMPOS_LOGISTICA})
    valores["log_requiere_fragil"] = form.get("log_requiere_fragil") == "1"
    return valores


# =============================================================================
# DFR 3.2 Consultar mis productos -> GET /vendedor/productos
# =============================================================================
@dataclass(frozen=True)
class FiltroMisProductosDTO:
    id_categoria: str = ""
    estado: str = ""
    q: str = ""
    cursor: str = ""

    @classmethod
    def from_form(cls, args):
        return cls(**{c: _texto(args, c) for c in ("id_categoria", "estado", "q", "cursor")})

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v}

    def filtros(self):
        return {k: v for k, v in self.to_dict().items() if k != "cursor"}


@dataclass(frozen=True)
class ProductoVendedorDTO:
    id_producto: int
    nombre: str
    precio: float
    estado: str
    marca: str
    id_categoria: Optional[int]
    categoria: str
    stock: int
    variantes: int

    @property
    def activo(self):
        return self.estado == "Activo"

    @classmethod
    def from_api(cls, d):
        return cls(
            id_producto=_entero(d, "id_producto"),
            nombre=_cadena(d, "nombre"),
            precio=_numero(d, "precio"),
            estado=_cadena(d, "estado"),
            marca=_cadena(d, "marca", obligatorio=False),
            id_categoria=_entero_opcional(d, "id_categoria"),
            categoria=_cadena(d, "categoria", obligatorio=False),
            stock=_entero_opcional(d, "stock") or 0,
            variantes=_entero_opcional(d, "variantes") or 0,
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PaginaMisProductosDTO:
    mensaje: str
    productos: list
    siguiente_cursor: Optional[int]

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("productos")
        if not isinstance(filas, list):
            raise ErrorRespuesta("productos")
        return cls(
            mensaje=_cadena(datos, "mensaje", obligatorio=False),
            productos=[ProductoVendedorDTO.from_api(f) for f in filas if isinstance(f, dict)],
            siguiente_cursor=_entero_opcional(datos, "siguiente_cursor"),
        )

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 3.4 Activar / desactivar -> PATCH /vendedor/productos/{id}/estado
# =============================================================================
@dataclass(frozen=True)
class EstadoProductoDTO:
    estado: str

    @classmethod
    def from_form(cls, form):
        estado = _texto(form, "estado")
        _obligatorios(estado)
        if estado not in ESTADOS_PRODUCTO:
            raise ErrorValidacion(MSG_ESTADO_NO_VALIDO)
        return cls(estado=estado)

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 3.5 Stock masivo -> POST /vendedor/stock-masivo (sp_ActualizarStockMasivo)
# =============================================================================
@dataclass(frozen=True)
class StockMasivoDTO:
    """La cantidad va como entero (con signo) para que el SP responda
    "La cantidad debe ser mayor a cero" con su texto del DFR."""
    id_categoria: int
    cantidad: int

    @classmethod
    def from_form(cls, form):
        categoria, cantidad = _texto(form, "id_categoria"), _texto(form, "cantidad")
        _obligatorios(categoria, cantidad)
        return cls(id_categoria=_entero_form(categoria, MSG_CATEGORIA_NO_EXISTE),
                   cantidad=_entero_form(cantidad, MSG_CANTIDAD_ENTERA))

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 3.6 Registrar variante -> POST /vendedor/productos/{id}/variantes
# =============================================================================
@dataclass(frozen=True)
class VarianteFormDTO:
    valores: tuple
    stock: int

    @classmethod
    def from_form(cls, form):
        elegidos = [v.strip() for v in form.getlist("valores") if isinstance(v, str) and v.strip()]
        stock = _texto(form, "stock")
        if not elegidos or not stock:
            raise ErrorValidacion(MSG_CAMPOS_OBLIGATORIOS)
        if len(elegidos) > VALORES_VARIANTE_MAX:
            raise ErrorValidacion(MSG_COMBINACION_LARGA)
        return cls(valores=tuple(_entero_form(v, MSG_VALOR_NO_EXISTE) for v in elegidos),
                   stock=_entero_form(stock, MSG_STOCK_ENTERO))

    def to_dict(self):
        return {"valores": list(self.valores), "stock": self.stock}


# =============================================================================
# DFR 8.1 / 8.2 / 7.4 Reportes por rango de fechas (sp_HistorialVentas)
# =============================================================================
@dataclass(frozen=True)
class FiltroFechasDTO:
    """Formato AAAA-MM-DD (input type=date). Que la fecha sea válida y el orden
    ("La fecha inicial no puede ser mayor a la fecha final") los validan la
    Lambda y el SP."""
    fecha_inicio: str
    fecha_fin: str

    @classmethod
    def from_form(cls, args):
        dto = cls(fecha_inicio=_texto(args, "fecha_inicio"), fecha_fin=_texto(args, "fecha_fin"))
        _obligatorios(dto.fecha_inicio, dto.fecha_fin)
        return dto

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class VentaProductoDTO:
    id_producto: Optional[int]
    producto: str
    unidades_vendidas: int
    total_vendido: float

    @classmethod
    def from_api(cls, d):
        return cls(
            id_producto=_entero_opcional(d, "id_producto"),
            producto=_cadena(d, "producto", obligatorio=False),
            unidades_vendidas=_entero_opcional(d, "unidades_vendidas") or 0,
            total_vendido=_numero(d, "total_vendido"),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ReporteVentasDTO:
    mensaje: str
    productos: list
    total_ventas: float
    vendedor: str = ""   # solo en 8.2

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("productos")
        if not isinstance(filas, list):
            raise ErrorRespuesta("productos")
        return cls(
            mensaje=_cadena(datos, "mensaje", obligatorio=False),
            productos=[VentaProductoDTO.from_api(f) for f in filas if isinstance(f, dict)],
            total_ventas=_numero(datos, "total_ventas"),
            vendedor=_cadena(datos, "vendedor", obligatorio=False),
        )

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 7.4 Historial de compras (Comprador) -> GET /historial/compras
# (sp_HistorialVentas 'Comprador'; las fechas usan FiltroFechasDTO)
# =============================================================================
@dataclass(frozen=True)
class CompraHistorialDTO:
    id_pedido: int
    fecha: str
    estado: str
    total: float
    suma_al_total: bool   # False si Cancelado o Devuelto (DFR 7.4)

    @classmethod
    def from_api(cls, d):
        suma = d.get("suma_al_total")
        if not isinstance(suma, bool):
            raise ErrorRespuesta("suma_al_total")
        return cls(id_pedido=_entero(d, "id_pedido"), fecha=_cadena(d, "fecha", obligatorio=False),
                   estado=_cadena(d, "estado"), total=_numero(d, "total"), suma_al_total=suma)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class HistorialComprasDTO:
    mensaje: str
    pedidos: list
    total_comprado: float

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("pedidos")
        if not isinstance(filas, list):
            raise ErrorRespuesta("pedidos")
        return cls(mensaje=_cadena(datos, "mensaje", obligatorio=False),
                   pedidos=[CompraHistorialDTO.from_api(f) for f in filas if isinstance(f, dict)],
                   total_comprado=_numero(datos, "total_comprado"))

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 1.3 a 1.6 Usuarios (Administrador) -> /admin/usuarios
# =============================================================================
def _nombre_apellido(nombre, apellido):
    if len(nombre) > NOMBRE_MAX or len(apellido) > NOMBRE_MAX:
        raise ErrorValidacion(MSG_NOMBRE_LARGO)


def _opcion(valor, opciones, mensaje):
    """Valor de un selector: debe ser una de las opciones (forma)."""
    if valor not in opciones:
        raise ErrorValidacion(mensaje)
    return valor


@dataclass(frozen=True)
class UsuarioNuevoDTO:
    """1.3. Formato de correo y fuerza de la contraseña: los valida la Lambda."""
    nombre: str
    apellido: str
    email: str
    password: str = field(repr=False)
    rol: str = ""

    @classmethod
    def from_form(cls, form):
        dto = cls(nombre=_texto(form, "nombre"), apellido=_texto(form, "apellido"),
                  email=_texto(form, "email"), password=_password(form, "password"),
                  rol=_texto(form, "rol"))
        _obligatorios(dto.nombre, dto.apellido, dto.email, dto.password, dto.rol)
        _nombre_apellido(dto.nombre, dto.apellido)
        if len(dto.email) > EMAIL_MAX:
            raise ErrorValidacion(MSG_CORREO_FORMATO)
        _opcion(dto.rol, ROLES, MSG_ROL_NO_VALIDO)
        return dto

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EditarUsuarioDTO:
    """1.5. Si el administrador se edita a sí mismo solo manda nombre y
    apellido (regla de Ian): rol y estado no se envían."""
    nombre: str
    apellido: str
    rol: Optional[str] = None
    estado: Optional[str] = None

    @classmethod
    def from_form(cls, form, es_propio=False):
        nombre, apellido = _texto(form, "nombre"), _texto(form, "apellido")
        if es_propio:
            _obligatorios(nombre, apellido)
            _nombre_apellido(nombre, apellido)
            return cls(nombre=nombre, apellido=apellido)
        rol, estado = _texto(form, "rol"), _texto(form, "estado")
        _obligatorios(nombre, apellido, rol, estado)
        _nombre_apellido(nombre, apellido)
        return cls(nombre=nombre, apellido=apellido,
                   rol=_opcion(rol, ROLES, MSG_ROL_NO_VALIDO),
                   estado=_opcion(estado, ESTADOS_USUARIO, MSG_ESTADO_NO_VALIDO))

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class FiltroUsuariosDTO:
    rol: str = ""
    estado: str = ""
    cursor: str = ""

    @classmethod
    def from_form(cls, args):
        return cls(**{c: _texto(args, c) for c in ("rol", "estado", "cursor")})

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v}

    def filtros(self):
        return {k: v for k, v in self.to_dict().items() if k != "cursor"}


@dataclass(frozen=True)
class UsuarioDTO:
    id_usuario: int
    nombre: str
    apellido: str
    email: str
    rol: str
    estado: str
    fecha_registro: str

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}".strip()

    @classmethod
    def from_api(cls, d):
        return cls(
            id_usuario=_entero(d, "id_usuario"),
            nombre=_cadena(d, "nombre"),
            apellido=_cadena(d, "apellido", obligatorio=False),
            email=_cadena(d, "email", obligatorio=False),
            rol=_cadena(d, "rol"),
            estado=_cadena(d, "estado"),
            fecha_registro=_cadena(d, "fecha_registro", obligatorio=False),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PaginaUsuariosDTO:
    mensaje: str
    usuarios: list
    siguiente_cursor: Optional[int]

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("usuarios")
        if not isinstance(filas, list):
            raise ErrorRespuesta("usuarios")
        return cls(mensaje=_cadena(datos, "mensaje", obligatorio=False),
                   usuarios=[UsuarioDTO.from_api(f) for f in filas if isinstance(f, dict)],
                   siguiente_cursor=_entero_opcional(datos, "siguiente_cursor"))

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 2.1 Crear / 2.3 Editar categoría -> POST /categorias, PUT /categorias/{id}
# =============================================================================
@dataclass(frozen=True)
class CategoriaFormDTO:
    """Descripción y padre son opcionales; en 2.3 (PUT) si van vacíos quedan
    en NULL, así que el formulario reenvía los valores actuales."""
    nombre: str
    descripcion: Optional[str] = None
    id_categoria_padre: Optional[int] = None

    @classmethod
    def from_form(cls, form):
        nombre, descripcion, padre = (_texto(form, c) for c in ("nombre", "descripcion", "id_categoria_padre"))
        _obligatorios(nombre)
        if len(nombre) > CATEGORIA_NOMBRE_MAX or len(descripcion) > CATEGORIA_DESCRIPCION_MAX:
            raise ErrorValidacion(MSG_CATEGORIA_LARGA)
        return cls(nombre=nombre, descripcion=descripcion or None,
                   id_categoria_padre=_entero_form(padre, MSG_CATEGORIA_PADRE_NO_EXISTE) if padre else None)

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 7.1 / A3 Pedidos, 7.2 Detalle, 7.3 Estado
# =============================================================================
@dataclass(frozen=True)
class FiltroPedidosDTO:
    estado: str = ""
    fecha: str = ""
    cursor: str = ""

    @classmethod
    def from_form(cls, args, estado_por_defecto=""):
        """estado_por_defecto se usa solo si el parámetro no viene en la URL
        (A3 abre con Pendiente; elegir "Todos" lo manda vacío)."""
        estado = _texto(args, "estado") if "estado" in args else estado_por_defecto
        return cls(estado=estado, fecha=_texto(args, "fecha"), cursor=_texto(args, "cursor"))

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v}

    def filtros(self):
        """Para los enlaces de paginación: el estado va siempre (aun vacío)."""
        return {"estado": self.estado, **({"fecha": self.fecha} if self.fecha else {})}


@dataclass(frozen=True)
class PedidoResumenDTO:
    id_pedido: int
    fecha: str
    total: float
    estado: str
    comprador: str = ""   # solo A3

    @classmethod
    def from_api(cls, d):
        return cls(id_pedido=_entero(d, "id_pedido"), fecha=_cadena(d, "fecha", obligatorio=False),
                   total=_numero(d, "total"), estado=_cadena(d, "estado"),
                   comprador=_cadena(d, "comprador", obligatorio=False))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PaginaPedidosDTO:
    mensaje: str
    pedidos: list
    siguiente_cursor: Optional[int]

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("pedidos")
        if not isinstance(filas, list):
            raise ErrorRespuesta("pedidos")
        return cls(mensaje=_cadena(datos, "mensaje", obligatorio=False),
                   pedidos=[PedidoResumenDTO.from_api(f) for f in filas if isinstance(f, dict)],
                   siguiente_cursor=_entero_opcional(datos, "siguiente_cursor"))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ProductoPedidoDTO:
    id_producto: int
    nombre: str
    sku: str
    atributos: dict
    cantidad: int
    precio_unitario: float   # histórico (DFR 7.2)
    subtotal: float
    url_imagen: Optional[str]

    @classmethod
    def from_api(cls, d):
        return cls(id_producto=_entero(d, "id_producto"), nombre=_cadena(d, "nombre"),
                   sku=_cadena(d, "sku", obligatorio=False), atributos=_mapa_texto(d.get("atributos")),
                   cantidad=_entero(d, "cantidad"), precio_unitario=_numero(d, "precio_unitario"),
                   subtotal=_numero(d, "subtotal"), url_imagen=url_segura(d.get("url_imagen")))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PedidoDetalleDTO:
    """7.2. Comprador: dirección completa y pago (últimos 4 y estado).
    Administrador: nombre del comprador, dirección reducida y sin pago."""
    id_pedido: int
    fecha: str
    estado: str
    total: float
    productos: list
    direccion: dict
    pago: Optional[dict]
    comprador: str

    @classmethod
    def from_api(cls, datos):
        p = datos.get("pedido")
        if not isinstance(p, dict):
            raise ErrorRespuesta("pedido")
        pago = p.get("pago")
        return cls(
            id_pedido=_entero(p, "id_pedido"),
            fecha=_cadena(p, "fecha", obligatorio=False),
            estado=_cadena(p, "estado"),
            total=_numero(p, "total"),
            productos=[ProductoPedidoDTO.from_api(f) for f in (p.get("productos") or []) if isinstance(f, dict)],
            direccion=_mapa_texto(p.get("direccion")),
            pago=_mapa_texto(pago) if isinstance(pago, dict) else None,
            comprador=_cadena(p, "comprador", obligatorio=False),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EstadoPedidoDTO:
    estado: str

    @classmethod
    def from_form(cls, form):
        estado = _texto(form, "estado")
        _obligatorios(estado)
        return cls(estado=_opcion(estado, ESTADOS_PEDIDO, MSG_ESTADO_NO_VALIDO))

    def to_dict(self):
        return asdict(self)


# =============================================================================
# Reseñas -> GET /productos/{id}/resenas, POST, PUT /resenas/{id}, DELETE
# =============================================================================
@dataclass(frozen=True)
class ResenaFormDTO:
    calificacion: int
    comentario: str

    @classmethod
    def from_form(cls, form):
        cal = _texto(form, "calificacion")
        com = _texto(form, "comentario")
        _obligatorios(cal, com)
        if not cal.isdigit() or not (1 <= int(cal) <= 5):
            raise ErrorValidacion(MSG_CALIFICACION_NO_VALIDA)
        if len(com) > COMENTARIO_MAX:
            raise ErrorValidacion(MSG_COMENTARIO_LARGO)
        return cls(calificacion=int(cal), comentario=com)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ResenaDTO:
    id_resena: int
    id_usuario: int
    nombre_usuario: str
    calificacion: int
    comentario: str
    fecha: str

    @classmethod
    def from_api(cls, d):
        return cls(
            id_resena=_entero(d, "id_resena"),
            id_usuario=_entero(d, "id_usuario"),
            nombre_usuario=_cadena(d, "nombre_usuario", obligatorio=False),
            calificacion=_entero(d, "calificacion"),
            comentario=_cadena(d, "comentario"),
            fecha=_cadena(d, "fecha", obligatorio=False),
        )

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PaginaResenasDTO:
    resenas: list
    siguiente_cursor: Optional[int]
    promedio_calificacion: Optional[float]
    mensaje: str

    @classmethod
    def from_api(cls, datos):
        filas = datos.get("resenas")
        if not isinstance(filas, list):
            raise ErrorRespuesta("resenas")
        cursor = datos.get("siguiente_cursor")
        promedio = datos.get("promedio_calificacion")
        return cls(
            resenas=[ResenaDTO.from_api(f) for f in filas if isinstance(f, dict)],
            siguiente_cursor=cursor if isinstance(cursor, int) else None,
            promedio_calificacion=float(promedio) if isinstance(promedio, (int, float)) and not isinstance(promedio, bool) else None,
            mensaje=_cadena(datos, "mensaje", obligatorio=False),
        )

    def to_dict(self):
        return asdict(self)


# =============================================================================
# DFR 8.2 Reporte de ventas por vendedor -> GET /admin/ventas
# =============================================================================
@dataclass(frozen=True)
class FiltroVentasAdminDTO:
    id_vendedor: int
    fecha_inicio: str
    fecha_fin: str

    @classmethod
    def from_form(cls, args):
        vendedor = _texto(args, "id_vendedor")
        fechas = FiltroFechasDTO(fecha_inicio=_texto(args, "fecha_inicio"), fecha_fin=_texto(args, "fecha_fin"))
        _obligatorios(vendedor, fechas.fecha_inicio, fechas.fecha_fin)
        return cls(id_vendedor=_entero_form(vendedor, MSG_VENDEDOR_NO_EXISTE),
                   fecha_inicio=fechas.fecha_inicio, fecha_fin=fechas.fecha_fin)

    def to_dict(self):
        return asdict(self)
