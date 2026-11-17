"""Errores debajo de cada campo (guía de diseño §6, formularios).

Las Lambdas y los DTOs devuelven un solo mensaje por formulario, con el texto
exacto del DFR. Aquí se decide a qué campo(s) pertenece ese mensaje, sin
cambiar el texto. Lo que no corresponde a un campo (carrito vacío, stock,
error interno...) se sigue mostrando arriba como mensaje general.

- En la misma petición (se vuelve a pintar el formulario): g.errores.
- Si la ruta redirige (agregar al carrito, cantidad, estado del pedido): los
  errores y lo que escribió el usuario pasan por la sesión del servidor
  (Flask-Session) y se leen una sola vez en la siguiente pantalla.
"""
import re
from datetime import date

from flask import flash, g, session

from constantes import (
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_CANTIDAD_ENTERA,
    MSG_CATEGORIA_LARGA,
    MSG_CATEGORIA_NO_EXISTE,
    MSG_CATEGORIA_PADRE_NO_EXISTE,
    MSG_COMBINACION_LARGA,
    MSG_CORREO_FORMATO,
    MSG_DIRECCION_LARGA,
    MSG_DIRECCION_NO_VALIDA,
    MSG_ESPECIFICACIONES,
    MSG_ESTADO_NO_VALIDO,
    MSG_FECHA_NO_VALIDA,
    MSG_LOGISTICA,
    MSG_MARCA_NO_EXISTE,
    MSG_NOMBRE_LARGO,
    MSG_PRODUCTO_LARGO,
    MSG_ROL_NO_VALIDO,
    MSG_STOCK_ENTERO,
    MSG_VALOR_NO_EXISTE,
    MSG_VARIANTE_NO_EXISTE,
    MSG_VENDEDOR_NO_EXISTE,
)

# Formularios: (todos los campos y grupos, obligatorios). Los grupos
# (especificaciones, logistica, valores) muestran el error bajo su título.
FORMULARIOS = {
    "login": (("email", "password"), ("email", "password")),
    "registro": (("nombre", "apellido", "email", "password", "confirmar_password"),
                 ("nombre", "apellido", "email", "password", "confirmar_password")),
    "usuario_nuevo": (("nombre", "apellido", "email", "password", "rol"),
                      ("nombre", "apellido", "email", "password", "rol")),
    "usuario_editar": (("nombre", "apellido", "rol", "estado"), ("nombre", "apellido", "rol", "estado")),
    "categoria": (("nombre", "descripcion", "id_categoria_padre"), ("nombre",)),
    "direccion": (("calle", "numero", "colonia", "ciudad", "estado", "codigo_postal"),
                  ("calle", "numero", "colonia", "ciudad", "estado", "codigo_postal")),
    "compra": (("id_direccion", "numero_tarjeta", "cvv"), ("id_direccion", "numero_tarjeta", "cvv")),
    "producto": (("nombre", "descripcion", "precio", "stock", "id_marca", "id_categoria", "url_imagen",
                  "especificaciones", "logistica", "log_tipo_empaque"),
                 ("nombre", "descripcion", "precio", "stock", "id_marca", "id_categoria", "url_imagen")),
    "variante": (("valores", "stock"), ("stock",)),
    "stock_masivo": (("id_categoria", "cantidad"), ("id_categoria", "cantidad")),
    "agregar": (("id_variante", "cantidad"), ("cantidad",)),
    "cantidad_carrito": (("cantidad",), ("cantidad",)),
    "estado_pedido": (("estado",), ("estado",)),
    "reporte": (("id_vendedor", "fecha_inicio", "fecha_fin"), ("id_vendedor", "fecha_inicio", "fecha_fin")),
    "filtro_pedidos": (("estado", "fecha"), ()),
    "filtro_productos": (("id_categoria", "estado"), ()),
    "filtro_usuarios": (("rol", "estado"), ()),
    "filtro_catalogo": (("precio_min", "precio_max", "id_categoria"), ()),
}

# Campos que son radio (si no se elige ninguno, el navegador no los envía).
_RADIOS = {"id_direccion"}

# Mensaje exacto -> campos candidatos (se quedan los que existen en el formulario).
_REGLAS = {
    MSG_CORREO_FORMATO: ("email",),
    "El correo electrónico ya está registrado": ("email",),
    "Usuario no encontrado": ("email",),
    "Contraseña incorrecta": ("password",),
    "La contraseña debe tener mínimo 8 caracteres, una mayúscula, un número y un carácter especial": ("password",),
    "Las contraseñas no coinciden": ("confirmar_password",),
    MSG_ROL_NO_VALIDO: ("rol",),
    MSG_ESTADO_NO_VALIDO: ("estado",),
    "La categoría ya existe": ("nombre",),
    MSG_CATEGORIA_PADRE_NO_EXISTE: ("id_categoria_padre",),
    "Una categoría no puede ser su propia categoría padre": ("id_categoria_padre",),
    "Una categoría no puede tener como padre a una de sus subcategorías": ("id_categoria_padre",),
    "El código postal debe tener 5 dígitos": ("codigo_postal",),
    MSG_DIRECCION_NO_VALIDA: ("id_direccion",),
    "El precio debe ser mayor a cero": ("precio",),
    "El precio mínimo no puede ser mayor al máximo": ("precio_min",),
    MSG_STOCK_ENTERO: ("stock",),
    "El stock no es válido": ("stock",),
    "El stock no puede ser negativo": ("stock",),
    "La URL de imagen no es válida": ("url_imagen",),
    MSG_MARCA_NO_EXISTE: ("id_marca",),
    MSG_CATEGORIA_NO_EXISTE: ("id_categoria",),
    MSG_ESPECIFICACIONES: ("especificaciones",),
    MSG_LOGISTICA: ("logistica",),
    MSG_CANTIDAD_ENTERA: ("cantidad",),
    "La cantidad debe ser mayor a cero": ("cantidad",),
    "La cantidad no es válida": ("cantidad",),
    "La cantidad solicitada supera el stock disponible": ("cantidad",),
    MSG_VARIANTE_NO_EXISTE: ("id_variante",),
    "No puedes elegir dos valores del mismo atributo": ("valores",),
    MSG_VALOR_NO_EXISTE: ("valores",),
    MSG_COMBINACION_LARGA: ("valores",),
    "La variante ya existe para este producto": ("valores",),
    "No se encontraron productos para actualizar": ("id_categoria",),
    "La fecha inicial no puede ser mayor a la fecha final": ("fecha_inicio",),
    MSG_VENDEDOR_NO_EXISTE: ("id_vendedor",),
}

# validar_texto de las Lambdas: "{etiqueta} no puede ..." (la más larga primero).
_ETIQUETAS = (
    ("El nombre de la especificación", "especificaciones"),
    ("La especificación", "especificaciones"),
    ("El tipo de empaque", "log_tipo_empaque"),
    ("La descripción", "descripcion"),
    ("El apellido", "apellido"),
    ("El nombre", "nombre"),
    ("La calle", "calle"),
    ("El número", "numero"),
    ("La colonia", "colonia"),
    ("La ciudad", "ciudad"),
    ("El estado", "estado"),
)
_FINALES = (" no puede tener espacios en blanco seguidos",
            " no puede tener más de dos caracteres especiales seguidos",
            " no puede contener solo números")

# Mensajes de longitud: campo -> máximo
_LONGITUDES = {
    MSG_NOMBRE_LARGO: {"nombre": 80, "apellido": 80},
    MSG_CATEGORIA_LARGA: {"nombre": 100, "descripcion": 255},
    MSG_PRODUCTO_LARGO: {"nombre": 200, "descripcion": 1000, "url_imagen": 500},
    MSG_DIRECCION_LARGA: {"calle": 150, "numero": 20, "colonia": 100, "ciudad": 100, "estado": 100},
}

_PRECIO = re.compile(r"^\d+(\.\d{1,2})?$")


def _valor(datos, campo):
    return (datos.get(campo) or "").strip()


def _fecha_valida(texto):
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto)) and bool(date.fromisoformat(texto))
    except ValueError:
        return False


def _precio_valido(texto):
    return bool(_PRECIO.match(texto)) and float(texto) < 100_000_000


def _campos_para(mensaje, todos, obligatorios, datos):
    if mensaje == MSG_CAMPOS_OBLIGATORIOS:
        vacios = [c for c in obligatorios
                  if (c in datos or c in _RADIOS) and not _valor(datos, c)]
        if "valores" in todos and hasattr(datos, "getlist") \
                and not any(v.strip() for v in datos.getlist("valores")):
            vacios.append("valores")
        return vacios
    if mensaje in _LONGITUDES:
        limites = {c: m for c, m in _LONGITUDES[mensaje].items() if c in todos}
        largos = [c for c, m in limites.items() if len(_valor(datos, c)) > m]
        return largos or list(limites)
    if mensaje == "Datos de pago no válidos":
        tarjeta = _valor(datos, "numero_tarjeta")
        digitos = re.sub(r"[ -]", "", tarjeta)
        malos = []
        if not (re.fullmatch(r"[0-9 -]+", tarjeta or "x") and len(digitos) == 16 and digitos.isdigit()):
            malos.append("numero_tarjeta")
        if not re.fullmatch(r"[0-9]{3}", _valor(datos, "cvv")):
            malos.append("cvv")
        return malos or ["numero_tarjeta", "cvv"]
    if mensaje == MSG_FECHA_NO_VALIDA:
        presentes = [c for c in ("fecha", "fecha_inicio", "fecha_fin") if c in todos and _valor(datos, c)]
        return [c for c in presentes if not _fecha_valida(_valor(datos, c))] or presentes
    if mensaje == "El precio no es válido":
        presentes = [c for c in ("precio", "precio_min", "precio_max") if c in todos and _valor(datos, c)]
        return [c for c in presentes if not _precio_valido(_valor(datos, c))] or presentes
    for etiqueta, campo in _ETIQUETAS:
        if mensaje.startswith(etiqueta) and mensaje.endswith(_FINALES):
            return [campo]
    return list(_REGLAS.get(mensaje, ()))


def errores_de(formulario, mensaje, datos):
    """{campo: mensaje} con los campos del formulario a los que pertenece el
    mensaje; vacío si no corresponde a ningún campo."""
    todos, obligatorios = FORMULARIOS[formulario]
    campos = [c for c in _campos_para(mensaje, todos, obligatorios, datos) if c in todos]
    return {c: mensaje for c in dict.fromkeys(campos)}


def asignar(mensaje, formulario, datos, sufijo=None, redirige=False):
    """Guarda los errores por campo. Devuelve False si el mensaje no es de un
    campo (la ruta decide cómo mostrarlo)."""
    errores = errores_de(formulario, mensaje, datos)
    if not errores:
        return False
    if sufijo is not None:
        errores = {f"{c}-{sufijo}": m for c, m in errores.items()}
    if redirige:
        session["errores_campo"] = errores
        # Lo que escribió el usuario, para no perderlo (nunca tarjeta, CVV ni contraseñas).
        previos = {c: _valor(datos, c) for c in FORMULARIOS[formulario][0] if c in datos}
        session["previos_campo"] = {(f"{c}-{sufijo}" if sufijo is not None else c): v for c, v in previos.items()}
    else:
        g.errores = errores
    return True


def avisar(exc_o_mensaje, formulario, datos, sufijo=None, redirige=False):
    """Error debajo del campo; si no corresponde a ninguno, mensaje general arriba."""
    mensaje = getattr(exc_o_mensaje, "mensaje", None) or str(exc_o_mensaje)
    if not asignar(mensaje, formulario, datos, sufijo, redirige):
        flash(mensaje, "error")


def para_plantilla():
    """Errores y valores previos de esta petición (o de la redirección anterior)."""
    if "errores" not in g:
        g.errores = session.pop("errores_campo", None) or {}
        g.previos = session.pop("previos_campo", None) or {}
    return {"errores": g.errores, "previos": g.get("previos", {})}
