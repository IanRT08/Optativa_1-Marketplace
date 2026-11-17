"""
lambda-crearProducto
DFR 3.1 Registrar producto (Vendedor): crea el producto (Activo) ligado al
vendedor de la sesión y su variante estándar con el stock inicial; después
lo publica en el catálogo de DynamoDB.
- RDS: transacción en Python (producto + variante_producto), commit.
- DynamoDB: PutItem con el estándar de Ian, después del commit. Si falla, el
  producto queda Inactivo en RDS, se registra el error y se responde 500.
- SKU de la variante estándar: P{id_producto}-STD.
- NombreBusqueda: nombre en minúsculas y sin acentos para la búsqueda de 4.1
  (contains de DynamoDB distingue mayúsculas). Aprobado por Ian.
Ruta: POST /vendedor/productos (token con rol Vendedor). Función nueva; la
Lambda vieja "crear" no se toca.
Tablas: producto, variante_producto, marca, categoria. No usa stored procedure.
"""
import os
import re
import unicodedata
from decimal import Decimal
from urllib.parse import urlsplit

import boto3
import pymysql

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_ERROR_INTERNO,
    ROL_VENDEDOR,
    ErrorNegocio,
    campo_texto,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_texto,
    validar_token,
)

MSG_PRODUCTO_REGISTRADO = "Producto registrado correctamente"  # DFR 3.1
MSG_PRECIO_CERO = "El precio debe ser mayor a cero"  # DFR 3.1
MSG_STOCK_NEGATIVO = "El stock no puede ser negativo"  # DFR 3.1
MSG_PRECIO_INVALIDO = "El precio no es válido"  # aprobado por Ian
MSG_STOCK_ENTERO = "El stock debe ser un número entero"  # aprobado por Ian
MSG_STOCK_INVALIDO = "El stock no es válido"  # aprobado por Ian
MSG_LONGITUD = (  # aprobado por Ian
    "El nombre no puede superar 200 caracteres, la descripción 1000 y la URL de imagen 500"
)
MSG_URL_INVALIDA = "La URL de imagen no es válida"  # aprobado por Ian
MSG_MARCA_NO_EXISTE = "La marca no existe"  # aprobado por Ian
MSG_CATEGORIA_NO_EXISTE = "La categoría no existe"  # aprobado por Ian
MSG_ESPECIFICACIONES = (  # aprobado por Ian
    "Se admiten hasta 20 especificaciones, con nombre de hasta 50 caracteres "
    "y valor de texto de hasta 200, sin nombres repetidos"
)
MSG_LOGISTICA = (  # aprobado por Ian
    "Las medidas y el peso deben ser mayores a cero y hasta 1000, con máximo 2 decimales; "
    "el tipo de empaque admite hasta 100 caracteres"
)

NOMBRE_MAX = 200  # producto.nombre VARCHAR(200)
DESCRIPCION_MAX = 1000  # solo DynamoDB (aprobado por Ian)
URL_MAX = 500  # solo DynamoDB (aprobado por Ian)
PRECIO_MAX = Decimal("100000000")  # DECIMAL(10,2): hasta 99,999,999.99
STOCK_MIN = 0  # DFR 3.1: "entero mayor o igual a cero"
STOCK_MAX = 2147483647  # variante_producto.stock INT
ERRNO_FK = 1452  # la categoría se borró entre la validación y el INSERT

# Campos opcionales del estándar de DynamoDB (aprobados por Ian)
ESPEC_MAX = 20  # cantidad de especificaciones
ESPEC_NOMBRE_MAX = 50
ESPEC_VALOR_MAX = 200
LOGISTICA_MAX = Decimal("1000")  # cm y kg
EMPAQUE_MAX = 100
MEDIDAS = (("alto", "Alto"), ("ancho", "Ancho"), ("profundidad", "Profundidad"))
CAMPOS_LOGISTICA = ("alto", "ancho", "profundidad", "peso_kg", "requiere_fragil", "tipo_empaque")

# Solo dígitos ASCII; el signo "-" se acepta para responder el mensaje del DFR.
_RE_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_MARCA = "SELECT nombre FROM marca WHERE id_marca = %s"
SQL_CATEGORIA = "SELECT nombre FROM categoria WHERE id_categoria = %s"
SQL_PRODUCTO = """
    INSERT INTO producto (id_vendedor, id_categoria, id_marca, nombre, precio, estado)
    VALUES (%s, %s, %s, %s, %s, 'Activo')
"""
SQL_VARIANTE = "INSERT INTO variante_producto (id_producto, sku, stock) VALUES (%s, %s, %s)"
SQL_INACTIVAR = "UPDATE producto SET estado = 'Inactivo' WHERE id_producto = %s"

# Cliente de DynamoDB creado fuera del handler (se reutiliza entre invocaciones)
tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _texto_busqueda(texto):
    """'Niño Azúl' -> 'nino azul' (igual que en 4.1, que normaliza la palabra clave)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _a_decimal(valor):
    """
    Decimal desde un número del JSON o un texto con solo dígitos (y "-" o "."
    opcionales). Rechaza letras, "$", comas, exponentes, NaN y booleanos -> None.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        numero = Decimal(valor)
    elif isinstance(valor, Decimal):  # número con punto en el JSON
        numero = valor
    elif isinstance(valor, str) and _RE_DECIMAL.fullmatch(valor.strip()):
        numero = Decimal(valor.strip())
    else:
        return None
    return numero if numero.is_finite() else None


def _max_dos_decimales(numero):
    return numero.normalize().as_tuple().exponent >= -2


def _precio(valor):
    """Decimal con 2 decimales, > 0 y < 100,000,000."""
    numero = _a_decimal(valor)
    if numero is None:
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    if numero <= 0:
        raise ErrorNegocio(400, MSG_PRECIO_CERO)
    if not _max_dos_decimales(numero) or numero >= PRECIO_MAX:
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    return numero.quantize(Decimal("0.01"))


def _stock(valor):
    """Entero de 0 a 2,147,483,647. Rechaza decimales, letras y signos."""
    if isinstance(valor, bool):
        raise ErrorNegocio(400, MSG_STOCK_ENTERO)
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
    else:
        raise ErrorNegocio(400, MSG_STOCK_ENTERO)

    if numero < STOCK_MIN:
        raise ErrorNegocio(400, MSG_STOCK_NEGATIVO)
    if numero > STOCK_MAX:
        raise ErrorNegocio(400, MSG_STOCK_INVALIDO)
    return numero


def _url_valida(url):
    if any(c.isspace() for c in url) or not url.isprintable():
        return False
    partes = urlsplit(url)
    return partes.scheme in ("http", "https") and bool(partes.netloc)


def _especificaciones(valor):
    """
    Opcional. {"Material": "Aluminio", ...} -> mapa Especificaciones de DynamoDB.
    Ausente, null o {} -> None (no se guarda el atributo).
    """
    if valor is None or valor == {}:
        return None
    if not isinstance(valor, dict) or len(valor) > ESPEC_MAX:
        raise ErrorNegocio(400, MSG_ESPECIFICACIONES)

    resultado = {}
    for clave, texto in valor.items():
        if not isinstance(texto, str):
            raise ErrorNegocio(400, MSG_ESPECIFICACIONES)
        nombre, texto = clave.strip(), texto.strip()
        if not nombre or not texto:
            raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
        if len(nombre) > ESPEC_NOMBRE_MAX or len(texto) > ESPEC_VALOR_MAX or nombre in resultado:
            raise ErrorNegocio(400, MSG_ESPECIFICACIONES)
        validar_texto(nombre, "El nombre de la especificación")
        # El valor puede ser solo números (p. ej. "Año": "2026")
        validar_texto(texto, "La especificación", permitir_solo_numeros=True)
        resultado[nombre] = texto
    return resultado


def _logistica(valor):
    """
    Opcional. Si se manda, los 6 campos son obligatorios. Devuelve el mapa
    LogisticaEnvio del estándar de DynamoDB. Ausente, null o {} -> None.
    """
    if valor is None or valor == {}:
        return None
    if not isinstance(valor, dict):
        raise ErrorNegocio(400, MSG_LOGISTICA)
    if any(_vacio(valor.get(campo)) for campo in CAMPOS_LOGISTICA):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    numeros = {}
    for campo in ("alto", "ancho", "profundidad", "peso_kg"):
        numero = _a_decimal(valor[campo])
        if numero is None or numero <= 0 or numero > LOGISTICA_MAX or not _max_dos_decimales(numero):
            raise ErrorNegocio(400, MSG_LOGISTICA)
        numeros[campo] = numero

    requiere_fragil = valor["requiere_fragil"]
    empaque = valor["tipo_empaque"]
    if not isinstance(requiere_fragil, bool) or not isinstance(empaque, str):
        raise ErrorNegocio(400, MSG_LOGISTICA)
    empaque = empaque.strip()
    if not empaque:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if len(empaque) > EMPAQUE_MAX:
        raise ErrorNegocio(400, MSG_LOGISTICA)
    validar_texto(empaque, "El tipo de empaque")

    return {
        "DimensionesCm": {clave: numeros[campo] for campo, clave in MEDIDAS},
        "PesoKg": numeros["peso_kg"],
        "RequiereFragil": requiere_fragil,
        "TipoEmpaque": empaque,
    }


def _buscar_nombre(cursor, sql, id_registro, mensaje):
    """Nombre de la marca o categoría; si el id no es válido o no existe -> 400."""
    if id_registro is None:
        raise ErrorNegocio(400, mensaje)
    cursor.execute(sql, (id_registro,))
    fila = cursor.fetchone()
    if fila is None:
        raise ErrorNegocio(400, mensaje)
    return fila["nombre"]


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
    datos = leer_body(event)

    nombre = campo_texto(datos, "nombre")
    descripcion = campo_texto(datos, "descripcion")
    url_imagen = campo_texto(datos, "url_imagen")
    obligatorios = (nombre, descripcion, url_imagen)
    numericos = (datos.get(c) for c in ("precio", "stock", "id_marca", "id_categoria"))
    if not all(obligatorios) or any(_vacio(v) for v in numericos):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    precio = _precio(datos["precio"])
    stock = _stock(datos["stock"])

    if len(nombre) > NOMBRE_MAX or len(descripcion) > DESCRIPCION_MAX or len(url_imagen) > URL_MAX:
        raise ErrorNegocio(400, MSG_LONGITUD)
    if not _url_valida(url_imagen):
        raise ErrorNegocio(400, MSG_URL_INVALIDA)

    validar_texto(nombre, "El nombre")
    validar_texto(descripcion, "La descripción")

    # Opcionales del estándar de DynamoDB
    especificaciones = _especificaciones(datos.get("especificaciones"))
    logistica = _logistica(datos.get("logistica_envio"))

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        id_marca = entero_positivo(datos["id_marca"])
        marca = _buscar_nombre(cursor, SQL_MARCA, id_marca, MSG_MARCA_NO_EXISTE)
        id_categoria = entero_positivo(datos["id_categoria"])
        categoria = _buscar_nombre(cursor, SQL_CATEGORIA, id_categoria, MSG_CATEGORIA_NO_EXISTE)

    # --- RDS: producto + variante estándar en una sola transacción ---
    id_vendedor = sesion["id_usuario"]
    try:
        conexion.begin()
        with conexion.cursor() as cursor:
            cursor.execute(SQL_PRODUCTO, (id_vendedor, id_categoria, id_marca, nombre, precio))
            id_producto = cursor.lastrowid
            sku = f"P{id_producto}-STD"
            cursor.execute(SQL_VARIANTE, (id_producto, sku, stock))
            id_variante = cursor.lastrowid
        conexion.commit()
    except pymysql.err.IntegrityError as e:
        conexion.rollback()
        if e.args and e.args[0] == ERRNO_FK:
            raise ErrorNegocio(400, MSG_CATEGORIA_NO_EXISTE)
        raise

    # --- DynamoDB: catálogo de búsqueda (estándar de Ian) ---
    item = {
        "productoID": str(id_producto),
        "Nombre": nombre,
        "NombreBusqueda": _texto_busqueda(nombre),  # para 4.1
        "Descripcion": {"Resumen": descripcion},
        "Precio": precio,
        "Marca": marca,
        "Categoria": categoria,
        "CategoriaID": id_categoria,
        "URLImagen": url_imagen,
        "Stock": stock,  # referencia inicial; el stock exacto vive en RDS
        "VendedorID": id_vendedor,
        "Estado": "Activo",
        "Variantes": [
            {"IdVariante": id_variante, "SKU": sku, "Stock": stock, "Atributos": {}}
        ],
    }
    if especificaciones:
        item["Especificaciones"] = especificaciones
    if logistica:
        item["LogisticaEnvio"] = logistica

    try:
        tabla_productos.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(productoID)",
        )
    except Exception as e:
        print(f"DynamoDB falló para el producto {id_producto}; queda Inactivo en RDS: {e!r}")
        with conexion.cursor() as cursor:
            cursor.execute(SQL_INACTIVAR, (id_producto,))
        raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    return ok(MSG_PRODUCTO_REGISTRADO, status=201, id_producto=id_producto, sku=sku)
