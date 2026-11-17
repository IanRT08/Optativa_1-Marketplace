"""
lambda-crearCategoria
DFR 2.1 Crear categoría (Administrador): registra una categoría con nombre
único, descripción opcional y categoría padre opcional (debe existir).
Ruta: POST /categorias (token con rol Administrador).
Tabla: categoria. No usa stored procedure.
"""
import pymysql

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_ADMINISTRADOR,
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

MSG_CATEGORIA_EXISTE = "La categoría ya existe"
MSG_CATEGORIA_CREADA = "Categoría creada correctamente"
MSG_PADRE_NO_EXISTE = "La categoría padre no existe"
MSG_LONGITUD = "El nombre no puede superar 100 caracteres y la descripción 255"

NOMBRE_MAX = 100       # categoria.nombre VARCHAR(100)
DESCRIPCION_MAX = 255  # categoria.descripcion VARCHAR(255)

ERRNO_DUPLICADO = 1062  # uq_categoria_nombre
ERRNO_FK = 1452         # fk_categoria_padre (el padre se borró entre la validación y el INSERT)

SQL_EXISTE_CATEGORIA = "SELECT 1 FROM categoria WHERE id_categoria = %s LIMIT 1"
SQL_EXISTE_NOMBRE = "SELECT 1 FROM categoria WHERE nombre = %s LIMIT 1"
SQL_INSERTAR = """
    INSERT INTO categoria (nombre, descripcion, id_categoria_padre)
    VALUES (%s, %s, %s)
"""


@manejar_errores
def lambda_handler(event, context):
    # Regla: solo un administrador puede crear categorías
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    datos = leer_body(event)
    nombre = campo_texto(datos, "nombre")
    descripcion = campo_texto(datos, "descripcion") or None  # opcional
    padre_crudo = datos.get("id_categoria_padre")             # opcional

    if not nombre:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    if len(nombre) > NOMBRE_MAX or (descripcion and len(descripcion) > DESCRIPCION_MAX):
        raise ErrorNegocio(400, MSG_LONGITUD)

    validar_texto(nombre, "El nombre")
    if descripcion:
        validar_texto(descripcion, "La descripción")

    id_padre = None
    if padre_crudo not in (None, ""):
        id_padre = entero_positivo(padre_crudo)
        if id_padre is None:
            raise ErrorNegocio(400, MSG_PADRE_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        # Regla: si se indica una categoría padre, debe existir
        if id_padre is not None:
            cursor.execute(SQL_EXISTE_CATEGORIA, (id_padre,))
            if not cursor.fetchone():
                raise ErrorNegocio(400, MSG_PADRE_NO_EXISTE)

        # Regla: el nombre de la categoría no puede repetirse
        cursor.execute(SQL_EXISTE_NOMBRE, (nombre,))
        if cursor.fetchone():
            raise ErrorNegocio(409, MSG_CATEGORIA_EXISTE)

    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_INSERTAR, (nombre, descripcion, id_padre))
            id_categoria = cursor.lastrowid
    except pymysql.err.IntegrityError as e:
        codigo = e.args[0] if e.args else None
        if codigo == ERRNO_DUPLICADO:
            raise ErrorNegocio(409, MSG_CATEGORIA_EXISTE)
        if codigo == ERRNO_FK:
            raise ErrorNegocio(400, MSG_PADRE_NO_EXISTE)
        raise

    return ok(MSG_CATEGORIA_CREADA, status=201, id_categoria=id_categoria)
