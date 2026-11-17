"""
lambda-editarUsuario
DFR 1.5 Editar usuario (Administrador): actualiza nombre, apellido, rol y
estado de un usuario. El correo y la contraseña no se editan aquí.
Regla aprobada por Ian: un administrador no puede cambiar su propio rol ni su
propio estado (evita dejar el sistema sin administradores); al editarse a sí
mismo solo cambia nombre y apellido.
Ruta: PUT /admin/usuarios/{id} (token con rol Administrador).
Tablas: usuario, rol. No usa stored procedure.
"""
from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_NOMBRE_LARGO,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    ROL_VENDEDOR,
    ErrorNegocio,
    campo_texto,
    entero_positivo,
    leer_body,
    manejar_errores,
    nombre_valido,
    obtener_conexion,
    ok,
    path_param,
    validar_texto,
    validar_token,
)

MSG_USUARIO_ACTUALIZADO = "Usuario actualizado correctamente"
MSG_USUARIO_NO_EXISTE = "El usuario no existe"
MSG_ROL_INVALIDO = "El rol seleccionado no es válido"
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"
MSG_PROPIO_ROL_ESTADO = "No puedes cambiar tu propio rol o estado"

ROLES_SISTEMA = {r.lower(): r for r in (ROL_ADMINISTRADOR, ROL_VENDEDOR, ROL_COMPRADOR)}
ESTADOS_USUARIO = {"activo": "Activo", "inactivo": "Inactivo"}  # usuario.estado ENUM

SQL_USUARIO_ACTUAL = """
    SELECT u.estado, r.nombre AS rol
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
    WHERE u.id_usuario = %s
"""

SQL_ACTUALIZAR = """
    UPDATE usuario
    SET nombre = %s,
        apellido = %s,
        id_rol = (SELECT id_rol FROM rol WHERE nombre = %s),
        estado = %s
    WHERE id_usuario = %s
"""


@manejar_errores
def lambda_handler(event, context):
    # DFR 1.5: solo un administrador puede editar usuarios
    sesion = validar_token(event, roles=[ROL_ADMINISTRADOR])

    id_usuario = entero_positivo(path_param(event, "id"))
    if id_usuario is None:
        raise ErrorNegocio(404, MSG_USUARIO_NO_EXISTE)

    es_propio = id_usuario == sesion["id_usuario"]

    datos = leer_body(event)
    nombre = campo_texto(datos, "nombre")
    apellido = campo_texto(datos, "apellido")
    rol_recibido = campo_texto(datos, "rol")
    estado_recibido = campo_texto(datos, "estado")

    # DFR 1.5: no se pueden dejar campos obligatorios vacíos.
    # Al editarse a sí mismo, rol y estado no se capturan (no son editables).
    if not nombre or not apellido:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if not es_propio and (not rol_recibido or not estado_recibido):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    if not nombre_valido(nombre, apellido):
        raise ErrorNegocio(400, MSG_NOMBRE_LARGO)

    validar_texto(nombre, "El nombre")
    validar_texto(apellido, "El apellido")

    rol = None
    if rol_recibido:
        rol = ROLES_SISTEMA.get(rol_recibido.lower())
        if rol is None:
            raise ErrorNegocio(400, MSG_ROL_INVALIDO)

    estado = None
    if estado_recibido:
        estado = ESTADOS_USUARIO.get(estado_recibido.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_USUARIO_ACTUAL, (id_usuario,))
        actual = cursor.fetchone()

    if not actual:
        raise ErrorNegocio(404, MSG_USUARIO_NO_EXISTE)

    if es_propio:
        # El administrador en sesión conserva su rol y su estado
        if (rol and rol != actual["rol"]) or (estado and estado != actual["estado"]):
            raise ErrorNegocio(403, MSG_PROPIO_ROL_ESTADO)
        rol = actual["rol"]
        estado = actual["estado"]

    with conexion.cursor() as cursor:
        cursor.execute(SQL_ACTUALIZAR, (nombre, apellido, rol, estado, id_usuario))

    return ok(MSG_USUARIO_ACTUALIZADO, id_usuario=id_usuario, rol=rol, estado=estado)
