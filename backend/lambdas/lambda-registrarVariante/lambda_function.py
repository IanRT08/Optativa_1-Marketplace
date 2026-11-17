"""
lambda-registrarVariante
DFR 3.6 Registrar variantes de un producto (Vendedor): crea una variante con
una combinación de valores del catálogo y su propio stock.
Reglas aprobadas por Ian:
- Solo en productos propios (otro vendedor -> "Acceso restringido") y Activos.
- La variante estándar P{id}-STD no se toca; el stock del producto es la suma
  de todas sus variantes, incluida la estándar.
- SKU: P{id}-{VALORES} ordenados por atributo, en mayúsculas, sin espacios ni
  acentos (p. ej. P123-M-ROJO), máximo 60 caracteres.
- Orden: RDS sin confirmar -> UpdateItem en DynamoDB -> commit; si DynamoDB
  falla, rollback.
Ruta: POST /vendedor/productos/{id}/variantes (token con rol Vendedor).
Tablas: producto, variante_producto, variante_valor, valor_atributo, atributo.
No usa stored procedure.
"""
import os
import re
import unicodedata

import boto3
import pymysql

from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_ERROR_INTERNO,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_VARIANTE_REGISTRADA = "Variante registrada correctamente"  # DFR 3.6
MSG_VARIANTE_EXISTE = "La variante ya existe para este producto"  # DFR 3.6
MSG_STOCK_NEGATIVO = "El stock no puede ser negativo"  # DFR 3.6
MSG_STOCK_ENTERO = "El stock debe ser un número entero"  # aprobado por Ian
MSG_STOCK_INVALIDO = "El stock no es válido"  # aprobado por Ian
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_PRODUCTO_INACTIVO = "El producto está inactivo y no se puede editar"  # aprobado por Ian
MSG_VALOR_NO_EXISTE = "Uno de los valores seleccionados no existe"  # aprobado por Ian
MSG_MISMO_ATRIBUTO = "No puedes elegir dos valores del mismo atributo"  # aprobado por Ian
MSG_COMBINACION_LARGA = (  # aprobado por Ian
    "La combinación de valores es demasiado larga; elige menos valores o valores más cortos"
)

STOCK_MIN = 0  # DFR 3.1: "entero mayor o igual a cero"
STOCK_MAX = 2147483647  # variante_producto.stock INT
SKU_MAX = 60  # variante_producto.sku VARCHAR(60)
VALORES_MAX = 20
ERRNO_DUPLICADO = 1062  # SKU repetido (UNIQUE uq_variante_sku)

_RE_ENTERO = re.compile(r"-?[0-9]+")
_RE_NO_SKU = re.compile(r"[^A-Z0-9]")

SQL_PRODUCTO = "SELECT id_vendedor, estado FROM producto WHERE id_producto = %s FOR UPDATE"
SQL_VALORES = """
    SELECT va.id_valor, va.valor, va.id_atributo
    FROM valor_atributo va
    WHERE va.id_valor IN ({marcas})
"""
SQL_COMBINACIONES = """
    SELECT vv.id_variante, vv.id_valor
    FROM variante_valor vv
    JOIN variante_producto v ON v.id_variante = vv.id_variante
    WHERE v.id_producto = %s
"""
SQL_INSERTAR_VARIANTE = "INSERT INTO variante_producto (id_producto, sku, stock) VALUES (%s, %s, %s)"
SQL_INSERTAR_VALOR = "INSERT INTO variante_valor (id_variante, id_valor) VALUES (%s, %s)"
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


def _stock(valor):
    """Mismas validaciones de stock que 3.1."""
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


def _ids_valores(valor):
    """Lista de id_valor distintos; vacía o ausente -> campos obligatorios."""
    if not isinstance(valor, list) or not valor:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if len(valor) > VALORES_MAX:
        raise ErrorNegocio(400, MSG_COMBINACION_LARGA)
    ids = [entero_positivo(v) for v in valor]
    if None in ids:
        raise ErrorNegocio(400, MSG_VALOR_NO_EXISTE)
    if len(set(ids)) != len(ids):  # el mismo valor dos veces
        raise ErrorNegocio(400, MSG_MISMO_ATRIBUTO)
    return ids


def _pieza_sku(texto, id_valor):
    """'Azul Marino' -> 'AZULMARINO' (sin acentos ni símbolos)."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    pieza = _RE_NO_SKU.sub("", sin_acentos.upper())
    return pieza or f"V{id_valor}"  # valor hecho solo de símbolos


def _variantes_desde_rds(filas):
    variantes = {}
    for fila in filas:
        variante = variantes.setdefault(
            fila["id_variante"],
            {"IdVariante": fila["id_variante"], "SKU": fila["sku"], "Stock": fila["stock"], "Atributos": {}},
        )
        if fila["atributo"] is not None:
            variante["Atributos"][fila["atributo"]] = fila["valor"]
    return list(variantes.values())


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])

    id_producto = entero_positivo(path_param(event, "id"))
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    datos = leer_body(event)
    stock_crudo = datos.get("stock")
    if stock_crudo is None or (isinstance(stock_crudo, str) and not stock_crudo.strip()):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    ids = _ids_valores(datos.get("valores"))
    stock = _stock(stock_crudo)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        marcas = ", ".join(["%s"] * len(ids))
        cursor.execute(SQL_VALORES.format(marcas=marcas), ids)
        valores = cursor.fetchall()
    if len(valores) != len(ids):
        raise ErrorNegocio(400, MSG_VALOR_NO_EXISTE)
    atributos = [v["id_atributo"] for v in valores]
    if len(set(atributos)) != len(atributos):
        raise ErrorNegocio(400, MSG_MISMO_ATRIBUTO)

    valores = sorted(valores, key=lambda v: v["id_atributo"])
    sku = f"P{id_producto}-" + "-".join(_pieza_sku(v["valor"], v["id_valor"]) for v in valores)
    if len(sku) > SKU_MAX:
        raise ErrorNegocio(400, MSG_COMBINACION_LARGA)

    # --- RDS sin confirmar (si algo falla, manejar_errores hace rollback) ---
    conexion.begin()
    with conexion.cursor() as cursor:
        # FOR UPDATE: dos registros simultáneos del mismo producto van en fila.
        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["id_vendedor"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)
        if producto["estado"] != "Activo":
            raise ErrorNegocio(409, MSG_PRODUCTO_INACTIVO)

        # DFR 3.6: no puede repetirse la combinación de valores
        cursor.execute(SQL_COMBINACIONES, (id_producto,))
        combinaciones = {}
        for fila in cursor.fetchall():
            combinaciones.setdefault(fila["id_variante"], set()).add(fila["id_valor"])
        if set(ids) in combinaciones.values():
            raise ErrorNegocio(409, MSG_VARIANTE_EXISTE)

        try:
            cursor.execute(SQL_INSERTAR_VARIANTE, (id_producto, sku, stock))
        except pymysql.err.IntegrityError as e:
            if e.args and e.args[0] == ERRNO_DUPLICADO:  # mismo SKU
                raise ErrorNegocio(409, MSG_VARIANTE_EXISTE)
            raise
        id_variante = cursor.lastrowid
        cursor.executemany(SQL_INSERTAR_VALOR, [(id_variante, i) for i in ids])

        cursor.execute(SQL_VARIANTES, (id_producto,))
        variantes = _variantes_desde_rds(cursor.fetchall())

    # --- DynamoDB antes del commit ---
    try:
        tabla_productos.update_item(
            Key={"productoID": str(id_producto)},
            UpdateExpression="SET #Variantes = :variantes, #Stock = :stock",
            ConditionExpression="attribute_exists(productoID)",
            ExpressionAttributeNames={"#Variantes": "Variantes", "#Stock": "Stock"},
            ExpressionAttributeValues={
                ":variantes": variantes,
                ":stock": sum(v["Stock"] for v in variantes),  # suma, incluida la estándar
            },
        )
    except Exception as e:
        print(f"DynamoDB falló al registrar la variante {sku}; rollback en RDS: {e!r}")
        conexion.rollback()
        raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    conexion.commit()
    return ok(MSG_VARIANTE_REGISTRADA, status=201, id_variante=id_variante, sku=sku)
