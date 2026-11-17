"""
lambda-editarCategoria
DFR 2.3 Editar categoría (Administrador): actualiza nombre, descripción y
categoría padre. El nombre no puede coincidir con el de otra categoría y una
categoría no puede ser su propio padre ni tener como padre a una de sus
subcategorías (evita ciclos).
Ruta: PUT /categorias/{id} (token con rol Administrador).
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
    path_param,
    validar_texto,
    validar_token,
)

MSG_CATEGORIA_ACTUALIZADA = "Categoría actualizada correctamente"
MSG_CATEGORIA_EXISTE = "La categoría ya existe"
MSG_CATEGORIA_NO_EXISTE = "La categoría no existe"
MSG_PROPIO_PADRE = "Una categoría no puede ser su propia categoría padre"
MSG_PADRE_ES_SUBCATEGORIA = "Una categoría no puede tener como padre a una de sus subcategorías"
MSG_PADRE_NO_EXISTE = "La categoría padre no existe"
MSG_LONGITUD = "El nombre no puede superar 100 caracteres y la descripción 255"

NOMBRE_MAX = 100       # categoria.nombre VARCHAR(100)
DESCRIPCION_MAX = 255  # categoria.descripcion VARCHAR(255)

ERRNO_DUPLICADO = 1062  # uq_categoria_nombre
ERRNO_FK = 1452         # fk_categoria_padre

SQL_EXISTE_CATEGORIA = "SELECT 1 FROM categoria WHERE id_categoria = %s LIMIT 1"

SQL_NOMBRE_EN_OTRA = """
    SELECT 1 FROM categoria
    WHERE nombre = %s AND id_categoria <> %s
    LIMIT 1
"""

# Recorre los ancestros del padre propuesto. Si la categoría que se edita
# aparece en esa cadena, el padre propuesto es una de sus subcategorías y se
# formaría un ciclo. UNION (sin ALL) detiene la recursión si hubiera un ciclo
# previo en los datos.
SQL_PADRE_ES_DESCENDIENTE = """
    WITH RECURSIVE ancestros (id_categoria, id_categoria_padre) AS (
        SELECT id_categoria, id_categoria_padre
        FROM categoria
        WHERE id_categoria = %s
        UNION
        SELECT c.id_categoria, c.id_categoria_padre
        FROM categoria c
        JOIN ancestros a ON c.id_categoria = a.id_categoria_padre
    )
    SELECT 1 FROM ancestros WHERE id_categoria = %s LIMIT 1
"""

SQL_ACTUALIZAR = """
    UPDATE categoria
    SET nombre = %s,
        descripcion = %s,
        id_categoria_padre = %s
    WHERE id_categoria = %s
"""


@manejar_errores
def lambda_handler(event, context):
    # Solo un administrador puede editar categorías
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    id_categoria = entero_positivo(path_param(event, "id"))
    if id_categoria is None:
        raise ErrorNegocio(404, MSG_CATEGORIA_NO_EXISTE)

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

    # DFR 2.3: una categoría no puede ser su propia categoría padre
    if id_padre == id_categoria:
        raise ErrorNegocio(400, MSG_PROPIO_PADRE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_EXISTE_CATEGORIA, (id_categoria,))
        if not cursor.fetchone():
            raise ErrorNegocio(404, MSG_CATEGORIA_NO_EXISTE)

        if id_padre is not None:
            cursor.execute(SQL_EXISTE_CATEGORIA, (id_padre,))
            if not cursor.fetchone():
                raise ErrorNegocio(400, MSG_PADRE_NO_EXISTE)

            # Evita ciclos: el padre no puede ser una subcategoría (directa o indirecta)
            cursor.execute(SQL_PADRE_ES_DESCENDIENTE, (id_padre, id_categoria))
            if cursor.fetchone():
                raise ErrorNegocio(400, MSG_PADRE_ES_SUBCATEGORIA)

        # DFR 2.3: el nombre no puede coincidir con el de otra categoría
        cursor.execute(SQL_NOMBRE_EN_OTRA, (nombre, id_categoria))
        if cursor.fetchone():
            raise ErrorNegocio(409, MSG_CATEGORIA_EXISTE)

    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_ACTUALIZAR, (nombre, descripcion, id_padre, id_categoria))
    except pymysql.err.IntegrityError as e:
        codigo = e.args[0] if e.args else None
        if codigo == ERRNO_DUPLICADO:
            raise ErrorNegocio(409, MSG_CATEGORIA_EXISTE)
        if codigo == ERRNO_FK:
            raise ErrorNegocio(400, MSG_PADRE_NO_EXISTE)
        raise

    return ok(MSG_CATEGORIA_ACTUALIZADA, id_categoria=id_categoria)
