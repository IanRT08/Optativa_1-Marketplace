"""
lambda-registrarUsuario
DFR 1.1 Registro de usuario (Comprador): crea la cuenta con rol Comprador y
estado Activo. La contraseña se guarda solo como hash bcrypt.
Ruta: POST /usuarios/registro (abierta, sin token).
Tabla: usuario (id_rol tomado de la tabla rol). No usa stored procedure.
"""
import pymysql

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    MSG_CORREO_FORMATO,
    MSG_CORREO_REGISTRADO,
    MSG_NOMBRE_LARGO,
    MSG_PASSWORD_INVALIDA,
    ROL_COMPRADOR,
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
)

MSG_PASSWORDS_NO_COINCIDEN = "Las contraseñas no coinciden"
MSG_REGISTRO_EXITOSO = "Registro exitoso"

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
    datos = leer_body(event)

    nombre = campo_texto(datos, "nombre")
    apellido = campo_texto(datos, "apellido")
    email = campo_texto(datos, "email").lower()
    password = campo_password(datos, "password")
    confirmar_password = campo_password(datos, "confirmar_password")

    # Reglas de negocio del DFR 1.1
    if not all([nombre, apellido, email, password, confirmar_password]):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    if not nombre_valido(nombre, apellido):
        raise ErrorNegocio(400, MSG_NOMBRE_LARGO)

    # Formato de textos libres (espacios seguidos, especiales seguidos, solo números)
    validar_texto(nombre, "El nombre")
    validar_texto(apellido, "El apellido")

    if not email_valido(email):
        raise ErrorNegocio(400, MSG_CORREO_FORMATO)

    if not password_valida(password):
        raise ErrorNegocio(400, MSG_PASSWORD_INVALIDA)

    if password != confirmar_password:
        raise ErrorNegocio(400, MSG_PASSWORDS_NO_COINCIDEN)

    conexion = obtener_conexion()

    # El correo no debe existir en un registro previo
    with conexion.cursor() as cursor:
        cursor.execute(SQL_EXISTE_EMAIL, (email,))
        if cursor.fetchone():
            raise ErrorNegocio(409, MSG_CORREO_REGISTRADO)

    # Hash irreversible generado en la Lambda (nunca se guarda el texto plano)
    password_hash = hashear_password(password)

    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                SQL_INSERTAR_USUARIO,
                (nombre, apellido, email, password_hash, ROL_COMPRADOR),
            )
            filas = cursor.rowcount
            id_usuario = cursor.lastrowid
    except pymysql.err.IntegrityError as e:
        if e.args and e.args[0] == ERRNO_DUPLICADO:
            # Otro registro con el mismo correo entró entre la verificación y el INSERT
            raise ErrorNegocio(409, MSG_CORREO_REGISTRADO)
        raise

    if filas != 1:
        # Solo pasa si falta el catálogo de roles (INSERT inicial del script)
        raise RuntimeError("No existe el rol Comprador en la tabla rol")

    return ok(MSG_REGISTRO_EXITOSO, status=201, id_usuario=id_usuario)
