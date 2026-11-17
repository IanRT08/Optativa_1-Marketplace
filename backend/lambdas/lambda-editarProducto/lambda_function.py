"""
lambda-editarProducto
DFR 3.3 Editar producto (Vendedor): actualiza un producto propio y Activo en
RDS y en el catálogo de DynamoDB, con las mismas validaciones de 3.1.
Reglas aprobadas por Ian:
- Solo productos Activos (para editar uno Inactivo, primero se activa con 3.4).
- stock cambia solo la variante estándar P{id}-STD; las demás, en 3.6.
- PUT completo: si especificaciones o logistica_envio no vienen, se quitan.
- Orden: cambios en RDS sin confirmar -> UpdateItem en DynamoDB -> commit.
  Si DynamoDB falla, rollback: nada cambia en ningún lado.
Descripcion: solo se actualiza Descripcion.Resumen (se conservan las demás
claves que traiga el script de carga). NombreBusqueda (minúsculas, sin
acentos) se actualiza junto con Nombre, para la búsqueda de 4.1.
Ruta: PUT /vendedor/productos/{id} (token con rol Vendedor). Función nueva; la
Lambda vieja "modificar" no se toca.
Tablas: producto, variante_producto, variante_valor, valor_atributo, atributo,
marca, categoria. No usa stored procedure.
"""
import os
import re
import unicodedata
from decimal import Decimal
from urllib.parse import urlsplit

import boto3
import pymysql

from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
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
    path_param,
    validar_texto,
    validar_token,
)

MSG_PRODUCTO_ACTUALIZADO = "Producto actualizado correctamente"  # DFR 3.3
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_PRODUCTO_INACTIVO = "El producto está inactivo y no se puede editar"  # aprobado por Ian
# Mismas validaciones que 3.1 (DFR 3.3)
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

NOMBRE_MAX = 200
DESCRIPCION_MAX = 1000
URL_MAX = 500
PRECIO_MAX = Decimal("100000000")
STOCK_MIN = 0  # DFR 3.1: "entero mayor o igual a cero"
STOCK_MAX = 2147483647
ERRNO_FK = 1452
ESPEC_MAX = 20
ESPEC_NOMBRE_MAX = 50
ESPEC_VALOR_MAX = 200
LOGISTICA_MAX = Decimal("1000")
EMPAQUE_MAX = 100
MEDIDAS = (("alto", "Alto"), ("ancho", "Ancho"), ("profundidad", "Profundidad"))
CAMPOS_LOGISTICA = ("alto", "ancho", "profundidad", "peso_kg", "requiere_fragil", "tipo_empaque")

_RE_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_MARCA = "SELECT nombre FROM marca WHERE id_marca = %s"
SQL_CATEGORIA = "SELECT nombre FROM categoria WHERE id_categoria = %s"
SQL_PRODUCTO = "SELECT id_vendedor, estado FROM producto WHERE id_producto = %s FOR UPDATE"
SQL_ACTUALIZAR = """
    UPDATE producto
    SET nombre = %s, precio = %s, id_marca = %s, id_categoria = %s
    WHERE id_producto = %s
"""
SQL_VARIANTE_STD = "SELECT id_variante FROM variante_producto WHERE sku = %s FOR UPDATE"
SQL_STOCK_STD = "UPDATE variante_producto SET stock = %s WHERE id_variante = %s"
# Todas las variantes del producto con sus atributos (para Variantes en DynamoDB)
SQL_VARIANTES = """
    SELECT v.id_variante, v.sku, v.stock, a.nombre AS atributo, va.valor
    FROM variante_producto v
    LEFT JOIN variante_valor vv ON vv.id_variante = v.id_variante
    LEFT JOIN valor_atributo va ON va.id_valor = vv.id_valor
    LEFT JOIN atributo a ON a.id_atributo = va.id_atributo
    WHERE v.id_producto = %s
    ORDER BY v.id_variante, a.nombre
"""

tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _texto_busqueda(texto):
    """'Niño Azúl' -> 'nino azul' (igual que en 3.1 y 4.1)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


# --- Validaciones (las mismas de 3.1) ---------------------------------------
def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _a_decimal(valor):
    """Decimal desde número o texto con solo dígitos; letras, $, comas, exponentes, NaN -> None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        numero = Decimal(valor)
    elif isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, str) and _RE_DECIMAL.fullmatch(valor.strip()):
        numero = Decimal(valor.strip())
    else:
        return None
    return numero if numero.is_finite() else None


def _max_dos_decimales(numero):
    return numero.normalize().as_tuple().exponent >= -2


def _precio(valor):
    numero = _a_decimal(valor)
    if numero is None:
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    if numero <= 0:
        raise ErrorNegocio(400, MSG_PRECIO_CERO)
    if not _max_dos_decimales(numero) or numero >= PRECIO_MAX:
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    return numero.quantize(Decimal("0.01"))


def _stock(valor):
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
        validar_texto(texto, "La especificación", permitir_solo_numeros=True)
        resultado[nombre] = texto
    return resultado


def _logistica(valor):
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
    if id_registro is None:
        raise ErrorNegocio(400, mensaje)
    cursor.execute(sql, (id_registro,))
    fila = cursor.fetchone()
    if fila is None:
        raise ErrorNegocio(400, mensaje)
    return fila["nombre"]


# --- DynamoDB ---------------------------------------------------------------
def _variantes_desde_rds(filas):
    """Agrupa las filas de SQL_VARIANTES en la lista Variantes del estándar."""
    variantes = {}
    for fila in filas:
        variante = variantes.setdefault(
            fila["id_variante"],
            {"IdVariante": fila["id_variante"], "SKU": fila["sku"], "Stock": fila["stock"], "Atributos": {}},
        )
        if fila["atributo"] is not None:
            variante["Atributos"][fila["atributo"]] = fila["valor"]
    return list(variantes.values())


def _actualizar_catalogo(id_producto, valores, especificaciones, logistica):
    """UpdateItem del estándar de Ian. Nunca crea el ítem si no existe."""
    nombres = {"#Descripcion": "Descripcion", "#Resumen": "Resumen"}
    expresiones = ["#Descripcion.#Resumen = :Resumen"]
    datos = {":Resumen": valores.pop("Resumen")}
    for atributo, valor in valores.items():
        nombres[f"#{atributo}"] = atributo
        datos[f":{atributo}"] = valor
        expresiones.append(f"#{atributo} = :{atributo}")

    quitar = []
    for atributo, valor in (("Especificaciones", especificaciones), ("LogisticaEnvio", logistica)):
        nombres[f"#{atributo}"] = atributo
        if valor:
            datos[f":{atributo}"] = valor
            expresiones.append(f"#{atributo} = :{atributo}")
        else:
            quitar.append(f"#{atributo}")  # PUT completo: si no viene, se quita

    expresion = "SET " + ", ".join(expresiones)
    if quitar:
        expresion += " REMOVE " + ", ".join(quitar)

    tabla_productos.update_item(
        Key={"productoID": str(id_producto)},
        UpdateExpression=expresion,
        ConditionExpression="attribute_exists(productoID)",
        ExpressionAttributeNames=nombres,
        ExpressionAttributeValues=datos,
    )


# --- Handler ----------------------------------------------------------------
@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])

    id_producto = entero_positivo(path_param(event, "id"))
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    datos = leer_body(event)
    nombre = campo_texto(datos, "nombre")
    descripcion = campo_texto(datos, "descripcion")
    url_imagen = campo_texto(datos, "url_imagen")
    numericos = (datos.get(c) for c in ("precio", "stock", "id_marca", "id_categoria"))
    if not all((nombre, descripcion, url_imagen)) or any(_vacio(v) for v in numericos):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    precio = _precio(datos["precio"])
    stock = _stock(datos["stock"])
    if len(nombre) > NOMBRE_MAX or len(descripcion) > DESCRIPCION_MAX or len(url_imagen) > URL_MAX:
        raise ErrorNegocio(400, MSG_LONGITUD)
    if not _url_valida(url_imagen):
        raise ErrorNegocio(400, MSG_URL_INVALIDA)
    validar_texto(nombre, "El nombre")
    validar_texto(descripcion, "La descripción")
    especificaciones = _especificaciones(datos.get("especificaciones"))
    logistica = _logistica(datos.get("logistica_envio"))

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        id_marca = entero_positivo(datos["id_marca"])
        marca = _buscar_nombre(cursor, SQL_MARCA, id_marca, MSG_MARCA_NO_EXISTE)
        id_categoria = entero_positivo(datos["id_categoria"])
        categoria = _buscar_nombre(cursor, SQL_CATEGORIA, id_categoria, MSG_CATEGORIA_NO_EXISTE)

    # --- RDS sin confirmar (si algo falla, manejar_errores hace rollback) ---
    conexion.begin()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["id_vendedor"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)  # DFR 3.3
        if producto["estado"] != "Activo":
            raise ErrorNegocio(409, MSG_PRODUCTO_INACTIVO)

        try:
            cursor.execute(SQL_ACTUALIZAR, (nombre, precio, id_marca, id_categoria, id_producto))
        except pymysql.err.IntegrityError as e:
            if e.args and e.args[0] == ERRNO_FK:  # categoría borrada en ese instante
                raise ErrorNegocio(400, MSG_CATEGORIA_NO_EXISTE)
            raise

        cursor.execute(SQL_VARIANTE_STD, (f"P{id_producto}-STD",))
        estandar = cursor.fetchone()
        if estandar is None:
            raise RuntimeError(f"El producto {id_producto} no tiene variante estándar")
        cursor.execute(SQL_STOCK_STD, (stock, estandar["id_variante"]))

        cursor.execute(SQL_VARIANTES, (id_producto,))
        variantes = _variantes_desde_rds(cursor.fetchall())

    # --- DynamoDB antes del commit ---
    valores = {
        "Nombre": nombre,
        "NombreBusqueda": _texto_busqueda(nombre),  # para 4.1
        "Resumen": descripcion,
        "Precio": precio,
        "Marca": marca,
        "Categoria": categoria,
        "CategoriaID": id_categoria,
        "URLImagen": url_imagen,
        "Variantes": variantes,
        "Stock": sum(v["Stock"] for v in variantes),  # DFR 3.6: suma de variantes
    }
    try:
        _actualizar_catalogo(id_producto, valores, especificaciones, logistica)
    except Exception as e:
        print(f"DynamoDB falló al editar el producto {id_producto}; se hace rollback en RDS: {e!r}")
        conexion.rollback()
        raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    conexion.commit()
    return ok(MSG_PRODUCTO_ACTUALIZADO, id_producto=id_producto)
