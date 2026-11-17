"""
lambda-crearUsuario
DFR 1.3 Crear usuario (Administrador): el administrador registra una cuenta
con rol Administrador, Vendedor o Comprador. La cuenta queda Activa y la
contraseña se guarda solo como hash bcrypt.
Ruta: POST /admin/usuarios (token con rol Administrador).
Tablas: usuario, rol. No usa stored procedure.
"""
import pymysql

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_CORREO_FORMATO,
    MSG_CORREO_REGISTRADO,
    MSG_NOMBRE_LARGO,
    MSG_PASSWORD_INVALIDA,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    ROL_VENDEDOR,
    ErrorNegocio,
    campo_password,
    campo_texto,
    email_valido,
    hashear_password,
    leer_body,
    manejar_errores,
    nombre_valido,
    obtener_conexion,
    ok,
    password_valida,
    validar_texto,
    validar_token,
)

MSG_USUARIO_CREADO = "Usuario creado exitosamente"
MSG_ROL_INVALIDO = "El rol seleccionado no es válido"

# Roles del sistema (tabla rol). Se aceptan sin distinguir mayúsculas.
ROLES_SISTEMA = {r.lower(): r for r in (ROL_ADMINISTRADOR, ROL_VENDEDOR, ROL_COMPRADOR)}

ERRNO_DUPLICADO = 1062  # llave única uq_usuario_email

SQL_EXISTE_EMAIL = "SELECT 1 FROM usuario WHERE email = %s LIMIT 1"

# El id del rol se toma de la tabla rol por nombre (no se fija el número).
SQL_INSERTAR_USUARIO = """
    INSERT INTO usuario (id_rol, nombre, apellido, email, password_hash, estado)
    SELECT r.id_rol, %s, %s, %s, %s, 'Activo'
    FROM rol r
    WHERE r.nombre = %s
"""


@manejar_errores
def lambda_handler(event, context):
    # DFR 1.3: solo un administrador puede crear usuarios desde este módulo
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    datos = leer_body(event)
    nombre = campo_texto(datos, "nombre")
    apellido = campo_texto(datos, "apellido")
    email = campo_texto(datos, "email").lower()
    password = campo_password(datos, "password")
    rol_recibido = campo_texto(datos, "rol")

    if not all([nombre, apellido, email, password, rol_recibido]):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    if not nombre_valido(nombre, apellido):
        raise ErrorNegocio(400, MSG_NOMBRE_LARGO)

    validar_texto(nombre, "El nombre")
    validar_texto(apellido, "El apellido")

    if not email_valido(email):
        raise ErrorNegocio(400, MSG_CORREO_FORMATO)

    if not password_valida(password):
        raise ErrorNegocio(400, MSG_PASSWORD_INVALIDA)

    rol = ROLES_SISTEMA.get(rol_recibido.lower())
    if rol is None:
        raise ErrorNegocio(400, MSG_ROL_INVALIDO)

    conexion = obtener_conexion()

    # El correo no debe existir en un registro previo
    with conexion.cursor() as cursor:
        cursor.execute(SQL_EXISTE_EMAIL, (email,))
        if cursor.fetchone():
            raise ErrorNegocio(409, MSG_CORREO_REGISTRADO)

    password_hash = hashear_password(password)

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                SQL_INSERTAR_USUARIO,
                (nombre, apellido, email, password_hash, rol),
            )
            filas = cursor.rowcount
            id_usuario = cursor.lastrowid
    except pymysql.err.IntegrityError as e:
        if e.args and e.args[0] == ERRNO_DUPLICADO:
            raise ErrorNegocio(409, MSG_CORREO_REGISTRADO)
        raise

    if filas != 1:
        # Solo pasa si falta el catálogo de roles (INSERT inicial del script)
        raise RuntimeError(f"No existe el rol {rol} en la tabla rol")

    return ok(MSG_USUARIO_CREADO, status=201, id_usuario=id_usuario, rol=rol)
