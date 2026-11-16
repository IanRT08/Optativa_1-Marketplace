# LAMBDAS: SMAVIB

Código para pegar en el editor de la consola de Lambda (archivo `lambda_function.py`, handler `lambda_function.lambda_handler`).

Todas las funciones usan dos Layers:
- **Layer 1**: PyMySQL, bcrypt, PyJWT (la armas tú).
- **Layer 2**: `smavib_common.py`. El archivo está en `lambdas/layer/python/smavib_common.py`; comprime la carpeta `python/` tal cual.

Runtime: Python 3.14 · Arquitectura: x86_64 · Rol: LabRole · Región: us-east-1

---

## lambda-consultarCategorias: DFR 2.2 Consultar categorías

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /categorias` (ruta nueva) |
| Acceso | Abierta, sin token (decisión 2026-11-13: la usan 3.1 y 4.1) |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |
| Prueba en consola | Evento `{}` |

**Respuestas**
- 200 `{"mensaje": "Consulta realizada", "categorias": [{id_categoria, nombre, descripcion, id_categoria_padre, categoria_padre}, ...]}`
- 200 `{"mensaje": "No se encontraron registros", "categorias": []}` cuando no hay categorías (DFR 2.2)
- 500 `{"error": "Ocurrió un error interno. Intenta más tarde"}`

```python
"""
lambda-consultarCategorias
DFR 2.2 Consultar categorías: lista las categorías indicando su categoría
padre cuando la tienen.
Ruta: GET /categorias (abierta, sin token).
Tabla: categoria (autorrelación id_categoria_padre). No usa stored procedure.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    manejar_errores,
    obtener_conexion,
    ok,
)

SQL_CATEGORIAS = """
    SELECT c.id_categoria,
           c.nombre,
           c.descripcion,
           c.id_categoria_padre,
           p.nombre AS categoria_padre
    FROM categoria c
    LEFT JOIN categoria p ON p.id_categoria = c.id_categoria_padre
    ORDER BY c.nombre
"""


@manejar_errores
def lambda_handler(event, context):
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CATEGORIAS)
        categorias = cursor.fetchall()

    if not categorias:
        # DFR 2.2: "Si no existen categorías, el sistema mostrará:
        # 'No se encontraron registros'". Se responde 200 con lista vacía.
        return ok(MSG_SIN_REGISTROS, categorias=[])

    return ok("Consulta realizada", categorias=categorias)
```

---

## lambda-registrarUsuario: DFR 1.1 Registro de usuario (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /usuarios/registro` (ruta nueva) |
| Acceso | Abierta, sin token |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME |
| Layers | Layer 1 (usa bcrypt) + Layer 2 |
| Timeout / memoria | 10 s / 256 MB (bcrypt usa CPU; con 128 MB el hash tarda notablemente más) |

**Body (JSON)**
```json
{"nombre": "Ana", "apellido": "López", "email": "ana@correo.com", "password": "Segura#2026", "confirmar_password": "Segura#2026"}
```

**Respuestas**
| Status | Body | Caso (DFR 1.1) |
|---|---|---|
| 201 | `{"mensaje": "Registro exitoso", "id_usuario": 15}` | Datos correctos. Flask redirige a la pantalla principal |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta un campo |
| 400 | `{"error": "El nombre y el apellido no pueden superar 80 caracteres"}` | Nombre o apellido demasiado largo (mensaje aprobado por Ian) |
| 400 | `{"error": "El nombre no puede tener espacios en blanco seguidos"}` (también: "...más de dos caracteres especiales seguidos", "...contener solo números"; igual con "El apellido") | Formato de texto inválido (regla de Ian) |
| 400 | `{"error": "El formato del correo electrónico no es válido"}` | Correo con formato incorrecto (mensaje aprobado por Ian) |
| 400 | `{"error": "La contraseña debe tener mínimo 8 caracteres, una mayúscula, un número y un carácter especial"}` | Contraseña débil |
| 400 | `{"error": "Las contraseñas no coinciden"}` | Confirmación distinta |
| 409 | `{"error": "El correo electrónico ya está registrado"}` | Correo existente |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: evento `{"body": "{\"nombre\":\"Ana\",\"apellido\":\"López\",\"email\":\"ana@correo.com\",\"password\":\"Segura#2026\",\"confirmar_password\":\"Segura#2026\"}"}`

```python
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
```

---

## lambda-iniciarSesion: DFR 1.2 Inicio de sesión (Comprador, Vendedor, Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /auth/login` (ruta nueva) |
| Acceso | Abierta, sin token. Emite el JWT que usan las demás Lambdas |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, **JWT_SECRET** (32 caracteres o más; el mismo valor en todas las Lambdas) |
| Layers | Layer 1 (bcrypt y PyJWT) + Layer 2 |
| Timeout / memoria | 10 s / 256 MB |

**Body (JSON)**
```json
{"email": "ana@correo.com", "password": "Segura#2026"}
```

**Respuestas**
| Status | Body | Caso (DFR 1.2) |
|---|---|---|
| 200 | `{"mensaje": "Sesión iniciada", "token": "eyJ...", "expira_en": 7200, "id_usuario": 15, "nombre": "Ana", "apellido": "López", "rol": "Comprador"}` | Credenciales correctas. Flask guarda el token y redirige según el rol |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta el correo o la contraseña |
| 404 | `{"error": "Usuario no encontrado"}` | El correo no existe |
| 401 | `{"error": "Contraseña incorrecta"}` | Contraseña que no coincide |
| 403 | `{"error": "La cuenta se encuentra inactiva"}` | Cuenta Inactiva (se revisa después de la contraseña) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

Flask debe mandar en cada petición protegida el header `Authorization: Bearer <token>`.

**Prueba en consola**: evento `{"body": "{\"email\":\"ana@correo.com\",\"password\":\"Segura#2026\"}"}`

```python
"""
lambda-iniciarSesion
DFR 1.2 Inicio de sesión (Comprador, Vendedor, Administrador): valida correo
y contraseña (bcrypt) y emite un JWT HS256 válido por 2 horas con el
id_usuario y el rol.
Ruta: POST /auth/login (abierta, sin token).
Tablas: usuario, rol. No usa stored procedure.
"""
from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    SESION_HORAS,
    ErrorNegocio,
    campo_password,
    campo_texto,
    emitir_token,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    verificar_password,
)

MSG_USUARIO_NO_ENCONTRADO = "Usuario no encontrado"
MSG_PASSWORD_INCORRECTA = "Contraseña incorrecta"
MSG_CUENTA_INACTIVA = "La cuenta se encuentra inactiva"
MSG_SESION_INICIADA = "Sesión iniciada"

SQL_USUARIO_POR_EMAIL = """
    SELECT u.id_usuario,
           u.nombre,
           u.apellido,
           u.password_hash,
           u.estado,
           r.nombre AS rol
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
    WHERE u.email = %s
    LIMIT 1
"""


@manejar_errores
def lambda_handler(event, context):
    datos = leer_body(event)

    email = campo_texto(datos, "email").lower()  # 1.1 guarda el correo en minúsculas
    password = campo_password(datos, "password")

    if not email or not password:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_USUARIO_POR_EMAIL, (email,))
        usuario = cursor.fetchone()

    # Regla 1: el usuario debe existir en el sistema
    if not usuario:
        raise ErrorNegocio(404, MSG_USUARIO_NO_ENCONTRADO)

    # Regla 2: la contraseña debe coincidir con la registrada (hash bcrypt)
    if not verificar_password(password, usuario["password_hash"]):
        raise ErrorNegocio(401, MSG_PASSWORD_INCORRECTA)

    # Regla 3: la cuenta debe estar activa (se revisa después de la contraseña
    # para no revelar el estado de la cuenta a quien no conoce la contraseña)
    if usuario["estado"] != "Activo":
        raise ErrorNegocio(403, MSG_CUENTA_INACTIVA)

    token = emitir_token(usuario["id_usuario"], usuario["rol"])

    # Inicia sesión según el rol de la cuenta: Flask redirige con 'rol'
    return ok(
        MSG_SESION_INICIADA,
        token=token,
        expira_en=SESION_HORAS * 3600,
        id_usuario=usuario["id_usuario"],
        nombre=usuario["nombre"],
        apellido=usuario["apellido"],
        rol=usuario["rol"],
    )
```

---

## lambda-crearCategoria: DFR 2.1 Crear categoría (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /categorias` (ruta nueva; misma ruta que 2.2 con otro método) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**: `id_categoria_padre` y `descripcion` son opcionales (pueden omitirse, ir vacíos o en `null`).
```json
{"nombre": "Tenis", "descripcion": "Calzado deportivo", "id_categoria_padre": 3}
```

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 201 | `{"mensaje": "Categoría creada correctamente", "id_categoria": 12}` | DFR 2.1: datos correctos |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | DFR 2.1: falta el nombre (o solo trae espacios) |
| 400 | `{"error": "El nombre no puede superar 100 caracteres y la descripción 255"}` | Longitud (mensaje aprobado por Ian) |
| 400 | `{"error": "El nombre no puede tener espacios en blanco seguidos"}` (también "...más de dos caracteres especiales seguidos", "...contener solo números"; igual con "La descripción") | Formato de texto (regla de Ian) |
| 400 | `{"error": "La categoría padre no existe"}` | Padre inexistente o id no válido (mensaje aprobado por Ian) |
| 409 | `{"error": "La categoría ya existe"}` | DFR 2.1: nombre repetido |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Sin token o token vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token de un administrador>"}, "body": "{\"nombre\":\"Tenis\",\"descripcion\":\"Calzado deportivo\"}"}`

```python
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

    return ok(MSG_CATEGORIA_CREADA, status=201, id_cateoria=id_categoria)
```

---

## lambda-editarCategoria: DFR 2.3 Editar categoría (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PUT /categorias/{id}` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**: es un PUT, así que se manda la categoría completa. Si `descripcion` o `id_categoria_padre` se omiten o van vacíos, quedan en NULL (Flask debe reenviar los valores actuales del formulario).
```json
{"nombre": "Tenis", "descripcion": "Calzado deportivo", "id_categoria_padre": 3}
```

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Categoría actualizada correctamente", "id_categoria": 12}` | DFR 2.3: edición válida |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta el nombre |
| 400 | `{"error": "El nombre no puede superar 100 caracteres y la descripción 255"}` | Longitud |
| 400 | `{"error": "El nombre no puede tener espacios en blanco seguidos"}` (y demás reglas de `validar_texto`) | Formato de texto |
| 400 | `{"error": "Una categoría no puede ser su propia categoría padre"}` | DFR 2.3 |
| 400 | `{"error": "Una categoría no puede tener como padre a una de sus subcategorías"}` | Ciclo (aprobado por Ian) |
| 400 | `{"error": "La categoría padre no existe"}` | Padre inexistente o id no válido |
| 404 | `{"error": "La categoría no existe"}` | La categoría a editar no existe (aprobado por Ian) |
| 409 | `{"error": "La categoría ya existe"}` | DFR 2.3: el nombre ya lo usa otra categoría |
| 401 / 403 | Sesión inválida / "Acceso restringido" | Sin token o rol distinto de Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "pathParameters": {"id": "12"}, "body": "{\"nombre\":\"Tenis\",\"descripcion\":\"Calzado deportivo\",\"id_categoria_padre\":3}"}`

```python
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
```

---

## lambda-eliminarCategoria: DFR 2.4 Eliminar categoría (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `DELETE /categorias/{id}` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body**: no lleva.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Categoría eliminada correctamente", "id_categoria": 12}` | DFR 2.4: eliminación válida |
| 409 | `{"error": "No se puede eliminar una categoría con productos asociados"}` | DFR 2.4: tiene productos (activos o inactivos) |
| 409 | `{"error": "No se puede eliminar una categoría con subcategorías"}` | DFR 2.4: tiene subcategorías |
| 404 | `{"error": "La categoría no existe"}` | No existe o el id no es válido |
| 401 / 403 | Sesión inválida / "Acceso restringido" | Sin token o rol distinto de Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "pathParameters": {"id": "12"}}`

```python
"""
lambda-eliminarCategoria
DFR 2.4 Eliminar categoría (Administrador): elimina una categoría que no se
utiliza. No se puede eliminar si tiene productos asociados (activos o
inactivos) ni si tiene subcategorías.
Borrado físico: el DFR indica "eliminada en BD" y la regla de bajas lógicas
no aplica a categorías (solo a usuarios, productos, pedidos y direcciones).
Ruta: DELETE /categorias/{id} (token con rol Administrador).
Tablas: categoria, producto. No usa stored procedure.
"""
import pymysql

from smavib_common import (
    ROL_ADMINISTRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_CATEGORIA_ELIMINADA = "Categoría eliminada correctamente"
MSG_CON_PRODUCTOS = "No se puede eliminar una categoría con productos asociados"
MSG_CON_SUBCATEGORIAS = "No se puede eliminar una categoría con subcategorías"
MSG_CATEGORIA_NO_EXISTE = "La categoría no existe"

ERRNO_FK_HIJOS = 1451  # fila referenciada por fk_producto_categoria o fk_categoria_padre

SQL_EXISTE_CATEGORIA = "SELECT 1 FROM categoria WHERE id_categoria = %s LIMIT 1"
SQL_TIENE_PRODUCTOS = "SELECT 1 FROM producto WHERE id_categoria = %s LIMIT 1"
SQL_TIENE_SUBCATEGORIAS = "SELECT 1 FROM categoria WHERE id_categoria_padre = %s LIMIT 1"
SQL_ELIMINAR = "DELETE FROM categoria WHERE id_categoria = %s"


def _validar_sin_dependencias(cursor, id_categoria):
    """Reglas del DFR 2.4, en el orden en que las lista el documento."""
    cursor.execute(SQL_TIENE_PRODUCTOS, (id_categoria,))
    if cursor.fetchone():
        raise ErrorNegocio(409, MSG_CON_PRODUCTOS)

    cursor.execute(SQL_TIENE_SUBCATEGORIAS, (id_categoria,))
    if cursor.fetchone():
        raise ErrorNegocio(409, MSG_CON_SUBCATEGORIAS)


@manejar_errores
def lambda_handler(event, context):
    # Solo un administrador puede eliminar categorías
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    id_categoria = entero_positivo(path_param(event, "id"))
    if id_categoria is None:
        raise ErrorNegocio(404, MSG_CATEGORIA_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_EXISTE_CATEGORIA, (id_categoria,))
        if not cursor.fetchone():
            raise ErrorNegocio(404, MSG_CATEGORIA_NO_EXISTE)

        _validar_sin_dependencias(cursor, id_categoria)

    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_ELIMINAR, (id_categoria,))
    except pymysql.err.IntegrityError as e:
        if e.args and e.args[0] == ERRNO_FK_HIJOS:
            # Entró un producto o una subcategoría entre la validación y el DELETE:
            # se vuelve a revisar para responder con el mensaje del DFR correcto.
            with conexion.cursor() as cursor:
                _validar_sin_dependencias(cursor, id_categoria)
        raise

    return ok(MSG_CATEGORIA_ELIMINADA, id_categoria=id_categoria)
```

---

## lambda-crearUsuario: DFR 1.3 Crear usuario (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /admin/usuarios` (ruta nueva) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 (usa bcrypt) + Layer 2 |
| Timeout / memoria | 10 s / 256 MB |

**Body (JSON)**: `rol` es el nombre del rol: `Administrador`, `Vendedor` o `Comprador`.
```json
{"nombre": "Luis", "apellido": "Pérez", "email": "luis@correo.com", "password": "Vende#2026", "rol": "Vendedor"}
```

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 201 | `{"mensaje": "Usuario creado exitosamente", "id_usuario": 20, "rol": "Vendedor"}` | DFR 1.3: registro correcto |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta un campo |
| 400 | `{"error": "El nombre y el apellido no pueden superar 80 caracteres"}` | Longitud |
| 400 | `{"error": "El nombre no puede tener espacios en blanco seguidos"}` (y demás reglas de `validar_texto`; igual con "El apellido") | Formato de texto |
| 400 | `{"error": "El formato del correo electrónico no es válido"}` | Formato de correo |
| 400 | `{"error": "La contraseña debe tener mínimo 8 caracteres, una mayúscula, un número y un carácter especial"}` | DFR 1.3: contraseña débil |
| 400 | `{"error": "El rol seleccionado no es válido"}` | Rol distinto de los 3 del sistema (aprobado por Ian) |
| 409 | `{"error": "El correo electrónico ya está registrado"}` | DFR 1.3: correo existente |
| 401 | Sesión inválida | Sin token o token vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 1.3: el rol no es Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "body": "{\"nombre\":\"Luis\",\"apellido\":\"Pérez\",\"email\":\"luis@correo.com\",\"password\":\"Vende#2026\",\"rol\":\"Vendedor\"}"}`

```python
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
```

---

## lambda-consultarUsuarios: DFR 1.4 Consultar usuarios (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /admin/usuarios` (ruta nueva) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Query string (todos opcionales y combinables)**
| Parámetro | Valores | Uso |
|---|---|---|
| `rol` | Administrador, Vendedor, Comprador (sin distinguir mayúsculas) | Filtro DFR 1.4 |
| `estado` | Activo, Inactivo (sin distinguir mayúsculas) | Filtro DFR 1.4 |
| `cursor` | `siguiente_cursor` de la respuesta anterior | Página siguiente (20 por página) |

Ejemplo: `GET /admin/usuarios?rol=Vendedor&estado=Activo&cursor=40`

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "usuarios": [{id_usuario, nombre, apellido, email, rol, estado, fecha_registro}, ...], "siguiente_cursor": 60}` | Hay resultados. `siguiente_cursor` es `null` en la última página |
| 200 | `{"mensaje": "No se encontraron registros", "usuarios": [], "siguiente_cursor": null}` | DFR 1.4: sin resultados |
| 400 | `{"error": "El rol seleccionado no es válido"}` | Filtro de rol inválido |
| 400 | `{"error": "El estado seleccionado no es válido"}` | Filtro de estado inválido (aprobado por Ian) |
| 401 / 403 | Sesión inválida / "Acceso restringido" | Sin token o rol distinto de Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "queryStringParameters": {"rol": "Vendedor"}}`

```python
"""
lambda-consultarUsuarios
DFR 1.4 Consultar usuarios (Administrador): lista los usuarios registrados
con filtros opcionales y combinables por rol y estado. Paginado de 20 en 20
con cursor por id_usuario (rápido con muchos registros: usa la llave primaria).
Nunca devuelve password_hash.
Ruta: GET /admin/usuarios?rol=&estado=&cursor= (token con rol Administrador).
Tablas: usuario, rol. No usa stored procedure.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    ROL_VENDEDOR,
    ErrorNegocio,
    campo_texto,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_ROL_INVALIDO = "El rol seleccionado no es válido"
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"
MSG_CONSULTA = "Consulta realizada"

TAMANO_PAGINA = 20

# Valores permitidos en los filtros (se aceptan sin distinguir mayúsculas)
ROLES_SISTEMA = {r.lower(): r for r in (ROL_ADMINISTRADOR, ROL_VENDEDOR, ROL_COMPRADOR)}
ESTADOS_USUARIO = {"activo": "Activo", "inactivo": "Inactivo"}  # usuario.estado ENUM

SQL_BASE = """
    SELECT u.id_usuario,
           u.nombre,
           u.apellido,
           u.email,
           r.nombre AS rol,
           u.estado,
           u.fecha_registro
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
"""


@manejar_errores
def lambda_handler(event, context):
    # DFR 1.4: solo un administrador puede consultar la lista de usuarios
    validar_token(event, roles=[ROL_ADMINISTRADOR])

    params = query_params(event)
    rol_recibido = campo_texto(params, "rol")
    estado_recibido = campo_texto(params, "estado")
    cursor_recibido = entero_positivo(params.get("cursor"))  # inválido -> primera página

    # Los filtros se combinan con AND. Solo se concatenan fragmentos fijos;
    # los valores siempre van como parámetros (sin inyección SQL).
    condiciones = []
    valores = []

    if rol_recibido:
        rol = ROLES_SISTEMA.get(rol_recibido.lower())
        if rol is None:
            raise ErrorNegocio(400, MSG_ROL_INVALIDO)
        condiciones.append("r.nombre = %s")
        valores.append(rol)

    if estado_recibido:
        estado = ESTADOS_USUARIO.get(estado_recibido.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("u.estado = %s")
        valores.append(estado)

    if cursor_recibido is not None:
        condiciones.append("u.id_usuario > %s")
        valores.append(cursor_recibido)

    sql = SQL_BASE
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY u.id_usuario LIMIT %s"
    valores.append(TAMANO_PAGINA + 1)  # uno extra para saber si hay otra página

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(sql, valores)
        usuarios = cursor.fetchall()

    if not usuarios:
        # DFR 1.4: "Si no existen resultados, el sistema mostrará:
        # 'No se encontraron registros'". Se responde 200 con lista vacía.
        return ok(MSG_SIN_REGISTROS, usuarios=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(usuarios) > TAMANO_PAGINA:
        usuarios = usuarios[:TAMANO_PAGINA]
        siguiente_cursor = usuarios[-1]["id_usuario"]

    return ok(MSG_CONSULTA, usuarios=usuarios, siguiente_cursor=siguiente_cursor)
```

---

## lambda-editarUsuario: DFR 1.5 Editar usuario (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PUT /admin/usuarios/{id}` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"nombre": "Luis", "apellido": "Pérez", "rol": "Vendedor", "estado": "Activo"}
```
- Usuario distinto al de la sesión: los cuatro campos son obligatorios (DFR 1.5).
- **El administrador editándose a sí mismo**: solo se mandan `nombre` y `apellido`. La pantalla de Flask no debe mostrar rol ni estado; si llegan con un valor distinto al actual, se rechazan.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Usuario actualizado correctamente", "id_usuario": 20, "rol": "Vendedor", "estado": "Activo"}` | DFR 1.5: edición válida |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | DFR 1.5: falta un campo obligatorio |
| 400 | `{"error": "El nombre y el apellido no pueden superar 80 caracteres"}` | Longitud |
| 400 | `{"error": "El nombre no puede tener espacios en blanco seguidos"}` (y demás reglas de `validar_texto`; igual con "El apellido") | Formato de texto |
| 400 | `{"error": "El rol seleccionado no es válido"}` / `{"error": "El estado seleccionado no es válido"}` | Rol o estado fuera del catálogo |
| 403 | `{"error": "No puedes cambiar tu propio rol o estado"}` | El administrador intenta cambiar su propio rol o estado (aprobado por Ian) |
| 404 | `{"error": "El usuario no existe"}` | No existe o el id no es válido (aprobado por Ian) |
| 401 / 403 | Sesión inválida / "Acceso restringido" | Sin token o rol distinto de Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error inesperado |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "pathParameters": {"id": "20"}, "body": "{\"nombre\":\"Luis\",\"apellido\":\"Pérez\",\"rol\":\"Vendedor\",\"estado\":\"Activo\"}"}`

```python
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
```

---

## lambda-eliminarUsuario: DFR 1.6 Eliminar usuario (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PATCH /admin/usuarios/{id}/desactivar` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body**: ninguno. El usuario se elige con `{id}` en la ruta.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Usuario eliminado correctamente", "id_usuario": 20, "estado": "Inactivo"}` | DFR 1.6: baja lógica válida (también si ya estaba Inactivo) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 1.6: el rol no es Administrador |
| 403 | `{"error": "No puedes cambiar tu propio rol o estado"}` | El administrador intenta desactivarse a sí mismo |
| 404 | `{"error": "El usuario no existe"}` | Id inexistente o no válido |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "pathParameters": {"id": "20"}}`

```python
"""
lambda-eliminarUsuario
DFR 1.6 Eliminar usuario (Administrador): baja lógica. No borra el registro;
cambia usuario.estado a 'Inactivo' para conservar los pedidos y productos
asociados.
Reglas aprobadas por Ian:
- Un administrador no puede desactivarse a sí mismo (mismo mensaje que 1.5).
- Si el usuario ya estaba Inactivo, responde 200 con el mismo mensaje.
- Los productos de un Vendedor no se desactivan aquí: el DFR 1.6 solo cambia
  al usuario, y como 3.4 no permite reactivar productos, reactivar al
  vendedor en 1.5 no podría devolverlos.
Ruta: PATCH /admin/usuarios/{id}/desactivar (token con rol Administrador).
Tabla: usuario. No usa stored procedure.
"""
from smavib_common import (
    ROL_ADMINISTRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_USUARIO_ELIMINADO = "Usuario eliminado correctamente"  # DFR 1.6
MSG_USUARIO_NO_EXISTE = "El usuario no existe"  # aprobado por Ian
MSG_PROPIO_ROL_ESTADO = "No puedes cambiar tu propio rol o estado"  # aprobado por Ian

ESTADO_INACTIVO = "Inactivo"

SQL_ESTADO = "SELECT estado FROM usuario WHERE id_usuario = %s"
SQL_DESACTIVAR = "UPDATE usuario SET estado = 'Inactivo' WHERE id_usuario = %s"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_ADMINISTRADOR])

    id_usuario = entero_positivo(path_param(event, "id"))
    if id_usuario is None:
        raise ErrorNegocio(404, MSG_USUARIO_NO_EXISTE)

    if id_usuario == sesion["id_usuario"]:
        raise ErrorNegocio(403, MSG_PROPIO_ROL_ESTADO)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_ESTADO, (id_usuario,))
        fila = cursor.fetchone()
        if fila is None:
            raise ErrorNegocio(404, MSG_USUARIO_NO_EXISTE)

        # Baja lógica (nunca DELETE). Si ya estaba Inactivo no se vuelve a escribir.
        if fila["estado"] != ESTADO_INACTIVO:
            cursor.execute(SQL_DESACTIVAR, (id_usuario,))

    return ok(MSG_USUARIO_ELIMINADO, id_usuario=id_usuario, estado=ESTADO_INACTIVO)
```

---

## lambda-consultarMarcas: A1 Consultar marcas (apoyo, abierta)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /marcas` (ruta nueva) |
| Acceso | **Abierta** (sin token), igual que `GET /categorias`. Solo lee el catálogo público de marcas |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body**: ninguno.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "marcas": [{"id_marca": 3, "nombre": "Adidas"}, ...]}` | Hay marcas (ordenadas por nombre) |
| 200 | `{"mensaje": "No se encontraron registros", "marcas": []}` | La tabla está vacía |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{}`

```python
"""
lambda-consultarMarcas
A1 (endpoint de apoyo aprobado por Ian, no está en el DFR): lista las marcas
para el selector "Marca *" de 3.1 y 3.3 (DFR: "La categoría y la marca deben
existir en el sistema").
Ruta: GET /marcas, abierta (sin token): solo lee nombres públicos de marcas.
Tabla: marca. No usa stored procedure. Sin paginación: catálogo corto que se
llena con el seed de marcas.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    manejar_errores,
    obtener_conexion,
    ok,
)

MSG_CONSULTA = "Consulta realizada"

SQL_MARCAS = "SELECT id_marca, nombre FROM marca ORDER BY nombre"


@manejar_errores
def lambda_handler(event, context):
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_MARCAS)
        marcas = cursor.fetchall()

    if not marcas:
        return ok(MSG_SIN_REGISTROS, marcas=[])
    return ok(MSG_CONSULTA, marcas=marcas)
```

---

## lambda-consultarAtributos: A2 Consultar atributos y valores (apoyo, abierta)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /atributos` (ruta nueva) |
| Acceso | **Abierta** (sin token), igual que `GET /marcas`. Solo lee el catálogo público de atributos |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body**: ninguno.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "atributos": [{"id_atributo": 2, "nombre": "Color", "valores": [{"id_valor": 9, "valor": "Rojo"}]}, {"id_atributo": 1, "nombre": "Talla", "valores": [{"id_valor": 1, "valor": "CH"}, {"id_valor": 2, "valor": "M"}]}]}` | Atributos por nombre; valores en el orden en que se cargaron (`id_valor`) |
| 200 | `{"mensaje": "Consulta realizada", "atributos": [{"id_atributo": 1, "nombre": "Talla", "valores": []}]}` | Atributo sin valores todavía |
| 200 | `{"mensaje": "No se encontraron registros", "atributos": []}` | No hay atributos |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{}`

```python
"""
lambda-consultarAtributos
A2 (endpoint de apoyo aprobado por Ian, no está en el DFR): lista los
atributos con sus valores para 3.6 (DFR: "Los atributos y valores se
seleccionan del catálogo registrado en el sistema").
Ruta: GET /atributos, abierta (sin token): solo lee el catálogo público.
Tablas: atributo, valor_atributo. No usa stored procedure.
Orden: atributos por nombre; valores por id_valor (orden de carga), para que
las tallas no salgan en orden alfabético.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    manejar_errores,
    obtener_conexion,
    ok,
)

MSG_CONSULTA = "Consulta realizada"

# LEFT JOIN: un atributo sin valores también aparece (con lista vacía).
SQL_ATRIBUTOS = """
    SELECT a.id_atributo, a.nombre, v.id_valor, v.valor
    FROM atributo a
    LEFT JOIN valor_atributo v ON v.id_atributo = a.id_atributo
    ORDER BY a.nombre, a.id_atributo, v.id_valor
"""


@manejar_errores
def lambda_handler(event, context):
    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_ATRIBUTOS)
        filas = cursor.fetchall()

    # Agrupa las filas por atributo conservando el orden de la consulta.
    atributos = {}
    for fila in filas:
        atributo = atributos.setdefault(
            fila["id_atributo"],
            {"id_atributo": fila["id_atributo"], "nombre": fila["nombre"], "valores": []},
        )
        if fila["id_valor"] is not None:
            atributo["valores"].append({"id_valor": fila["id_valor"], "valor": fila["valor"]})

    if not atributos:
        return ok(MSG_SIN_REGISTROS, atributos=[])
    return ok(MSG_CONSULTA, atributos=list(atributos.values()))
```

---

## lambda-registrarDireccion: DFR 9.1 Registrar dirección de envío (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /direcciones` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"calle": "Av. Juárez", "numero": "120-B", "colonia": "Centro", "ciudad": "Monterrey", "estado": "Nuevo León", "codigo_postal": "64000"}
```
- Los seis campos son obligatorios (DFR 9.1). `estado` se guarda en `direccion.estado_region`.
- `codigo_postal` debe mandarse como **texto** de 5 dígitos. Como número se pierde el cero inicial (01234 → 1234) y se rechaza.
- El comprador sale del token, nunca del body.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 201 | `{"mensaje": "Dirección registrada correctamente", "id_direccion": 7}` | DFR 9.1: datos correctos |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | DFR 9.1: falta un campo obligatorio |
| 400 | `{"error": "El código postal debe tener 5 dígitos"}` | DFR 9.1 |
| 400 | `{"error": "La calle no puede superar 150 caracteres, el número 20 y la colonia, la ciudad y el estado 100"}` | Longitud (aprobado por Ian) |
| 400 | `{"error": "La calle no puede tener espacios en blanco seguidos"}` (y demás mensajes de `validar_texto`) | Regla de textos libres de Ian |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "body": "{\"calle\":\"Av. Juárez\",\"numero\":\"120-B\",\"colonia\":\"Centro\",\"ciudad\":\"Monterrey\",\"estado\":\"Nuevo León\",\"codigo_postal\":\"64000\"}"}`

```python
"""
lambda-registrarDireccion
DFR 9.1 Registrar dirección de envío (Comprador): la dirección queda ligada al
comprador de la sesión y activa (activa = 1).
Reglas de Ian: textos libres con validar_texto (el número exterior admite solo
números); sin límite de direcciones por comprador.
Ruta: POST /direcciones (token con rol Comprador).
Tabla: direccion. No usa stored procedure.
"""
import re

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    campo_texto,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_texto,
    validar_token,
)

MSG_DIRECCION_REGISTRADA = "Dirección registrada correctamente"  # DFR 9.1
MSG_CP_INVALIDO = "El código postal debe tener 5 dígitos"  # DFR 9.1
MSG_LONGITUD = (  # aprobado por Ian
    "La calle no puede superar 150 caracteres, el número 20 y la colonia, "
    "la ciudad y el estado 100"
)

# Longitudes de la tabla direccion
CALLE_MAX = 150
NUMERO_MAX = 20
LUGAR_MAX = 100  # colonia, ciudad, estado_region

# Solo dígitos ASCII, igual que el CHECK ck_direccion_cp de la tabla
_RE_CP = re.compile(r"[0-9]{5}")

SQL_INSERTAR = """
    INSERT INTO direccion
        (id_usuario, calle, numero, colonia, ciudad, estado_region, codigo_postal, activa)
    VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
"""


def _codigo_postal(datos):
    """Texto del código postal; si llega como número entero se convierte a texto."""
    valor = datos.get("codigo_postal")
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor)
    return campo_texto(datos, "codigo_postal")


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    calle = campo_texto(datos, "calle")
    numero = campo_texto(datos, "numero")
    colonia = campo_texto(datos, "colonia")
    ciudad = campo_texto(datos, "ciudad")
    estado = campo_texto(datos, "estado")
    codigo_postal = _codigo_postal(datos)

    if not all((calle, numero, colonia, ciudad, estado, codigo_postal)):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    if not _RE_CP.fullmatch(codigo_postal):
        raise ErrorNegocio(400, MSG_CP_INVALIDO)

    if (
        len(calle) > CALLE_MAX
        or len(numero) > NUMERO_MAX
        or max(len(colonia), len(ciudad), len(estado)) > LUGAR_MAX
    ):
        raise ErrorNegocio(400, MSG_LONGITUD)

    validar_texto(calle, "La calle")
    validar_texto(numero, "El número", permitir_solo_numeros=True)
    validar_texto(colonia, "La colonia")
    validar_texto(ciudad, "La ciudad")
    validar_texto(estado, "El estado")

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_INSERTAR,
            (sesion["id_usuario"], calle, numero, colonia, ciudad, estado, codigo_postal),
        )
        id_direccion = cursor.lastrowid

    return ok(MSG_DIRECCION_REGISTRADA, status=201, id_direccion=id_direccion)
```

---

## lambda-consultarDirecciones: DFR 9.2 Consultar mis direcciones (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /direcciones` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body**: ninguno. El comprador sale del token.

**Orden (regla de Ian)**: primero la dirección activa más antigua (la primera que registró) y después las demás, de la más reciente a la menos reciente. Sin paginación.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "direcciones": [{"id_direccion": 2, "calle": "Av. Juárez", "numero": "120-B", "colonia": "Centro", "ciudad": "Monterrey", "estado": "Nuevo León", "codigo_postal": "64000"}, ...]}` | DFR 9.2: direcciones activas del comprador |
| 200 | `{"mensaje": "No tienes direcciones registradas", "direcciones": []}` | DFR 9.2: sin direcciones activas |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}}`

```python
"""
lambda-consultarDirecciones
DFR 9.2 Consultar mis direcciones (Comprador): solo las direcciones activas
del comprador de la sesión.
Reglas de Ian: sin paginación; primero la dirección activa más antigua y
después las demás de la más reciente a la menos reciente.
Ruta: GET /direcciones (token con rol Comprador).
Tabla: direccion. No usa stored procedure.
"""
from smavib_common import (
    ROL_COMPRADOR,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_DIRECCIONES = "No tienes direcciones registradas"  # DFR 9.2

# estado_region se devuelve como "estado", igual que el body de 9.1.
SQL_DIRECCIONES = """
    SELECT id_direccion, calle, numero, colonia, ciudad,
           estado_region AS estado, codigo_postal
    FROM direccion
    WHERE id_usuario = %s AND activa = 1
    ORDER BY id_direccion DESC
"""


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_DIRECCIONES, (sesion["id_usuario"],))
        direcciones = list(cursor.fetchall())

    if not direcciones:
        return ok(MSG_SIN_DIRECCIONES, direcciones=[])

    # Vienen de la más reciente a la más antigua; la más antigua (la última)
    # pasa al principio.
    direcciones.insert(0, direcciones.pop())
    return ok(MSG_CONSULTA, direcciones=direcciones)
```

---

## lambda-desactivarDireccion: DFR 9.3 Desactivar dirección (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PATCH /direcciones/{id}/desactivar` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body**: ninguno. La dirección se elige con `{id}` en la ruta.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Dirección desactivada correctamente", "id_direccion": 7}` | DFR 9.3: acción válida (también si ya estaba inactiva) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 9.3: la dirección es de otro usuario, o el rol no es Comprador |
| 404 | `{"error": "La dirección no existe"}` | Id inexistente o no válido (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "pathParameters": {"id": "7"}}`

```python
"""
lambda-desactivarDireccion
DFR 9.3 Desactivar dirección (Comprador): baja lógica (activa = 0). No se
borra para conservar la información de los pedidos ya generados.
Reglas aprobadas por Ian: si ya estaba inactiva responde 200 con el mismo
mensaje; dirección inexistente -> 404 "La dirección no existe".
Ruta: PATCH /direcciones/{id}/desactivar (token con rol Comprador).
Tabla: direccion. No usa stored procedure.
"""
from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_DIRECCION_DESACTIVADA = "Dirección desactivada correctamente"  # DFR 9.3
MSG_DIRECCION_NO_EXISTE = "La dirección no existe"  # aprobado por Ian

SQL_DIRECCION = "SELECT id_usuario, activa FROM direccion WHERE id_direccion = %s"
SQL_DESACTIVAR = "UPDATE direccion SET activa = 0 WHERE id_direccion = %s AND id_usuario = %s"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    id_direccion = entero_positivo(path_param(event, "id"))
    if id_direccion is None:
        raise ErrorNegocio(404, MSG_DIRECCION_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_DIRECCION, (id_direccion,))
        direccion = cursor.fetchone()
        if direccion is None:
            raise ErrorNegocio(404, MSG_DIRECCION_NO_EXISTE)

        # DFR 9.3: solo puede desactivar sus propias direcciones.
        if direccion["id_usuario"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)

        # Baja lógica (nunca DELETE). Si ya estaba inactiva no se vuelve a escribir.
        if direccion["activa"]:
            cursor.execute(SQL_DESACTIVAR, (id_direccion, sesion["id_usuario"]))

    return ok(MSG_DIRECCION_DESACTIVADA, id_direccion=id_direccion)
```

---

## lambda-crearProducto: DFR 3.1 Registrar producto (Vendedor)

Función **nueva**. La Lambda vieja `crear` (`POST /crear`) no se toca.

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /vendedor/productos` (ruta nueva) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** en la tabla de rutas de esas subredes |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB (carga boto3 y PyMySQL) |

**Body (JSON)**: los 7 primeros campos son obligatorios (DFR 3.1); `especificaciones` y `logistica_envio` son opcionales (aprobados por Ian).
```json
{"nombre": "iPhone 18 PRO MAX", "descripcion": "Smartphone de gama alta con carcasa de aluminio", "precio": "50000.00", "id_marca": 3, "id_categoria": 5, "url_imagen": "https://placehold.co/600x400", "stock": 75,
 "especificaciones": {"Material": "Aluminio"},
 "logistica_envio": {"alto": 15, "ancho": 1, "profundidad": 1, "peso_kg": "0.5", "requiere_fragil": true, "tipo_empaque": "Cartón"}}
```
- `especificaciones`: objeto nombre → texto; hasta 20; nombre de hasta 50 caracteres y valor de hasta 200. Se guarda como `Especificaciones`.
- `logistica_envio`: si se manda, sus 6 campos son obligatorios. Medidas (cm) y peso (kg) > 0 y ≤ 1000, máximo 2 decimales; `requiere_fragil` es `true`/`false`; `tipo_empaque` hasta 100 caracteres. Se guarda como `LogisticaEnvio` (`DimensionesCm`, `PesoKg`, `RequiereFragil`, `TipoEmpaque`).
- Si no se mandan (o van en `null` o `{}`), el ítem no lleva esos atributos.
- `precio`: número o texto con dígitos y hasta 2 decimales (sin letras, signos ni exponentes); mayor a 0 y menor a 100,000,000 (DECIMAL(10,2)).
- `stock`: número entero (o texto con solo dígitos), de 0 a 2,147,483,647.
- `id_marca` e `id_categoria`: los ids de `GET /marcas` y `GET /categorias`.
- `url_imagen`: `http://` o `https://`, sin espacios, máximo 500 caracteres.

**Qué guarda**
- RDS (una transacción): `producto` (estado Activo, `id_vendedor` del token) + `variante_producto` estándar con SKU `P{id_producto}-STD` y el stock inicial.
- DynamoDB (después del commit), con el estándar de Ian: `productoID`, `Nombre`, `NombreBusqueda` (minúsculas, sin acentos; para la búsqueda de 4.1), `Descripcion` (`{"Resumen": ...}`), `Precio`, `Marca`, `Categoria`, `CategoriaID`, `URLImagen`, `Stock`, `VendedorID`, `Estado`, `Variantes` (la estándar, con `Atributos` vacío) y, si se mandan, `Especificaciones` y `LogisticaEnvio`. `PutItem` con `attribute_not_exists(productoID)`: no sobrescribe un ítem que ya exista con ese id.
- Si DynamoDB falla: el producto queda Inactivo en RDS, se registra el error en CloudWatch y se responde 500.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 201 | `{"mensaje": "Producto registrado correctamente", "id_producto": 120, "sku": "P120-STD"}` | DFR 3.1: datos correctos |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | DFR 3.1: falta un campo (también un campo vacío dentro de `especificaciones` o `logistica_envio`) |
| 400 | `{"error": "El precio debe ser mayor a cero"}` | DFR 3.1: precio ≤ 0 |
| 400 | `{"error": "El precio no es válido"}` | Letras, signos, más de 2 decimales o fuera de rango (aprobado por Ian) |
| 400 | `{"error": "El stock no puede ser negativo"}` | DFR 3.1 |
| 400 | `{"error": "El stock debe ser un número entero"}` | Decimales, letras o signos (aprobado por Ian) |
| 400 | `{"error": "El stock no es válido"}` | Mayor a 2,147,483,647 (límite de INT; aprobado por Ian) |
| 400 | `{"error": "Se admiten hasta 20 especificaciones, con nombre de hasta 50 caracteres y valor de texto de hasta 200, sin nombres repetidos"}` | `especificaciones` fuera de formato (aprobado por Ian) |
| 400 | `{"error": "Las medidas y el peso deben ser mayores a cero y hasta 1000, con máximo 2 decimales; el tipo de empaque admite hasta 100 caracteres"}` | `logistica_envio` fuera de formato (aprobado por Ian) |
| 400 | `{"error": "El nombre no puede superar 200 caracteres, la descripción 1000 y la URL de imagen 500"}` | Longitud (aprobado por Ian) |
| 400 | `{"error": "La URL de imagen no es válida"}` | No es http/https o tiene espacios (aprobado por Ian) |
| 400 | `{"error": "El nombre no puede tener espacios en blanco seguidos"}` (y demás mensajes de `validar_texto`) | Regla de textos libres de Ian (nombre y descripción) |
| 400 | `{"error": "La marca no existe"}` / `{"error": "La categoría no existe"}` | DFR 3.1: deben existir (aprobados por Ian) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Vendedor |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado o falla de DynamoDB (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "body": "{\"nombre\":\"iPhone 18 PRO MAX\",\"descripcion\":\"Smartphone de gama alta\",\"precio\":\"50000.00\",\"id_marca\":3,\"id_categoria\":5,\"url_imagen\":\"https://placehold.co/600x400\",\"stock\":75}"}`

```python
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
```

---

## lambda-consultarMisProductos: DFR 3.2 Consultar mis productos (Vendedor)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /vendedor/productos?id_categoria=&estado=&q=&cursor=` (ruta nueva) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Query string** (todos opcionales y combinables, DFR 3.2)
- `id_categoria`: categoría exacta (no incluye subcategorías).
- `estado`: `Activo` o `Inactivo`, sin distinguir mayúsculas.
- `q`: palabra clave en el nombre (contiene, sin distinguir mayúsculas; `%` y `_` se buscan como texto).
- `cursor`: el `siguiente_cursor` de la página anterior. Un cursor no válido se toma como primera página.

**Fuente**: RDS (stock exacto de `variante_producto`, incluye productos Inactivos). Páginas de 20 ordenadas por `id_producto`.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "productos": [{"id_producto": 120, "nombre": "iPhone 18 PRO MAX", "precio": 50000.0, "estado": "Activo", "marca": "Apple", "id_categoria": 5, "categoria": "Celulares", "stock": 75, "variantes": 1}], "siguiente_cursor": null}` | DFR 3.2: productos del vendedor |
| 200 | `{"mensaje": "No tienes productos registrados", "productos": [], "siguiente_cursor": null}` | DFR 3.2: el vendedor no tiene ningún producto |
| 200 | `{"mensaje": "No se encontraron registros", "productos": [], "siguiente_cursor": null}` | Tiene productos, pero ninguno cumple los filtros (aprobado por Ian) |
| 400 | `{"error": "El estado seleccionado no es válido"}` | `estado` distinto de Activo/Inactivo |
| 400 | `{"error": "La categoría no existe"}` | `id_categoria` no válido o inexistente |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Vendedor |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "queryStringParameters": {"estado": "activo", "q": "iphone"}}`

```python
"""
lambda-consultarMisProductos
DFR 3.2 Consultar mis productos (Vendedor): solo los productos del vendedor
de la sesión, con filtros opcionales combinables (categoría, estado, palabra
clave en el nombre).
Fuente: RDS (stock exacto = suma de variante_producto; incluye Inactivos).
Paginación: 20 por página con cursor por id_producto.
Reglas de Ian: categoría exacta (sin subcategorías); sin productos ->
"No tienes productos registrados"; con productos pero sin coincidencias ->
"No se encontraron registros".
Ruta: GET /vendedor/productos (token con rol Vendedor).
Tablas: producto, marca, categoria, variante_producto. No usa stored procedure.
"""
from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PRODUCTOS = "No tienes productos registrados"  # DFR 3.2
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_CATEGORIA_NO_EXISTE = "La categoría no existe"  # aprobado por Ian

TAM_PAGINA = 20
ESTADOS = {"activo": "Activo", "inactivo": "Inactivo"}

SQL_EXISTE_CATEGORIA = "SELECT 1 FROM categoria WHERE id_categoria = %s"
SQL_TIENE_PRODUCTOS = "SELECT 1 FROM producto WHERE id_vendedor = %s LIMIT 1"

# Los filtros se agregan como fragmentos fijos con parámetros (%s); nunca se
# concatena texto del usuario en el SQL.
SQL_BASE = """
    SELECT p.id_producto, p.nombre, p.precio, p.estado,
           m.nombre AS marca, c.id_categoria, c.nombre AS categoria,
           COALESCE(SUM(v.stock), 0) AS stock,
           COUNT(v.id_variante) AS variantes
    FROM producto p
    JOIN marca m ON m.id_marca = p.id_marca
    JOIN categoria c ON c.id_categoria = p.id_categoria
    LEFT JOIN variante_producto v ON v.id_producto = p.id_producto
    WHERE {condiciones}
    GROUP BY p.id_producto, p.nombre, p.precio, p.estado, m.nombre, c.id_categoria, c.nombre
    ORDER BY p.id_producto
    LIMIT %s
"""


def _patron_like(texto):
    """'%texto%' con % y _ escapados (se buscan como texto, no como comodines)."""
    escapado = texto.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escapado}%"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
    id_vendedor = sesion["id_usuario"]
    filtros = query_params(event)

    condiciones = ["p.id_vendedor = %s"]
    parametros = [id_vendedor]

    cursor_pagina = entero_positivo(filtros.get("cursor"))  # no válido -> primera página
    if cursor_pagina:
        condiciones.append("p.id_producto > %s")
        parametros.append(cursor_pagina)

    estado_texto = (filtros.get("estado") or "").strip()
    if estado_texto:
        estado = ESTADOS.get(estado_texto.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("p.estado = %s")
        parametros.append(estado)

    palabra = (filtros.get("q") or "").strip()
    if palabra:
        condiciones.append("p.nombre LIKE %s ESCAPE '!'")
        parametros.append(_patron_like(palabra))

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        categoria_texto = (filtros.get("id_categoria") or "").strip()
        if categoria_texto:
            id_categoria = entero_positivo(categoria_texto)
            if id_categoria is None:
                raise ErrorNegocio(400, MSG_CATEGORIA_NO_EXISTE)
            cursor.execute(SQL_EXISTE_CATEGORIA, (id_categoria,))
            if cursor.fetchone() is None:
                raise ErrorNegocio(400, MSG_CATEGORIA_NO_EXISTE)
            condiciones.append("p.id_categoria = %s")
            parametros.append(id_categoria)

        # Se pide uno de más para saber si hay otra página.
        sql = SQL_BASE.format(condiciones=" AND ".join(condiciones))
        cursor.execute(sql, (*parametros, TAM_PAGINA + 1))
        productos = list(cursor.fetchall())

        if not productos:
            cursor.execute(SQL_TIENE_PRODUCTOS, (id_vendedor,))
            mensaje = MSG_SIN_REGISTROS if cursor.fetchone() else MSG_SIN_PRODUCTOS
            return ok(mensaje, productos=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(productos) > TAM_PAGINA:
        productos = productos[:TAM_PAGINA]
        siguiente_cursor = productos[-1]["id_producto"]

    return ok(MSG_CONSULTA, productos=productos, siguiente_cursor=siguiente_cursor)
```

---

## lambda-editarProducto: DFR 3.3 Editar producto (Vendedor)

Función **nueva**. La Lambda vieja `modificar` (`PUT /modificar/{productoID}`) no se toca.

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PUT /vendedor/productos/{id}` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB |

**Body (JSON)**: igual que la 3.1 (mismas validaciones, DFR 3.3). Es un **PUT completo**: si `especificaciones` o `logistica_envio` no vienen, se quitan del ítem.
```json
{"nombre": "iPhone 18 PRO MAX", "descripcion": "Smartphone de gama alta", "precio": "48999.90", "id_marca": 3, "id_categoria": 5, "url_imagen": "https://placehold.co/600x400", "stock": 60,
 "especificaciones": {"Material": "Aluminio"}}
```
- `stock` cambia **solo la variante estándar** `P{id}-STD`; las demás variantes se administran en 3.6 (DFR 3.3).
- Solo se editan productos **Activos** (regla de Ian).
- El precio nuevo no toca `detalle_pedido.precio_unitario` de pedidos ya generados.

**Qué guarda**
1. RDS en una transacción sin confirmar: bloquea el producto y la variante estándar (`FOR UPDATE`, así no se pisa con una compra en curso), actualiza `producto` y el stock de `P{id}-STD`.
2. DynamoDB `UpdateItem` con `attribute_exists(productoID)` (nunca crea un ítem incompleto): `Nombre`, `NombreBusqueda`, `Descripcion.Resumen` (las demás claves de `Descripcion` se conservan), `Precio`, `Marca`, `Categoria`, `CategoriaID`, `URLImagen`, `Especificaciones`, `LogisticaEnvio`, y `Variantes` y `Stock` (suma) reconstruidos desde RDS. `Estado` y `VendedorID` no cambian.
3. Si DynamoDB falla → rollback en RDS (nada cambia en ningún lado) y 500. Si no, commit.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Producto actualizado correctamente", "id_producto": 120}` | DFR 3.3: edición válida |
| 400 | Los mismos mensajes de validación de la 3.1 ("Debe completar los campos obligatorios", "El precio debe ser mayor a cero", "El stock no puede ser negativo", etc.) | DFR 3.3: mismas validaciones del registro |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 3.3: el producto es de otro vendedor, o el rol no es Vendedor |
| 404 | `{"error": "El producto no existe"}` | Id inexistente o no válido (aprobado por Ian) |
| 409 | `{"error": "El producto está inactivo y no se puede editar"}` | Producto Inactivo (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado o falla de DynamoDB (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "pathParameters": {"id": "120"}, "body": "{\"nombre\":\"iPhone 18 PRO MAX\",\"descripcion\":\"Smartphone de gama alta\",\"precio\":\"48999.90\",\"id_marca\":3,\"id_categoria\":5,\"url_imagen\":\"https://placehold.co/600x400\",\"stock\":60}"}`

```python
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
```

---

## lambda-estadoProducto: DFR 3.4 Activar / desactivar producto (Vendedor)

Función **nueva**. La Lambda vieja `eliminar` (`DELETE /eliminar/{productoID}`) no se toca.

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PATCH /vendedor/productos/{id}/estado` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB |

**Body (JSON)**
```json
{"estado": "Inactivo"}
```
- `estado`: `Activo` o `Inactivo` (obligatorio, DFR 3.4), sin distinguir mayúsculas.
- Nunca se borra el producto; solo cambia `producto.estado` y `Estado` en DynamoDB.
- Orden: RDS sin confirmar (`FOR UPDATE`) → `UpdateItem` de `Estado` con `attribute_exists(productoID)` → commit. Si DynamoDB falla → rollback y 500.
- Si el producto ya tenía ese estado → 200 con el mismo mensaje, sin escribir.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Estado del producto actualizado correctamente", "id_producto": 120, "estado": "Inactivo"}` | DFR 3.4: cambio válido (o ya tenía ese estado) |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | DFR 3.4: falta `estado` |
| 400 | `{"error": "El estado seleccionado no es válido"}` | Distinto de Activo/Inactivo |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 3.4: producto de otro vendedor, o el rol no es Vendedor |
| 404 | `{"error": "El producto no existe"}` | Id inexistente o no válido |
| 409 | `{"error": "El producto no se registró completo en el catálogo; regístralo de nuevo"}` | Activar un producto sin ítem en DynamoDB (la 3.1 falló al publicarlo) (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado o falla de DynamoDB (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "pathParameters": {"id": "120"}, "body": "{\"estado\":\"Inactivo\"}"}`

```python
"""
lambda-estadoProducto
DFR 3.4 Activar / desactivar producto (Vendedor): cambia el estado de un
producto propio en RDS y en el catálogo de DynamoDB. Nunca lo borra.
Un producto Inactivo no se muestra en 4.1 ni se puede agregar al carrito
(se aplica en 4.1 y 5.1).
Reglas aprobadas por Ian:
- Sigue el DFR: activa y desactiva (se anuló "sin reactivación").
- Orden: RDS sin confirmar -> UpdateItem en DynamoDB -> commit; si DynamoDB
  falla, rollback.
- Si ya tenía ese estado: 200 con el mismo mensaje, sin escribir.
- Activar un producto sin ítem en DynamoDB (la 3.1 falló al publicarlo) ->
  409: no se puede reconstruir porque la descripción y la URL solo vivían en
  DynamoDB.
Ruta: PATCH /vendedor/productos/{id}/estado (token con rol Vendedor). Función
nueva; la Lambda vieja "eliminar" no se toca.
Tabla: producto (+ DynamoDB). No usa stored procedure.
"""
import os

import boto3

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
    validar_token,
)

MSG_ESTADO_ACTUALIZADO = "Estado del producto actualizado correctamente"  # DFR 3.4
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_SIN_CATALOGO = (  # aprobado por Ian
    "El producto no se registró completo en el catálogo; regístralo de nuevo"
)

ESTADOS = {"activo": "Activo", "inactivo": "Inactivo"}
CONDICION_FALLIDA = "ConditionalCheckFailedException"  # el ítem no existe

SQL_PRODUCTO = "SELECT id_vendedor, estado FROM producto WHERE id_producto = %s FOR UPDATE"
SQL_ESTADO = "UPDATE producto SET estado = %s WHERE id_producto = %s"

tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _codigo_error(excepcion):
    """Código de error de boto3 (ClientError), o None si no es de DynamoDB."""
    return (getattr(excepcion, "response", None) or {}).get("Error", {}).get("Code")


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])

    id_producto = entero_positivo(path_param(event, "id"))
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    datos = leer_body(event)
    estado_texto = campo_texto(datos, "estado")
    if not estado_texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    estado = ESTADOS.get(estado_texto.lower())
    if estado is None:
        raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)

    # --- RDS sin confirmar (si algo falla, manejar_errores hace rollback) ---
    conexion = obtener_conexion()
    conexion.begin()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["id_vendedor"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)  # DFR 3.4

        if producto["estado"] == estado:
            conexion.rollback()  # nada que cambiar
            return ok(MSG_ESTADO_ACTUALIZADO, id_producto=id_producto, estado=estado)

        cursor.execute(SQL_ESTADO, (estado, id_producto))

    # --- DynamoDB antes del commit ---
    try:
        tabla_productos.update_item(
            Key={"productoID": str(id_producto)},
            UpdateExpression="SET #Estado = :estado",
            ConditionExpression="attribute_exists(productoID)",
            ExpressionAttributeNames={"#Estado": "Estado"},
            ExpressionAttributeValues={":estado": estado},
        )
    except Exception as e:
        if _codigo_error(e) == CONDICION_FALLIDA and estado == "Inactivo":
            # Sin ítem en el catálogo no hay nada que ocultar: basta con RDS.
            print(f"Producto {id_producto} sin ítem en DynamoDB; se desactiva solo en RDS")
        elif _codigo_error(e) == CONDICION_FALLIDA:
            conexion.rollback()
            raise ErrorNegocio(409, MSG_SIN_CATALOGO)
        else:
            print(f"DynamoDB falló al cambiar el estado del producto {id_producto}; rollback: {e!r}")
            conexion.rollback()
            raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    conexion.commit()
    return ok(MSG_ESTADO_ACTUALIZADO, id_producto=id_producto, estado=estado)
```

---

## lambda-registrarVariante: DFR 3.6 Registrar variantes de un producto (Vendedor)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /vendedor/productos/{id}/variantes` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB |

**Body (JSON)**
```json
{"valores": [11, 10], "stock": 20}
```
- `valores`: lista de `id_valor` de `GET /atributos` (uno o más, uno por atributo; máximo 20). DFR 3.6: se eligen del catálogo.
- `stock`: mismas validaciones que la 3.1 (entero, 0 a 2,147,483,647).
- SKU generado: `P{id}-{VALORES}` ordenados por atributo, en mayúsculas, sin espacios ni acentos (p. ej. `P123-M-ROJO`); máximo 60 caracteres.
- La variante estándar `P{id}-STD` **no se toca**: conserva su stock. El stock del producto es la suma de todas sus variantes, incluida la estándar (regla de Ian).
- Solo productos Activos. Orden: RDS sin confirmar → DynamoDB (`Variantes` y `Stock` reconstruidos desde RDS) → commit; si DynamoDB falla, rollback y 500.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 201 | `{"mensaje": "Variante registrada correctamente", "id_variante": 501, "sku": "P123-M-ROJO"}` | DFR 3.6: datos correctos |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta `valores` (o va vacío) o `stock` |
| 400 | `{"error": "El stock no puede ser negativo"}` | DFR 3.6 |
| 400 | `{"error": "El stock debe ser un número entero"}` / `{"error": "El stock no es válido"}` | Mismas validaciones de la 3.1 |
| 400 | `{"error": "Uno de los valores seleccionados no existe"}` | Id de valor inexistente o no válido (aprobado por Ian) |
| 400 | `{"error": "No puedes elegir dos valores del mismo atributo"}` | P. ej. dos tallas (aprobado por Ian) |
| 400 | `{"error": "La combinación de valores es demasiado larga; elige menos valores o valores más cortos"}` | SKU de más de 60 caracteres o más de 20 valores (aprobado por Ian) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | Producto de otro vendedor (aprobado por Ian), o el rol no es Vendedor |
| 404 | `{"error": "El producto no existe"}` | Id inexistente o no válido |
| 409 | `{"error": "La variante ya existe para este producto"}` | DFR 3.6: combinación repetida |
| 409 | `{"error": "El producto está inactivo y no se puede editar"}` | Producto Inactivo (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado o falla de DynamoDB (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "pathParameters": {"id": "123"}, "body": "{\"valores\":[11,10],\"stock\":20}"}`

```python
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
```

---

## lambda-actualizarStockMasivo: DFR 3.5 Actualizar stock de forma masiva (Vendedor)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /vendedor/stock-masivo` (ruta nueva) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"id_categoria": 5, "cantidad": 10}
```
- Ejecuta **`sp_ActualizarStockMasivo(p_id_vendedor, p_id_categoria, p_cantidad)`** (DFR 3.5). El vendedor sale del token. El SP hace la transacción completa: si algo falla, no cambia ningún stock.
- `cantidad`: entero (número o texto con solo dígitos), hasta 1,000,000 por operación. Si es ≤ 0, el mensaje lo da el SP.
- Suma a **todas** las variantes de los productos del vendedor en esa categoría, incluidos los Inactivos (el SP no filtra por estado).
- No toca DynamoDB: el `Stock` del catálogo es solo referencia; el exacto se lee de RDS.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Stock actualizado correctamente", "variantes_actualizadas": 12}` | DFR 3.5: proceso correcto |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta `id_categoria` o `cantidad` |
| 400 | `{"error": "La cantidad debe ser mayor a cero"}` | DFR 3.5 (mensaje del SP) |
| 400 | `{"error": "La cantidad debe ser un número entero"}` | Decimales, letras o signos (aprobado por Ian) |
| 400 | `{"error": "La cantidad no es válida"}` | Más de 1,000,000 (aprobado por Ian) |
| 400 | `{"error": "No se encontraron productos para actualizar"}` | DFR 3.5 (mensaje del SP); también categoría inexistente o id no válido (aprobado por Ian) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Vendedor |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "body": "{\"id_categoria\":5,\"cantidad\":10}"}`

```python
"""
lambda-actualizarStockMasivo
DFR 3.5 Actualizar stock de forma masiva (Vendedor): suma la cantidad indicada
a todas las variantes de los productos del vendedor en una categoría.
La lógica transaccional vive en sp_ActualizarStockMasivo (una sola
transacción; si falla, no cambia ningún stock). Sus errores (SQLSTATE 45000)
llegan como errno 1644 y manejar_errores los devuelve con 400 y el mensaje
exacto del SP.
Reglas aprobadas por Ian: cantidad entera, máximo 1,000,000 por operación;
categoría no válida -> mensaje del DFR "No se encontraron productos para
actualizar".
No toca DynamoDB (el Stock del catálogo es solo referencia).
Ruta: POST /vendedor/stock-masivo (token con rol Vendedor).
SP: sp_ActualizarStockMasivo(p_id_vendedor, p_id_categoria, p_cantidad).
"""
import re

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_STOCK_ACTUALIZADO = "Stock actualizado correctamente"  # DFR 3.5
MSG_SIN_PRODUCTOS = "No se encontraron productos para actualizar"  # DFR 3.5 (también lo da el SP)
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"  # aprobado por Ian
MSG_CANTIDAD_INVALIDA = "La cantidad no es válida"  # aprobado por Ian

CANTIDAD_MAX = 1000000
ID_MAX = 4294967295  # INT UNSIGNED del parámetro p_id_categoria

_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_SP = "CALL sp_ActualizarStockMasivo(%s, %s, %s)"


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _cantidad(valor):
    """Entero (número o texto con solo dígitos). Si es <= 0, el SP da el mensaje del DFR."""
    if isinstance(valor, bool):
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
    else:
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if numero > CANTIDAD_MAX:
        raise ErrorNegocio(400, MSG_CANTIDAD_INVALIDA)
    return max(numero, -1)  # cualquier valor <= 0 lo rechaza el SP


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
    datos = leer_body(event)

    if _vacio(datos.get("id_categoria")) or _vacio(datos.get("cantidad")):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    cantidad = _cantidad(datos["cantidad"])
    id_categoria = entero_positivo(datos["id_categoria"])
    if id_categoria is None or id_categoria > ID_MAX:
        raise ErrorNegocio(400, MSG_SIN_PRODUCTOS)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_SP, (sesion["id_usuario"], id_categoria, cantidad))
        fila = cursor.fetchone()  # SELECT v_actualizadas AS variantes_actualizadas
        # Consumir todos los resultados del CALL para dejar libre la conexión
        # que se reutiliza en la siguiente invocación.
        while cursor.nextset():
            pass

    actualizadas = fila["variantes_actualizadas"] if fila else 0
    return ok(MSG_STOCK_ACTUALIZADO, variantes_actualizadas=actualizadas)
```

---

## lambda-consultarProductos: DFR 4.1 Buscar y filtrar productos (abierta)

Función **nueva**. La Lambda vieja `consultar` (`GET /consultar`) no se toca.

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /productos?q=&id_categoria=&precio_min=&precio_max=&cursor=` (ruta nueva) |
| Acceso | **Abierta** (sin token): catálogo público (aprobado por Ian). Flask distinguirá en pantalla si hay sesión de Comprador |
| VPC | **No** (solo lee DynamoDB; no toca RDS) |
| Variables de entorno | TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (`smavib_common` importa PyMySQL y PyJWT al cargarse) |
| Timeout / memoria | 10 s / 256 MB (boto3) |
| Requisito | Los GSI **`EstadoPrecio`** y **`CategoriaPrecio`** creados y en estado *Activo* (instrucciones en `PROGRESO.md`) |

**Query string** (todos opcionales y combinables, DFR 4.1)
- `q`: palabra clave en el nombre (contiene; sin distinguir mayúsculas ni acentos, sobre `NombreBusqueda`). Máximo 100 caracteres.
- `id_categoria`: categoría exacta (sin subcategorías).
- `precio_min`, `precio_max`: números con hasta 2 decimales, sin signos ni letras.
- `cursor`: el `siguiente_cursor` de la página anterior. Un cursor no válido se toma como primera página.

**Cómo busca**: solo productos con `Estado = "Activo"`. Sin categoría usa `Query` sobre `EstadoPrecio`; con categoría, sobre `CategoriaPrecio`. El rango de precio va en la condición de llave (no recorre la tabla) y la palabra clave en el filtro. Páginas de 20 ordenadas por precio de menor a mayor. No muestra stock (el exacto se ve en 4.2).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "productos": [{"id_producto": 120, "nombre": "iPhone 18 PRO MAX", "precio": 50000, "marca": "Apple", "categoria": "Celulares", "id_categoria": 5, "url_imagen": "https://placehold.co/600x400"}], "siguiente_cursor": "eyJpIjoi..."}` | DFR 4.1 (`siguiente_cursor` es `null` en la última página) |
| 200 | `{"mensaje": "No se encontraron productos", "productos": [], "siguiente_cursor": null}` | DFR 4.1: sin resultados (también con una categoría no válida) |
| 400 | `{"error": "El precio mínimo no puede ser mayor al máximo"}` | DFR 4.1 |
| 400 | `{"error": "El precio no es válido"}` | Precio con letras, signos o más de 2 decimales (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"queryStringParameters": {"q": "iphone", "precio_max": "60000"}}`

```python
"""
lambda-consultarProductos
DFR 4.1 Buscar y filtrar productos: solo productos Activos, con filtros
opcionales combinables (palabra clave, categoría, precio mínimo y máximo).
Se resuelve sobre DynamoDB (DFR, Requerimientos de Eficiencia) con dos GSI:
  - EstadoPrecio    (Estado, Precio):      búsqueda sin categoría
  - CategoriaPrecio (CategoriaID, Precio): búsqueda con categoría
El rango de precio va en la condición de llave (Query, sin recorrer la tabla);
la palabra clave filtra sobre NombreBusqueda (minúsculas, sin acentos).
Paginación: 20 por página, ordenadas por precio; cursor codificado en base64.
Reglas de Ian: abierta (sin token); categoría exacta; el listado no muestra
stock (el exacto se ve en 4.2, desde RDS).
Ruta: GET /productos. No usa RDS ni stored procedures.
"""
import base64
import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation

import boto3

from smavib_common import (
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    ok,
    query_params,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PRODUCTOS = "No se encontraron productos"  # DFR 4.1
MSG_RANGO_PRECIO = "El precio mínimo no puede ser mayor al máximo"  # DFR 4.1
MSG_PRECIO_INVALIDO = "El precio no es válido"  # aprobado por Ian

TAM_PAGINA = 20
LOTE = 200  # ítems que evalúa cada Query
MAX_EVALUADOS = 2000  # tope por invocación (si se alcanza, se devuelve lo encontrado y un cursor)
Q_MAX = 100
PRECIO_MAX = Decimal("100000000")
INDICE_ESTADO = "EstadoPrecio"
INDICE_CATEGORIA = "CategoriaPrecio"

_RE_PRECIO = re.compile(r"[0-9]+(\.[0-9]{1,2})?")

NOMBRES = {
    "#Nombre": "Nombre",
    "#Precio": "Precio",
    "#Marca": "Marca",
    "#Categoria": "Categoria",
    "#CategoriaID": "CategoriaID",
    "#URLImagen": "URLImagen",
    "#Estado": "Estado",
}
PROYECCION = "productoID, " + ", ".join(NOMBRES)

tabla_productos = boto3.resource("dynamodb").Table(os.environ["TABLA_PRODUCTOS"])


def _texto_busqueda(texto):
    """'Niño Azúl' -> 'nino azul' (igual que NombreBusqueda en 3.1 y 3.3)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _precio_filtro(texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    if not _RE_PRECIO.fullmatch(texto):
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    precio = Decimal(texto)
    if precio >= PRECIO_MAX:
        raise ErrorNegocio(400, MSG_PRECIO_INVALIDO)
    return precio


# --- Cursor -----------------------------------------------------------------
def _llave(item, indice):
    """ExclusiveStartKey de un GSI: llave de la tabla + llaves del índice."""
    llave = {"productoID": item["productoID"], "Precio": item["Precio"]}
    if indice == INDICE_CATEGORIA:
        llave["CategoriaID"] = item["CategoriaID"]
    else:
        llave["Estado"] = item["Estado"]
    return llave


def _codificar_cursor(llave, indice):
    datos = {
        "i": indice,
        "p": llave["productoID"],
        "precio": str(llave["Precio"]),
        "k": str(llave.get("CategoriaID", llave.get("Estado"))),
    }
    return base64.urlsafe_b64encode(json.dumps(datos).encode("utf-8")).decode("ascii")


def _decodificar_cursor(texto, indice, id_categoria):
    """Devuelve la llave de inicio o None (primera página) si el cursor no es válido."""
    if not texto:
        return None
    try:
        datos = json.loads(base64.urlsafe_b64decode(texto.encode("ascii")))
        producto_id, precio, valor = datos["p"], Decimal(datos["precio"]), datos["k"]
        if datos["i"] != indice or not isinstance(producto_id, str) or not precio.is_finite():
            return None
        llave = {"productoID": producto_id, "Precio": precio}
        if indice == INDICE_CATEGORIA:
            if valor != str(id_categoria):
                return None
            llave["CategoriaID"] = id_categoria
        else:
            if valor != "Activo":
                return None
            llave["Estado"] = "Activo"
        return llave
    except (ValueError, TypeError, KeyError, InvalidOperation, UnicodeError):
        return None


# --- Búsqueda ---------------------------------------------------------------
def _buscar(parametros, inicio, indice):
    """Junta hasta 20 productos aunque el filtro descarte ítems en cada lote."""
    encontrados = []
    evaluados = 0
    while True:
        consulta = dict(parametros, Limit=LOTE)
        if inicio:
            consulta["ExclusiveStartKey"] = inicio
        respuesta = tabla_productos.query(**consulta)
        evaluados += respuesta.get("ScannedCount", 0)
        lote = respuesta.get("Items", [])
        ultima = respuesta.get("LastEvaluatedKey")

        faltan = TAM_PAGINA - len(encontrados)
        if len(lote) >= faltan:
            encontrados.extend(lote[:faltan])
            hay_mas = len(lote) > faltan or ultima is not None
            return encontrados, (_llave(encontrados[-1], indice) if hay_mas else None)

        encontrados.extend(lote)
        if ultima is None:
            return encontrados, None
        if evaluados >= MAX_EVALUADOS:
            return encontrados, ultima
        inicio = ultima


def _producto(item):
    producto_id = item["productoID"]
    return {
        "id_producto": int(producto_id) if producto_id.isdigit() else producto_id,
        "nombre": item.get("Nombre"),
        "precio": item.get("Precio"),
        "marca": item.get("Marca"),
        "categoria": item.get("Categoria"),
        "id_categoria": item.get("CategoriaID"),
        "url_imagen": item.get("URLImagen"),
    }


@manejar_errores
def lambda_handler(event, context):
    filtros = query_params(event)

    precio_min = _precio_filtro(filtros.get("precio_min"))
    precio_max = _precio_filtro(filtros.get("precio_max"))
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        raise ErrorNegocio(400, MSG_RANGO_PRECIO)

    palabra = _texto_busqueda((filtros.get("q") or "")[:Q_MAX])

    categoria_texto = (filtros.get("id_categoria") or "").strip()
    id_categoria = entero_positivo(categoria_texto) if categoria_texto else None
    if categoria_texto and id_categoria is None:
        return ok(MSG_SIN_PRODUCTOS, productos=[], siguiente_cursor=None)

    nombres = dict(NOMBRES)
    valores = {":activo": "Activo"}
    filtro = []
    if id_categoria:
        indice = INDICE_CATEGORIA
        llave = "#CategoriaID = :categoria"
        valores[":categoria"] = id_categoria
        filtro.append("#Estado = :activo")  # DFR 4.1: solo Activos
    else:
        indice = INDICE_ESTADO
        llave = "#Estado = :activo"  # DFR 4.1: solo Activos

    if precio_min is not None and precio_max is not None:
        llave += " AND #Precio BETWEEN :min AND :max"
        valores.update({":min": precio_min, ":max": precio_max})
    elif precio_min is not None:
        llave += " AND #Precio >= :min"
        valores[":min"] = precio_min
    elif precio_max is not None:
        llave += " AND #Precio <= :max"
        valores[":max"] = precio_max

    if palabra:
        filtro.append("contains(#NombreBusqueda, :q)")
        nombres["#NombreBusqueda"] = "NombreBusqueda"
        valores[":q"] = palabra

    parametros = {
        "IndexName": indice,
        "KeyConditionExpression": llave,
        "ProjectionExpression": PROYECCION,
        "ExpressionAttributeNames": nombres,
        "ExpressionAttributeValues": valores,
    }
    if filtro:
        parametros["FilterExpression"] = " AND ".join(filtro)

    inicio = _decodificar_cursor(filtros.get("cursor"), indice, id_categoria)
    items, siguiente = _buscar(parametros, inicio, indice)
    cursor = _codificar_cursor(siguiente, indice) if siguiente else None

    if not items and cursor is None:
        return ok(MSG_SIN_PRODUCTOS, productos=[], siguiente_cursor=None)
    return ok(MSG_CONSULTA, productos=[_producto(i) for i in items], siguiente_cursor=cursor)
```

---

## lambda-consultarProducto: DFR 4.2 Consultar detalle de producto (abierta)

Función **nueva**. La Lambda vieja `consultar/{productoID}` no se toca.

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /productos/{id}` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | **Abierta**. El token es **opcional**: con sesión válida (cualquier rol) se muestra el stock exacto; sin sesión, o con token inválido o vencido, solo la disponibilidad (regla de Ian) |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB |

**Fuentes**
- RDS (fuente de verdad): estado, nombre, precio, marca, categoría, vendedor (`usuario`) y variantes con su stock exacto.
- DynamoDB (`GetItem`): descripción (`Descripcion.Resumen` y sus claves extra), URL de imagen, especificaciones y logística de envío.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "producto": {"id_producto": 120, "nombre": "iPhone 18 PRO MAX", "descripcion": "Smartphone de gama alta", "detalles": {"Pantalla": "6.9 pulgadas"}, "precio": 50000.0, "marca": "Apple", "categoria": "Celulares", "id_categoria": 5, "url_imagen": "https://placehold.co/600x400", "vendedor": "Luis Pérez", "especificaciones": {"Material": "Aluminio"}, "logistica_envio": {...}, "disponible": true, "stock": 95, "variantes": [{"id_variante": 1, "sku": "P120-STD", "atributos": {}, "disponible": true, "stock": 75}]}}` | DFR 4.2, con sesión (cualquier rol) |
| 200 | Igual, **sin** `stock` en el producto ni en las variantes (solo `disponible`) | DFR 4.2, visitante |
| 404 | `{"error": "El producto no existe"}` | Id inexistente o no válido |
| 404 | `{"error": "Este producto ya no está disponible"}` | DFR 4.2: producto Inactivo (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"pathParameters": {"id": "120"}}` (visitante) o `{"headers": {"Authorization": "Bearer <token>"}, "pathParameters": {"id": "120"}}` (con sesión)

```python
"""
lambda-consultarProducto
DFR 4.2 Consultar detalle de producto: nombre, descripción, precio, stock
disponible, marca, categoría, imagen y vendedor. Solo productos Activos.
Reglas de Ian:
- Abierta. Token opcional: con sesión válida (cualquier rol) se muestra el
  stock exacto; visitante (o token inválido/vencido) solo ve "disponible".
- Producto Inactivo -> 404 "Este producto ya no está disponible".
Fuentes: RDS para estado, nombre, precio, marca, categoría, vendedor y stock
exacto por variante (fuente de verdad); DynamoDB para descripción, imagen,
especificaciones y logística.
Ruta: GET /productos/{id}.
Tablas: producto, marca, categoria, usuario, variante_producto,
variante_valor, valor_atributo, atributo (+ DynamoDB). No usa SP.
"""
import os

import boto3

from smavib_common import (
    MSG_ERROR_INTERNO,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_NO_DISPONIBLE = "Este producto ya no está disponible"  # aprobado por Ian

SQL_PRODUCTO = """
    SELECT p.id_producto, p.nombre, p.precio, p.estado,
           m.nombre AS marca, c.id_categoria, c.nombre AS categoria,
           u.nombre AS vendedor_nombre, u.apellido AS vendedor_apellido
    FROM producto p
    JOIN marca m ON m.id_marca = p.id_marca
    JOIN categoria c ON c.id_categoria = p.id_categoria
    JOIN usuario u ON u.id_usuario = p.id_vendedor
    WHERE p.id_producto = %s
"""
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


def _usuario_opcional(event):
    """Usuario del token si es válido; None si no hay token o no es válido (visitante)."""
    try:
        return validar_token(event)
    except ErrorNegocio:
        return None


def _variantes(filas, con_stock):
    variantes = {}
    for fila in filas:
        variante = variantes.get(fila["id_variante"])
        if variante is None:
            variante = {
                "id_variante": fila["id_variante"],
                "sku": fila["sku"],
                "atributos": {},
                "disponible": fila["stock"] > 0,
            }
            if con_stock:
                variante["stock"] = fila["stock"]
            variantes[fila["id_variante"]] = variante
        if fila["atributo"] is not None:
            variante["atributos"][fila["atributo"]] = fila["valor"]
    return list(variantes.values())


@manejar_errores
def lambda_handler(event, context):
    id_producto = entero_positivo(path_param(event, "id"))
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    con_stock = _usuario_opcional(event) is not None

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["estado"] != "Activo":  # DFR 4.2: solo Activos
            raise ErrorNegocio(404, MSG_NO_DISPONIBLE)
        cursor.execute(SQL_VARIANTES, (id_producto,))
        variantes = _variantes(cursor.fetchall(), con_stock)

    respuesta = tabla_productos.get_item(
        Key={"productoID": str(id_producto)},
        ProjectionExpression="#Descripcion, #URLImagen, #Especificaciones, #LogisticaEnvio",
        ExpressionAttributeNames={
            "#Descripcion": "Descripcion",
            "#URLImagen": "URLImagen",
            "#Especificaciones": "Especificaciones",
            "#LogisticaEnvio": "LogisticaEnvio",
        },
    )
    item = respuesta.get("Item")
    if item is None:
        # Activo en RDS pero sin ítem en el catálogo: no debería pasar.
        print(f"Producto {id_producto} Activo en RDS sin ítem en DynamoDB")
        raise ErrorNegocio(500, MSG_ERROR_INTERNO)

    descripcion = dict(item.get("Descripcion") or {})
    detalle = {
        "id_producto": producto["id_producto"],
        "nombre": producto["nombre"],
        "descripcion": descripcion.pop("Resumen", None),
        "detalles": descripcion,  # claves extra de Descripcion (p. ej. Pantalla)
        "precio": producto["precio"],
        "marca": producto["marca"],
        "categoria": producto["categoria"],
        "id_categoria": producto["id_categoria"],
        "url_imagen": item.get("URLImagen"),
        "vendedor": f"{producto['vendedor_nombre']} {producto['vendedor_apellido']}",
        "especificaciones": item.get("Especificaciones") or {},
        "logistica_envio": item.get("LogisticaEnvio"),
        "disponible": any(v["disponible"] for v in variantes),
        "variantes": variantes,
    }
    if con_stock:
        detalle["stock"] = sum(v["stock"] for v in variantes)  # DFR 3.6: suma de variantes

    return ok(MSG_CONSULTA, producto=detalle)
```

---

## lambda-agregarAlCarrito: DFR 5.1 Agregar producto al carrito (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /carrito/items` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador**. Sin sesión → 401 y Flask redirige al login (DFR 5.1) |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"id_producto": 120, "id_variante": 11, "cantidad": 2}
```
- `id_producto` y `cantidad` son obligatorios (DFR 5.1).
- `id_variante` es opcional: si se omite, se usa la variante estándar `P{id}-STD`. Si viene, debe ser de ese producto (los ids salen de `variantes` en 4.2).
- `cantidad`: entero mayor a cero. Si la variante ya está en el carrito, se **suma**, sin superar el stock de esa variante.
- El carrito vive en RDS (uno por comprador, se crea en la primera vez), así que se conserva entre sesiones.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Producto agregado al carrito", "id_variante": 11, "cantidad_en_carrito": 3}` | DFR 5.1: datos correctos (`cantidad_en_carrito` = total de esa variante en el carrito) |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta `id_producto` o `cantidad` |
| 400 | `{"error": "La cantidad debe ser mayor a cero"}` | DFR 5.1: cantidad ≤ 0 (texto de 3.5, aprobado por Ian) |
| 400 | `{"error": "La cantidad debe ser un número entero"}` | Decimales, letras o signos (aprobado por Ian) |
| 400 | `{"error": "La cantidad solicitada supera el stock disponible"}` | DFR 5.1: carrito + nueva cantidad > stock de la variante |
| 400 | `{"error": "La variante seleccionada no existe"}` | Variante inexistente o de otro producto (aprobado por Ian) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | DFR 5.1: sin sesión → Flask redirige al login |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 404 | `{"error": "El producto no existe"}` | Id inexistente o no válido |
| 409 | `{"error": "El producto iPhone 18 PRO MAX ya no está disponible"}` | DFR 5.1: producto Inactivo (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "body": "{\"id_producto\":120,\"cantidad\":2}"}`

```python
"""
lambda-agregarAlCarrito
DFR 5.1 Agregar producto al carrito (Comprador): agrega una variante con su
cantidad al carrito del comprador (en RDS, se conserva entre sesiones). Si ya
estaba, suma la cantidad sin superar el stock de esa variante.
Reglas aprobadas por Ian:
- id_variante opcional: si se omite, la variante estándar P{id}-STD.
- Producto Inactivo -> "El producto [nombre] ya no está disponible".
- Cantidad: textos de 3.5 ("mayor a cero", "número entero").
- Variante inexistente o de otro producto -> "La variante seleccionada no existe".
El carrito se bloquea (FOR UPDATE) durante la operación: un doble clic no
suma dos veces sin revisar el stock. El stock se vuelve a validar al comprar
(sp_RegistrarCompra).
Ruta: POST /carrito/items (token con rol Comprador).
Tablas: carrito, carrito_detalle, variante_producto, producto. No usa SP.
"""
import re

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_AGREGADO = "Producto agregado al carrito"  # DFR 5.1
MSG_SUPERA_STOCK = "La cantidad solicitada supera el stock disponible"  # DFR 5.1
MSG_CANTIDAD_CERO = "La cantidad debe ser mayor a cero"  # texto de 3.5 (aprobado por Ian)
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"  # aprobado por Ian
MSG_VARIANTE_NO_EXISTE = "La variante seleccionada no existe"  # aprobado por Ian
MSG_PRODUCTO_NO_EXISTE = "El producto no existe"  # aprobado por Ian
MSG_NO_DISPONIBLE = "El producto {nombre} ya no está disponible"  # aprobado por Ian

_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_CREAR_CARRITO = """
    INSERT INTO carrito (id_usuario) VALUES (%s)
    ON DUPLICATE KEY UPDATE id_usuario = id_usuario
"""
SQL_CARRITO = "SELECT id_carrito FROM carrito WHERE id_usuario = %s FOR UPDATE"
SQL_PRODUCTO = "SELECT nombre, estado FROM producto WHERE id_producto = %s"
SQL_VARIANTE = "SELECT id_variante, stock FROM variante_producto WHERE id_variante = %s AND id_producto = %s"
SQL_VARIANTE_STD = "SELECT id_variante, stock FROM variante_producto WHERE sku = %s"
SQL_EN_CARRITO = "SELECT cantidad FROM carrito_detalle WHERE id_carrito = %s AND id_variante = %s"
SQL_GUARDAR = """
    INSERT INTO carrito_detalle (id_carrito, id_variante, cantidad) VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE cantidad = %s
"""


def _vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _cantidad(valor):
    """Entero mayor a cero (número o texto con solo dígitos)."""
    if isinstance(valor, bool):
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
    else:
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if numero <= 0:
        raise ErrorNegocio(400, MSG_CANTIDAD_CERO)
    return numero


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    if _vacio(datos.get("id_producto")) or _vacio(datos.get("cantidad")):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    cantidad = _cantidad(datos["cantidad"])

    id_producto = entero_positivo(datos["id_producto"])
    if id_producto is None:
        raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)

    variante_pedida = datos.get("id_variante")
    id_variante = None
    if not _vacio(variante_pedida):
        id_variante = entero_positivo(variante_pedida)
        if id_variante is None:
            raise ErrorNegocio(400, MSG_VARIANTE_NO_EXISTE)

    id_usuario = sesion["id_usuario"]
    conexion = obtener_conexion()
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        # Carrito del comprador (se crea la primera vez) y bloqueado hasta el commit
        cursor.execute(SQL_CREAR_CARRITO, (id_usuario,))
        cursor.execute(SQL_CARRITO, (id_usuario,))
        id_carrito = cursor.fetchone()["id_carrito"]

        cursor.execute(SQL_PRODUCTO, (id_producto,))
        producto = cursor.fetchone()
        if producto is None:
            raise ErrorNegocio(404, MSG_PRODUCTO_NO_EXISTE)
        if producto["estado"] != "Activo":  # DFR 5.1: el producto debe estar activo
            raise ErrorNegocio(409, MSG_NO_DISPONIBLE.format(nombre=producto["nombre"]))

        if id_variante is None:
            cursor.execute(SQL_VARIANTE_STD, (f"P{id_producto}-STD",))
        else:
            cursor.execute(SQL_VARIANTE, (id_variante, id_producto))
        variante = cursor.fetchone()
        if variante is None:
            raise ErrorNegocio(400, MSG_VARIANTE_NO_EXISTE)

        cursor.execute(SQL_EN_CARRITO, (id_carrito, variante["id_variante"]))
        en_carrito = cursor.fetchone()
        total = (en_carrito["cantidad"] if en_carrito else 0) + cantidad

        # DFR 5.1: la suma no puede superar el stock de la variante seleccionada
        if total > variante["stock"]:
            raise ErrorNegocio(400, MSG_SUPERA_STOCK)

        cursor.execute(SQL_GUARDAR, (id_carrito, variante["id_variante"], total, total))
    conexion.commit()

    return ok(MSG_AGREGADO, id_variante=variante["id_variante"], cantidad_en_carrito=total)
```

---

## lambda-consultarCarrito: DFR 5.2 Consultar carrito (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /carrito` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** (imágenes) |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB |

**Body**: ninguno. El comprador sale del token (solo ve su propio carrito).

**Qué muestra**
- Por renglón: producto, variante (SKU y atributos), precio actual (el mismo que cobrará `sp_RegistrarCompra`), cantidad, subtotal, imagen y avisos: `disponible` (producto Activo), `stock` y `stock_suficiente`.
- Total del carrito y `puede_comprar` (todos los renglones disponibles y con stock suficiente). El SP compra todo el carrito o nada, así que Flask debe avisar antes de confirmar.
- Orden: por nombre del producto.
- Imágenes: un solo `BatchGetItem` por llave (solo los productos del carrito, solo `URLImagen`). Si DynamoDB falla, el carrito se muestra sin imágenes (`url_imagen: null`).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "items": [{"id_producto": 120, "nombre": "iPhone 18", "id_variante": 11, "sku": "P120-M-ROJO", "atributos": {"Color": "Rojo", "Talla": "M"}, "precio": 50000.0, "cantidad": 2, "subtotal": 100000.0, "url_imagen": "https://...", "disponible": true, "stock": 5, "stock_suficiente": true}], "total": 100000.0, "puede_comprar": true}` | DFR 5.2 |
| 200 | `{"mensaje": "Tu carrito está vacío", "items": [], "total": 0, "puede_comprar": false}` | DFR 5.2: carrito vacío (o sin carrito todavía) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}}`

```python
"""
lambda-consultarCarrito
DFR 5.2 Consultar carrito (Comprador): renglones del carrito del comprador de
la sesión con precio, cantidad y subtotal, y el total.
Además (para 6.1): cada renglón avisa si el producto sigue Activo y si el
stock alcanza; puede_comprar indica si sp_RegistrarCompra lo aceptaría (el SP
compra todo el carrito o nada).
Imágenes: un solo BatchGetItem por llave, solo de los productos del carrito y
solo URLImagen (bajo costo, regla de Ian). Si DynamoDB falla, se responde sin
imágenes en vez de fallar.
Ruta: GET /carrito (token con rol Comprador).
Tablas: carrito, carrito_detalle, variante_producto, producto, variante_valor,
valor_atributo, atributo (+ DynamoDB). No usa SP.
"""
import os
from decimal import Decimal

import boto3

from smavib_common import (
    ROL_COMPRADOR,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_CARRITO_VACIO = "Tu carrito está vacío"  # DFR 5.2

LOTE_DYNAMO = 100  # máximo de llaves por BatchGetItem

SQL_CARRITO = """
    SELECT cd.id_variante, cd.cantidad, v.sku, v.stock,
           p.id_producto, p.nombre, p.precio, p.estado,
           a.nombre AS atributo, va.valor
    FROM carrito c
    JOIN carrito_detalle cd ON cd.id_carrito = c.id_carrito
    JOIN variante_producto v ON v.id_variante = cd.id_variante
    JOIN producto p ON p.id_producto = v.id_producto
    LEFT JOIN variante_valor vv ON vv.id_variante = v.id_variante
    LEFT JOIN valor_atributo va ON va.id_valor = vv.id_valor
    LEFT JOIN atributo a ON a.id_atributo = va.id_atributo
    WHERE c.id_usuario = %s
    ORDER BY p.nombre, cd.id_variante, a.nombre
"""

TABLA_PRODUCTOS = os.environ["TABLA_PRODUCTOS"]
dynamodb = boto3.resource("dynamodb")


def _imagenes(ids_producto):
    """{id_producto: URLImagen} con BatchGetItem; ante cualquier falla, {}."""
    imagenes = {}
    llaves = [{"productoID": str(i)} for i in ids_producto]
    try:
        for inicio in range(0, len(llaves), LOTE_DYNAMO):
            pedido = {
                TABLA_PRODUCTOS: {
                    "Keys": llaves[inicio:inicio + LOTE_DYNAMO],
                    "ProjectionExpression": "productoID, URLImagen",
                }
            }
            for _ in range(2):  # un reintento para llaves no procesadas
                respuesta = dynamodb.batch_get_item(RequestItems=pedido)
                for item in respuesta.get("Responses", {}).get(TABLA_PRODUCTOS, []):
                    imagenes[item["productoID"]] = item.get("URLImagen")
                pedido = respuesta.get("UnprocessedKeys") or {}
                if not pedido:
                    break
    except Exception as e:
        print(f"No se pudieron leer las imágenes del carrito: {e!r}")
        return {}
    return imagenes


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CARRITO, (sesion["id_usuario"],))
        filas = cursor.fetchall()

    if not filas:
        return ok(MSG_CARRITO_VACIO, items=[], total=0, puede_comprar=False)

    # Agrupa los atributos por renglón, conservando el orden de la consulta
    renglones = {}
    for fila in filas:
        renglon = renglones.get(fila["id_variante"])
        if renglon is None:
            precio = Decimal(fila["precio"])
            renglon = {
                "id_producto": fila["id_producto"],
                "nombre": fila["nombre"],
                "id_variante": fila["id_variante"],
                "sku": fila["sku"],
                "atributos": {},
                "precio": precio,
                "cantidad": fila["cantidad"],
                "subtotal": precio * fila["cantidad"],
                "url_imagen": None,
                "disponible": fila["estado"] == "Activo",
                "stock": fila["stock"],
                "stock_suficiente": fila["cantidad"] <= fila["stock"],
            }
            renglones[fila["id_variante"]] = renglon
        if fila["atributo"] is not None:
            renglon["atributos"][fila["atributo"]] = fila["valor"]
    items = list(renglones.values())

    imagenes = _imagenes({i["id_producto"] for i in items})
    for item in items:
        item["url_imagen"] = imagenes.get(str(item["id_producto"]))

    total = sum((i["subtotal"] for i in items), Decimal("0"))
    puede_comprar = all(i["disponible"] and i["stock_suficiente"] for i in items)
    return ok(MSG_CONSULTA, items=items, total=total, puede_comprar=puede_comprar)
```

---

## lambda-modificarCantidadCarrito: DFR 5.3 Modificar cantidad en el carrito (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PUT /carrito/items/{id}` (ruta nueva; `{id}` = `id_variante` de la 5.2) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"cantidad": 3}
```
- La cantidad **reemplaza** a la actual (no se suma como en 5.1). Debe ser entera y mayor a cero (DFR 5.3).
- Si el comprador pone 0 en la pantalla, **Flask llama a la 5.4** (eliminar) en vez de a esta función (acuerdo con Ian, respetando el DFR).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Carrito actualizado correctamente", "id_variante": 11, "cantidad": 3, "subtotal": 301.5}` | DFR 5.3: modificación válida |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta `cantidad` |
| 400 | `{"error": "La cantidad debe ser mayor a cero"}` | DFR 5.3: cantidad ≤ 0 |
| 400 | `{"error": "La cantidad debe ser un número entero"}` | Decimales, letras o signos |
| 400 | `{"error": "La cantidad solicitada supera el stock disponible"}` | DFR 5.3 |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 404 | `{"error": "El producto no está en tu carrito"}` | La variante no está en el carrito del comprador (ajena, inexistente o id no válido) (aprobado por Ian) |
| 409 | `{"error": "El producto iPhone 18 ya no está disponible"}` | Producto Inactivo: hay que quitarlo con 5.4 (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "pathParameters": {"id": "11"}, "body": "{\"cantidad\":3}"}`

```python
"""
lambda-modificarCantidadCarrito
DFR 5.3 Modificar cantidad en el carrito (Comprador): reemplaza la cantidad de
una variante del carrito del comprador, sin superar su stock.
Reglas aprobadas por Ian:
- Variante que no está en su carrito -> 404 "El producto no está en tu carrito".
- Producto Inactivo -> 409 "El producto [nombre] ya no está disponible"
  (se quita con 5.4).
- Cantidad 0: la Lambda la rechaza (DFR: "mayor a cero"); la pantalla de
  Flask llama a 5.4 para quitar el producto.
El carrito se bloquea (FOR UPDATE) durante la operación, igual que en 5.1.
Ruta: PUT /carrito/items/{id} ({id} = id_variante) (token con rol Comprador).
Tablas: carrito, carrito_detalle, variante_producto, producto. No usa SP.
"""
import re
from decimal import Decimal

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_ACTUALIZADO = "Carrito actualizado correctamente"  # DFR 5.3
MSG_SUPERA_STOCK = "La cantidad solicitada supera el stock disponible"  # DFR 5.3
MSG_CANTIDAD_CERO = "La cantidad debe ser mayor a cero"  # texto de 3.5 (aprobado por Ian)
MSG_CANTIDAD_ENTERA = "La cantidad debe ser un número entero"  # aprobado por Ian
MSG_NO_EN_CARRITO = "El producto no está en tu carrito"  # aprobado por Ian
MSG_NO_DISPONIBLE = "El producto {nombre} ya no está disponible"  # aprobado por Ian

_RE_ENTERO = re.compile(r"-?[0-9]+")

SQL_CARRITO = "SELECT id_carrito FROM carrito WHERE id_usuario = %s FOR UPDATE"
SQL_RENGLON = """
    SELECT cd.cantidad, v.stock, p.nombre, p.estado, p.precio
    FROM carrito_detalle cd
    JOIN variante_producto v ON v.id_variante = cd.id_variante
    JOIN producto p ON p.id_producto = v.id_producto
    WHERE cd.id_carrito = %s AND cd.id_variante = %s
"""
SQL_ACTUALIZAR = "UPDATE carrito_detalle SET cantidad = %s WHERE id_carrito = %s AND id_variante = %s"


def _cantidad(valor):
    """Entero mayor a cero (número o texto con solo dígitos), igual que 5.1."""
    if isinstance(valor, bool):
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str) and _RE_ENTERO.fullmatch(valor.strip()):
        numero = int(valor.strip())
    else:
        raise ErrorNegocio(400, MSG_CANTIDAD_ENTERA)
    if numero <= 0:
        raise ErrorNegocio(400, MSG_CANTIDAD_CERO)
    return numero


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])

    id_variante = entero_positivo(path_param(event, "id"))
    if id_variante is None:
        raise ErrorNegocio(404, MSG_NO_EN_CARRITO)

    datos = leer_body(event)
    valor = datos.get("cantidad")
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    cantidad = _cantidad(valor)

    conexion = obtener_conexion()
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CARRITO, (sesion["id_usuario"],))
        carrito = cursor.fetchone()
        if carrito is None:
            raise ErrorNegocio(404, MSG_NO_EN_CARRITO)

        # Solo renglones del carrito del comprador: uno ajeno simplemente no aparece
        cursor.execute(SQL_RENGLON, (carrito["id_carrito"], id_variante))
        renglon = cursor.fetchone()
        if renglon is None:
            raise ErrorNegocio(404, MSG_NO_EN_CARRITO)
        if renglon["estado"] != "Activo":
            raise ErrorNegocio(409, MSG_NO_DISPONIBLE.format(nombre=renglon["nombre"]))
        if cantidad > renglon["stock"]:  # DFR 5.3
            raise ErrorNegocio(400, MSG_SUPERA_STOCK)

        cursor.execute(SQL_ACTUALIZAR, (cantidad, carrito["id_carrito"], id_variante))
    conexion.commit()

    subtotal = Decimal(renglon["precio"]) * cantidad
    return ok(MSG_ACTUALIZADO, id_variante=id_variante, cantidad=cantidad, subtotal=subtotal)
```

---

## lambda-eliminarDelCarrito: DFR 5.4 Eliminar producto del carrito (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `DELETE /carrito/items` (ruta nueva; lleva body JSON) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"variantes": [10, 11]}
```
- Lista de `id_variante` de la 5.2: uno o varios (DFR 5.4). Los repetidos se cuentan una vez.
- Borrado físico de renglones de `carrito_detalle` (la regla de bajas lógicas no aplica al carrito; `sp_RegistrarCompra` también los borra).
- Se quitan los que sí están en el carrito del comprador; solo si **ninguno** estaba → 404 (regla de Ian: una lista con ids ya borrados no da error). Un doble clic sobre **un solo** producto sí da 404 en la segunda petición: Flask debe desactivar el botón mientras la petición está en curso.
- Desde Flask: `requests.delete(url, json={"variantes": [...]}, headers=...)`.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Producto/s eliminado/s del carrito", "eliminados": 2}` | DFR 5.4 (texto exacto) |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta `variantes` o va vacía |
| 400 | `{"error": "La variante seleccionada no existe"}` | Un id no válido (texto, negativo, etc.) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 404 | `{"error": "El producto no está en tu carrito"}` | Ninguno de los ids estaba en su carrito |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "body": "{\"variantes\":[10,11]}"}`

```python
"""
lambda-eliminarDelCarrito
DFR 5.4 Eliminar producto del carrito (Comprador): quita uno o varios
renglones del carrito del comprador de la sesión.
Reglas aprobadas por Ian: se quitan los que sí están; 404 solo si ninguno
estaba (una lista con ids ya borrados no da error, y una lista de ids ajenos
no revela nada). Flask desactiva el botón durante la petición para evitar el
404 de un doble clic sobre un solo producto. Borrado físico: la regla de bajas lógicas no aplica a
renglones del carrito.
Los ids se procesan en bloques de 100 dentro de una sola transacción.
Ruta: DELETE /carrito/items (token con rol Comprador).
Tablas: carrito, carrito_detalle. No usa SP.
"""
from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_ELIMINADOS = "Producto/s eliminado/s del carrito"  # DFR 5.4 (texto exacto)
MSG_VARIANTE_NO_EXISTE = "La variante seleccionada no existe"  # aprobado por Ian
MSG_NO_EN_CARRITO = "El producto no está en tu carrito"  # aprobado por Ian

BLOQUE = 100

SQL_CARRITO = "SELECT id_carrito FROM carrito WHERE id_usuario = %s"
SQL_ELIMINAR = "DELETE FROM carrito_detalle WHERE id_carrito = %s AND id_variante IN ({marcas})"


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    lista = datos.get("variantes")
    if not isinstance(lista, list) or not lista:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    ids = [entero_positivo(v) for v in lista]
    if None in ids:
        raise ErrorNegocio(400, MSG_VARIANTE_NO_EXISTE)
    ids = list(dict.fromkeys(ids))  # sin repetidos, conservando el orden

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CARRITO, (sesion["id_usuario"],))
        carrito = cursor.fetchone()
    if carrito is None:
        raise ErrorNegocio(404, MSG_NO_EN_CARRITO)

    eliminados = 0
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        for inicio in range(0, len(ids), BLOQUE):
            bloque = ids[inicio:inicio + BLOQUE]
            sql = SQL_ELIMINAR.format(marcas=", ".join(["%s"] * len(bloque)))
            # Solo filas del carrito del comprador: los ids ajenos no borran nada
            cursor.execute(sql, (carrito["id_carrito"], *bloque))
            eliminados += cursor.rowcount
    conexion.commit()

    if eliminados == 0:
        raise ErrorNegocio(404, MSG_NO_EN_CARRITO)
    return ok(MSG_ELIMINADOS, eliminados=eliminados)
```

---

## lambda-confirmarCompra: DFR 6.1 Confirmar compra (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `POST /compras` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |
| **API Gateway** | **No activar el registro completo de peticiones/respuestas** (*full request/response logging* / *data trace*) en esta ruta: guardaría el número de tarjeta en CloudWatch. El registro de errores normal sí puede quedar |

**Body (JSON)**
```json
{"id_direccion": 7, "numero_tarjeta": "4242 4242 4242 4242", "cvv": "123"}
```
- `numero_tarjeta`: solo dígitos, espacios y guiones (regla de Ian); sin espacios ni guiones debe quedar en **16 dígitos** (DFR 6.1). Letras, puntos, comas o signos → "Datos de pago no válidos".
- `cvv`: exactamente **3 dígitos** (DFR 6.1).
- **Pago tokenizado:** la Lambda genera un token aleatorio (`tok_` + 32 hexadecimales, no derivado de la tarjeta) y al SP solo le pasa el token y los últimos 4 dígitos. El número completo y el CVV **nunca** se guardan ni se imprimen.
- Ejecuta **`sp_RegistrarCompra(p_id_usuario, p_id_direccion, p_token, p_ultimos4, @p_id_pedido)`**: pedido Pendiente, detalle con precio histórico, descuento de stock, pago Aprobado y carrito vacío, todo en una transacción (DFR 6.1).
- Doble clic: el SP bloquea el carrito; la segunda petición recibe "Tu carrito está vacío". Flask debe desactivar el botón de pagar mientras la petición está en curso.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 201 | `{"mensaje": "Compra realizada correctamente", "id_pedido": 345, "total": 100000.0}` | DFR 6.1: número de orden |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | DFR 6.1: falta un campo |
| 400 | `{"error": "Datos de pago no válidos"}` | DFR 6.1: tarjeta o CVV con formato inválido |
| 400 | `{"error": "Tu carrito está vacío"}` | DFR 6.1 (mensaje del SP) |
| 400 | `{"error": "La dirección de envío no es válida"}` | DFR 6.1 (mensaje del SP; también id no válido) |
| 400 | `{"error": "Stock insuficiente para el producto iPhone 18"}` | DFR 6.1 (mensaje del SP) |
| 400 | `{"error": "El producto iPhone 18 ya no está disponible"}` | DFR 6.1 (mensaje del SP) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch, sin datos de la tarjeta) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "body": "{\"id_direccion\":7,\"numero_tarjeta\":\"4242 4242 4242 4242\",\"cvv\":\"123\"}"}`

```python
"""
lambda-confirmarCompra
DFR 6.1 Confirmar compra (Comprador): convierte el carrito en un pedido con
pago simulado. La transacción completa vive en sp_RegistrarCompra; sus
errores (SQLSTATE 45000) llegan como errno 1644 y manejar_errores los
devuelve con 400 y el mensaje exacto.
Pago tokenizado (CLAUDE.md, regla 4): se valida la tarjeta (16 dígitos) y el
CVV (3 dígitos); al SP solo llegan un token aleatorio y los últimos 4
dígitos. El número completo y el CVV nunca se guardan ni se imprimen.
Regla de Ian: la tarjeta admite solo dígitos, espacios y guiones.
Ruta: POST /compras (token con rol Comprador).
SP: sp_RegistrarCompra(p_id_usuario, p_id_direccion, p_token, p_ultimos4, OUT p_id_pedido).
"""
import re
import secrets

from smavib_common import (
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    leer_body,
    manejar_errores,
    obtener_conexion,
    ok,
    validar_token,
)

MSG_COMPRA_REALIZADA = "Compra realizada correctamente"  # DFR 6.1
MSG_PAGO_INVALIDO = "Datos de pago no válidos"  # DFR 6.1 (también lo da el SP)
MSG_DIRECCION_INVALIDA = "La dirección de envío no es válida"  # DFR 6.1 (también lo da el SP)

ID_MAX = 4294967295  # INT UNSIGNED de p_id_direccion

# Solo dígitos ASCII, espacios y guiones (regla de Ian)
_RE_TARJETA_PERMITIDA = re.compile(r"[0-9 \-]+")
_RE_16_DIGITOS = re.compile(r"[0-9]{16}")
_RE_CVV = re.compile(r"[0-9]{3}")

SQL_LIMPIAR_OUT = "SET @p_id_pedido = NULL"
SQL_SP = "CALL sp_RegistrarCompra(%s, %s, %s, %s, @p_id_pedido)"
SQL_LEER_OUT = "SELECT @p_id_pedido AS id_pedido"
SQL_TOTAL = "SELECT total FROM pedido WHERE id_pedido = %s AND id_usuario = %s"


def _texto(valor):
    """Texto del campo; un número entero del JSON se toma como texto."""
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, int):
        return str(valor)
    return valor.strip() if isinstance(valor, str) else ""


def _ultimos4(numero_tarjeta, cvv):
    """Valida tarjeta y CVV y devuelve solo los últimos 4 dígitos."""
    if not _RE_TARJETA_PERMITIDA.fullmatch(numero_tarjeta):
        raise ErrorNegocio(400, MSG_PAGO_INVALIDO)
    digitos = numero_tarjeta.replace(" ", "").replace("-", "")
    if not _RE_16_DIGITOS.fullmatch(digitos) or not _RE_CVV.fullmatch(cvv):
        raise ErrorNegocio(400, MSG_PAGO_INVALIDO)
    return digitos[-4:]


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    datos = leer_body(event)

    direccion_texto = _texto(datos.get("id_direccion"))
    numero_tarjeta = _texto(datos.get("numero_tarjeta"))
    cvv = _texto(datos.get("cvv"))
    if not direccion_texto or not numero_tarjeta or not cvv:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)

    ultimos4 = _ultimos4(numero_tarjeta, cvv)
    del numero_tarjeta, cvv, datos  # el número completo y el CVV no se usan más

    id_direccion = entero_positivo(direccion_texto)
    if id_direccion is None or id_direccion > ID_MAX:
        raise ErrorNegocio(400, MSG_DIRECCION_INVALIDA)

    token_pago = "tok_" + secrets.token_hex(16)  # aleatorio: no se deriva de la tarjeta

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_LIMPIAR_OUT)
        cursor.execute(SQL_SP, (sesion["id_usuario"], id_direccion, token_pago, ultimos4))
        while cursor.nextset():  # deja libre la conexión que se reutiliza
            pass
        cursor.execute(SQL_LEER_OUT)
        id_pedido = cursor.fetchone()["id_pedido"]
        if id_pedido is None:
            raise RuntimeError("sp_RegistrarCompra terminó sin número de pedido")
        cursor.execute(SQL_TOTAL, (id_pedido, sesion["id_usuario"]))
        pedido = cursor.fetchone()

    return ok(
        MSG_COMPRA_REALIZADA,
        status=201,
        id_pedido=id_pedido,
        total=pedido["total"] if pedido else None,
    )
```

---

## lambda-consultarMisPedidos: DFR 7.1 Consultar mis pedidos (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /pedidos?estado=&fecha=&cursor=` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Query string** (opcionales y combinables, DFR 7.1)
- `estado`: Pendiente, Enviado, Entregado, Cancelado o Devuelto (sin distinguir mayúsculas).
- `fecha`: un día en formato `AAAA-MM-DD`, **en hora de México**.
- `cursor`: el `siguiente_cursor` de la página anterior (no válido → primera página).

**Fechas (opción A de Ian):** las fechas se guardan en hora de México (la conexión de `smavib_common` usa `time_zone = '-06:00'`). El día que escribe el comprador se busca tal cual y la fecha se devuelve con `-06:00`. El comprador ve y busca la misma fecha.

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "pedidos": [{"id_pedido": 345, "fecha": "2026-11-14T19:05:00-06:00", "total": 100000.0, "estado": "Pendiente"}], "siguiente_cursor": null}` | DFR 7.1: del más reciente al más antiguo, 20 por página |
| 200 | `{"mensaje": "No tienes pedidos registrados", "pedidos": [], "siguiente_cursor": null}` | DFR 7.1: el comprador nunca ha comprado |
| 200 | `{"mensaje": "No se encontraron registros", "pedidos": [], "siguiente_cursor": null}` | Tiene pedidos, pero ninguno cumple los filtros |
| 400 | `{"error": "El estado seleccionado no es válido"}` | Estado fuera de los 5 (aprobado por Ian) |
| 400 | `{"error": "La fecha no es válida"}` | Fecha mal escrita (aprobado por Ian) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "queryStringParameters": {"estado": "pendiente", "fecha": "2026-11-14"}}`

```python
"""
lambda-consultarMisPedidos
DFR 7.1 Consultar mis pedidos (Comprador): ID de orden, fecha, total y estado
de los pedidos del comprador de la sesión, con filtros opcionales por estado y
fecha.
Paginación: 20 por página, del más reciente al más antiguo, con cursor por
id_pedido (WHERE id_pedido < cursor ORDER BY id_pedido DESC).
Fechas (opción A de Ian): se guardan en hora de México (la conexión usa
time_zone = '-06:00'); el día se filtra tal cual y se devuelve con -06:00.
Ruta: GET /pedidos (token con rol Comprador).
Tablas: pedido, estado_pedido. No usa SP.
"""
import datetime
import re

from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PEDIDOS = "No tienes pedidos registrados"  # DFR 7.1
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

TAM_PAGINA = 20
ESTADOS = {e.lower(): e for e in ("Pendiente", "Enviado", "Entregado", "Cancelado", "Devuelto")}
# Hora de México (Ciudad de México): UTC-6 fijo, sin horario de verano desde 2022
ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # para la etiqueta -06:00

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_TIENE_PEDIDOS = "SELECT 1 FROM pedido WHERE id_usuario = %s LIMIT 1"
SQL_BASE = """
    SELECT p.id_pedido, p.fecha, p.total, e.nombre AS estado
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    WHERE {condiciones}
    ORDER BY p.id_pedido DESC
    LIMIT %s
"""


def _rango_dia(texto):
    """'2026-11-14' -> (inicio, fin) del día; las fechas ya están en hora de México."""
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        dia = datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    inicio = datetime.datetime.combine(dia, datetime.time.min)
    return inicio, inicio + datetime.timedelta(days=1)


def _fecha_mexico(fecha):
    """datetime de RDS (ya en hora de México, sin zona) -> texto ISO con -06:00."""
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    id_usuario = sesion["id_usuario"]
    filtros = query_params(event)

    condiciones = ["p.id_usuario = %s"]
    parametros = [id_usuario]

    cursor_pagina = entero_positivo(filtros.get("cursor"))  # no válido -> primera página
    if cursor_pagina:
        condiciones.append("p.id_pedido < %s")
        parametros.append(cursor_pagina)

    estado_texto = (filtros.get("estado") or "").strip()
    if estado_texto:
        estado = ESTADOS.get(estado_texto.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("e.nombre = %s")
        parametros.append(estado)

    fecha_texto = (filtros.get("fecha") or "").strip()
    if fecha_texto:
        inicio, fin = _rango_dia(fecha_texto)
        condiciones.append("p.fecha >= %s AND p.fecha < %s")
        parametros.extend([inicio, fin])

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        sql = SQL_BASE.format(condiciones=" AND ".join(condiciones))
        cursor.execute(sql, (*parametros, TAM_PAGINA + 1))
        pedidos = list(cursor.fetchall())

        if not pedidos:
            cursor.execute(SQL_TIENE_PEDIDOS, (id_usuario,))
            mensaje = MSG_SIN_REGISTROS if cursor.fetchone() else MSG_SIN_PEDIDOS
            return ok(mensaje, pedidos=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(pedidos) > TAM_PAGINA:
        pedidos = pedidos[:TAM_PAGINA]
        siguiente_cursor = pedidos[-1]["id_pedido"]

    for pedido in pedidos:
        pedido["fecha"] = _fecha_mexico(pedido["fecha"])
    return ok(MSG_CONSULTA, pedidos=pedidos, siguiente_cursor=siguiente_cursor)
```

---

## lambda-consultarDetallePedido: DFR 7.2 Consultar detalle de pedido (Comprador y Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /pedidos/{id}` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Comprador** (solo sus pedidos) o **Administrador** (todos, con datos reducidos) |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** (imágenes) |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | 10 s / 256 MB |

**Qué ve cada rol (reglas de Ian)**
| Dato | Comprador (dueño) | Administrador |
|---|---|---|
| Productos, cantidad, precio unitario histórico, subtotal, total, fecha, estado | Sí | Sí |
| Dirección de envío | Completa | Solo ciudad, estado y código postal |
| Pago | Últimos 4 dígitos y estado del pago | **No** |
| Nombre del comprador | — | Sí (sin correo) |

- El precio de cada renglón es `detalle_pedido.precio_unitario` (el de la compra, DFR 7.2), no el precio actual. El token de pago nunca se devuelve.
- Fecha en hora de México (se guarda así; se devuelve con `-06:00`), igual que 7.1. Imágenes con un solo `BatchGetItem` (si DynamoDB falla, sin imágenes).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "pedido": {"id_pedido": 345, "fecha": "2026-11-14T19:05:00-06:00", "estado": "Pendiente", "total": 100000.0, "direccion": {"calle": "Av. Juárez", "numero": "120-B", "colonia": "Centro", "ciudad": "Monterrey", "estado": "Nuevo León", "codigo_postal": "64000"}, "pago": {"ultimos4": "4242", "estado": "Aprobado"}, "productos": [{"id_producto": 120, "nombre": "iPhone 18", "id_variante": 11, "sku": "P120-M-ROJO", "atributos": {"Color": "Rojo", "Talla": "M"}, "cantidad": 2, "precio_unitario": 50000.0, "subtotal": 100000.0, "url_imagen": "https://..."}]}}` | DFR 7.2, comprador dueño |
| 200 | Igual, con `"comprador": "Ana López"`, `"direccion": {"ciudad", "estado", "codigo_postal"}` y **sin** `pago` | Administrador |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | Pedido de otro comprador, o rol Vendedor (aprobado por Ian) |
| 404 | `{"error": "El pedido no existe"}` | Id inexistente o no válido (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador o admin>"}, "pathParameters": {"id": "345"}}`

```python
"""
lambda-consultarDetallePedido
DFR 7.2 Consultar detalle de pedido: cada producto con cantidad, precio
unitario histórico (detalle_pedido.precio_unitario) y subtotal, y el total.
Reglas de Ian:
- Comprador: solo sus pedidos (otro -> 403 "Acceso restringido"); ve la
  dirección completa y el pago (últimos 4 dígitos y estado).
- Administrador: cualquier pedido, con datos reducidos: nombre del comprador,
  dirección solo con ciudad, estado y código postal, y sin datos de pago.
- Inexistente o id no válido -> 404 "El pedido no existe".
El token de pago nunca se devuelve. Fecha guardada en hora de México (se devuelve con -06:00).
Imágenes: un solo BatchGetItem de bajo costo; si DynamoDB falla, sin imágenes.
Ruta: GET /pedidos/{id} (token Comprador o Administrador).
Tablas: pedido, estado_pedido, usuario, direccion, pago, detalle_pedido,
variante_producto, producto, variante_valor, valor_atributo, atributo (+ DynamoDB).
"""
import datetime
import os
from decimal import Decimal

import boto3

from smavib_common import (
    MSG_ACCESO_RESTRINGIDO,
    ROL_ADMINISTRADOR,
    ROL_COMPRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    path_param,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_PEDIDO_NO_EXISTE = "El pedido no existe"  # aprobado por Ian

ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # UTC-6 fijo
LOTE_DYNAMO = 100

SQL_PEDIDO = """
    SELECT p.id_pedido, p.id_usuario, p.fecha, p.total, e.nombre AS estado,
           u.nombre AS comprador_nombre, u.apellido AS comprador_apellido,
           d.calle, d.numero, d.colonia, d.ciudad, d.estado_region, d.codigo_postal,
           pg.ultimos4, pg.estado AS estado_pago
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    JOIN usuario u ON u.id_usuario = p.id_usuario
    LEFT JOIN direccion d ON d.id_direccion = p.id_direccion
    LEFT JOIN pago pg ON pg.id_pedido = p.id_pedido
    WHERE p.id_pedido = %s
"""
SQL_PRODUCTOS = """
    SELECT dp.id_detalle, dp.id_variante, dp.cantidad, dp.precio_unitario, v.sku,
           pr.id_producto, pr.nombre, a.nombre AS atributo, va.valor
    FROM detalle_pedido dp
    JOIN variante_producto v ON v.id_variante = dp.id_variante
    JOIN producto pr ON pr.id_producto = v.id_producto
    LEFT JOIN variante_valor vv ON vv.id_variante = v.id_variante
    LEFT JOIN valor_atributo va ON va.id_valor = vv.id_valor
    LEFT JOIN atributo a ON a.id_atributo = va.id_atributo
    WHERE dp.id_pedido = %s
    ORDER BY dp.id_detalle, a.nombre
"""

TABLA_PRODUCTOS = os.environ["TABLA_PRODUCTOS"]
dynamodb = boto3.resource("dynamodb")


def _fecha_mexico(fecha):
    """datetime de RDS (ya en hora de México, sin zona) -> texto ISO con -06:00."""
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


def _imagenes(ids_producto):
    """{id_producto: URLImagen} con BatchGetItem (igual que 5.2); ante falla, {}."""
    imagenes = {}
    llaves = [{"productoID": str(i)} for i in ids_producto]
    try:
        for inicio in range(0, len(llaves), LOTE_DYNAMO):
            pedido = {
                TABLA_PRODUCTOS: {
                    "Keys": llaves[inicio:inicio + LOTE_DYNAMO],
                    "ProjectionExpression": "productoID, URLImagen",
                }
            }
            for _ in range(2):  # un reintento para llaves no procesadas
                respuesta = dynamodb.batch_get_item(RequestItems=pedido)
                for item in respuesta.get("Responses", {}).get(TABLA_PRODUCTOS, []):
                    imagenes[item["productoID"]] = item.get("URLImagen")
                pedido = respuesta.get("UnprocessedKeys") or {}
                if not pedido:
                    break
    except Exception as e:
        print(f"No se pudieron leer las imágenes del pedido: {e!r}")
        return {}
    return imagenes


def _productos(filas):
    productos = {}
    for fila in filas:
        producto = productos.get(fila["id_detalle"])
        if producto is None:
            precio = Decimal(fila["precio_unitario"])
            producto = {
                "id_producto": fila["id_producto"],
                "nombre": fila["nombre"],
                "id_variante": fila["id_variante"],
                "sku": fila["sku"],
                "atributos": {},
                "cantidad": fila["cantidad"],
                "precio_unitario": precio,  # DFR 7.2: precio histórico
                "subtotal": precio * fila["cantidad"],
                "url_imagen": None,
            }
            productos[fila["id_detalle"]] = producto
        if fila["atributo"] is not None:
            producto["atributos"][fila["atributo"]] = fila["valor"]
    return list(productos.values())


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR, ROL_ADMINISTRADOR])
    es_admin = sesion["rol"] == ROL_ADMINISTRADOR

    id_pedido = entero_positivo(path_param(event, "id"))
    if id_pedido is None:
        raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_PEDIDO, (id_pedido,))
        cabecera = cursor.fetchone()
        if cabecera is None:
            raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)
        if not es_admin and cabecera["id_usuario"] != sesion["id_usuario"]:
            raise ErrorNegocio(403, MSG_ACCESO_RESTRINGIDO)  # DFR 7.2: solo sus pedidos
        cursor.execute(SQL_PRODUCTOS, (id_pedido,))
        productos = _productos(cursor.fetchall())

    imagenes = _imagenes({p["id_producto"] for p in productos})
    for producto in productos:
        producto["url_imagen"] = imagenes.get(str(producto["id_producto"]))

    detalle = {
        "id_pedido": cabecera["id_pedido"],
        "fecha": _fecha_mexico(cabecera["fecha"]),
        "estado": cabecera["estado"],
        "total": cabecera["total"],
        "productos": productos,
    }

    tiene_direccion = cabecera["ciudad"] is not None
    if es_admin:
        # Datos reducidos (regla de Ian): sin pago y sin calle, número ni colonia
        detalle["comprador"] = f"{cabecera['comprador_nombre']} {cabecera['comprador_apellido']}"
        detalle["direccion"] = {
            "ciudad": cabecera["ciudad"],
            "estado": cabecera["estado_region"],
            "codigo_postal": cabecera["codigo_postal"],
        } if tiene_direccion else None
    else:
        detalle["direccion"] = {
            "calle": cabecera["calle"],
            "numero": cabecera["numero"],
            "colonia": cabecera["colonia"],
            "ciudad": cabecera["ciudad"],
            "estado": cabecera["estado_region"],
            "codigo_postal": cabecera["codigo_postal"],
        } if tiene_direccion else None
        detalle["pago"] = {
            "ultimos4": cabecera["ultimos4"],
            "estado": cabecera["estado_pago"],
        } if cabecera["ultimos4"] else None

    return ok(MSG_CONSULTA, pedido=detalle)
```

---

## lambda-consultarPedidosAdmin: A3 Consultar pedidos (Administrador, apoyo)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /admin/pedidos?estado=&fecha=&cursor=` (ruta nueva) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Query string** (opcionales y combinables, igual que 7.1)
- `estado`: Pendiente, Enviado, Entregado, Cancelado o Devuelto (sin distinguir mayúsculas). **Flask abre la pantalla con `estado=Pendiente`** (regla de Ian); la Lambda sin filtro devuelve todos.
- `fecha`: un día `AAAA-MM-DD` en hora de México (las fechas se guardan así).
- `cursor`: el `siguiente_cursor` de la página anterior (no válido → primera página).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "pedidos": [{"id_pedido": 345, "fecha": "2026-11-14T19:05:00-06:00", "total": 100000.0, "estado": "Pendiente", "comprador": "Ana López"}], "siguiente_cursor": null}` | Del más reciente al más antiguo, 20 por página (sin dirección ni pago: eso está en 7.2) |
| 200 | `{"mensaje": "No se encontraron registros", "pedidos": [], "siguiente_cursor": null}` | Sin resultados |
| 400 | `{"error": "El estado seleccionado no es válido"}` | Estado fuera de los 5 |
| 400 | `{"error": "La fecha no es válida"}` | Fecha mal escrita |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Administrador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "queryStringParameters": {"estado": "Pendiente"}}`

```python
"""
lambda-consultarPedidosAdmin
A3 (endpoint de apoyo aprobado por Ian, no está en el DFR): lista todos los
pedidos para que el administrador elija cuál actualizar con 7.3.
Filtros opcionales: estado y fecha (día en hora de México; las fechas se
guardan así), igual que 7.1. Flask abre la pantalla con estado=Pendiente (regla de Ian).
Muestra ID de orden, fecha (hora de México), total, estado y nombre del
comprador; sin dirección ni pago (eso está en 7.2 con datos reducidos).
Paginación: 20 por página, del más reciente al más antiguo (cursor id_pedido).
Ruta: GET /admin/pedidos (token con rol Administrador).
Tablas: pedido, estado_pedido, usuario. No usa SP.
"""
import datetime
import re

from smavib_common import (
    MSG_SIN_REGISTROS,
    ROL_ADMINISTRADOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

TAM_PAGINA = 20
ESTADOS = {e.lower(): e for e in ("Pendiente", "Enviado", "Entregado", "Cancelado", "Devuelto")}
ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # UTC-6 fijo

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_BASE = """
    SELECT p.id_pedido, p.fecha, p.total, e.nombre AS estado,
           u.nombre AS comprador_nombre, u.apellido AS comprador_apellido
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    JOIN usuario u ON u.id_usuario = p.id_usuario
    {donde}
    ORDER BY p.id_pedido DESC
    LIMIT %s
"""


def _rango_dia(texto):
    """'2026-11-14' -> (inicio, fin) del día; las fechas ya están en hora de México."""
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        dia = datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    inicio = datetime.datetime.combine(dia, datetime.time.min)
    return inicio, inicio + datetime.timedelta(days=1)


def _fecha_mexico(fecha):
    """datetime de RDS (ya en hora de México, sin zona) -> texto ISO con -06:00."""
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


@manejar_errores
def lambda_handler(event, context):
    validar_token(event, roles=[ROL_ADMINISTRADOR])
    filtros = query_params(event)

    condiciones = []
    parametros = []

    cursor_pagina = entero_positivo(filtros.get("cursor"))  # no válido -> primera página
    if cursor_pagina:
        condiciones.append("p.id_pedido < %s")
        parametros.append(cursor_pagina)

    estado_texto = (filtros.get("estado") or "").strip()
    if estado_texto:
        estado = ESTADOS.get(estado_texto.lower())
        if estado is None:
            raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
        condiciones.append("e.nombre = %s")
        parametros.append(estado)

    fecha_texto = (filtros.get("fecha") or "").strip()
    if fecha_texto:
        inicio, fin = _rango_dia(fecha_texto)
        condiciones.append("p.fecha >= %s AND p.fecha < %s")
        parametros.extend([inicio, fin])

    donde = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_BASE.format(donde=donde), (*parametros, TAM_PAGINA + 1))
        filas = list(cursor.fetchall())

    if not filas:
        return ok(MSG_SIN_REGISTROS, pedidos=[], siguiente_cursor=None)

    siguiente_cursor = None
    if len(filas) > TAM_PAGINA:
        filas = filas[:TAM_PAGINA]
        siguiente_cursor = filas[-1]["id_pedido"]

    pedidos = [
        {
            "id_pedido": f["id_pedido"],
            "fecha": _fecha_mexico(f["fecha"]),
            "total": f["total"],
            "estado": f["estado"],
            "comprador": f"{f['comprador_nombre']} {f['comprador_apellido']}",
        }
        for f in filas
    ]
    return ok(MSG_CONSULTA, pedidos=pedidos, siguiente_cursor=siguiente_cursor)
```

---

## lambda-actualizarEstadoPedido: DFR 7.3 Actualizar estado de pedido (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `PATCH /admin/pedidos/{id}/estado` (ruta nueva; el parámetro de ruta se llama `id`) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + Layer 2 |
| Timeout / memoria | 10 s / 128 MB |

**Body (JSON)**
```json
{"estado": "Enviado"}
```
- `estado`: Enviado, Entregado, Cancelado o Devuelto (sin distinguir mayúsculas).
- **Cancelado / Devuelto** → `sp_CancelarPedido(p_id_pedido, p_nuevo_estado)`: valida la transición, repone el stock y pone el pago en "Reembolsado" en una transacción (DFR 7.3).
- **Enviado / Entregado** → UPDATE simple desde la Lambda (como indica el propio SP), con el pedido bloqueado (`FOR UPDATE`): solo Pendiente → Enviado y Enviado → Entregado. No toca stock.
- Un pedido Cancelado o Devuelto ya no cambia (DFR 7.3).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Estado del pedido actualizado correctamente", "id_pedido": 345, "estado": "Cancelado", "variantes_repuestas": 2}` | DFR 7.3 (`variantes_repuestas` solo en Cancelado/Devuelto) |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta `estado` |
| 400 | `{"error": "El pedido no puede cambiar a ese estado"}` | DFR 7.3: transición no válida (también "Pendiente" como destino) |
| 400 | `{"error": "El estado seleccionado no es válido"}` | Valor que no es estado (aprobado por Ian) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 7.3: el rol no es Administrador |
| 404 | `{"error": "El pedido no existe"}` | Id inexistente o no válido (también cuando lo dice el SP; aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "pathParameters": {"id": "345"}, "body": "{\"estado\":\"Enviado\"}"}`

```python
"""
lambda-actualizarEstadoPedido
DFR 7.3 Actualizar estado de pedido (Administrador).
Transiciones del DFR: Pendiente->Enviado, Pendiente->Cancelado,
Enviado->Entregado, Enviado->Cancelado, Entregado->Devuelto. Un pedido
Cancelado o Devuelto ya no cambia.
- Cancelado / Devuelto: sp_CancelarPedido(p_id_pedido, p_nuevo_estado), que
  valida, repone stock y reembolsa el pago en una transacción. Sus errores
  (errno 1644) los devuelve manejar_errores con 400; "El pedido no existe"
  se traduce a 404 (aprobado por Ian, igual que 7.2).
- Enviado / Entregado: UPDATE simple desde la Lambda (lo indica el propio SP),
  con el pedido bloqueado (FOR UPDATE OF p).
Reglas de Ian: un valor que no es estado -> "El estado seleccionado no es
válido"; "Pendiente" como destino -> "El pedido no puede cambiar a ese estado".
Ruta: PATCH /admin/pedidos/{id}/estado (token con rol Administrador).
Tablas: pedido, estado_pedido. SP: sp_CancelarPedido.
"""
import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
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
    validar_token,
)

MSG_ESTADO_ACTUALIZADO = "Estado del pedido actualizado correctamente"  # DFR 7.3
MSG_TRANSICION_INVALIDA = "El pedido no puede cambiar a ese estado"  # DFR 7.3 (también lo da el SP)
MSG_PEDIDO_NO_EXISTE = "El pedido no existe"  # aprobado por Ian (también lo da el SP)
MSG_ESTADO_INVALIDO = "El estado seleccionado no es válido"  # aprobado por Ian

ID_MAX = 4294967295  # INT UNSIGNED de p_id_pedido
ESTADOS = {e.lower(): e for e in ("Pendiente", "Enviado", "Entregado", "Cancelado", "Devuelto")}
CON_SP = ("Cancelado", "Devuelto")
# Destino -> estado actual requerido (cambios que no tocan stock)
ORIGEN_REQUERIDO = {"Enviado": "Pendiente", "Entregado": "Enviado"}

SQL_SP = "CALL sp_CancelarPedido(%s, %s)"
SQL_ESTADO_ACTUAL = """
    SELECT e.nombre AS estado
    FROM pedido p
    JOIN estado_pedido e ON e.id_estado = p.id_estado
    WHERE p.id_pedido = %s
    FOR UPDATE OF p
"""
SQL_ACTUALIZAR = """
    UPDATE pedido
    SET id_estado = (SELECT id_estado FROM estado_pedido WHERE nombre = %s)
    WHERE id_pedido = %s
"""


def _cancelar_o_devolver(conexion, id_pedido, destino):
    """Ejecuta sp_CancelarPedido y devuelve cuántas variantes repuso."""
    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (id_pedido, destino))
            fila = cursor.fetchone()  # id_pedido, nuevo_estado, variantes_repuestas
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_PEDIDO_NO_EXISTE:
            raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)
    return fila["variantes_repuestas"] if fila else 0


def _enviar_o_entregar(conexion, id_pedido, destino):
    """Pendiente -> Enviado o Enviado -> Entregado, con el pedido bloqueado."""
    conexion.begin()  # si algo falla, manejar_errores hace rollback
    with conexion.cursor() as cursor:
        cursor.execute(SQL_ESTADO_ACTUAL, (id_pedido,))
        actual = cursor.fetchone()
        if actual is None:
            raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)
        if actual["estado"] != ORIGEN_REQUERIDO[destino]:
            raise ErrorNegocio(400, MSG_TRANSICION_INVALIDA)
        cursor.execute(SQL_ACTUALIZAR, (destino, id_pedido))
    conexion.commit()


@manejar_errores
def lambda_handler(event, context):
    validar_token(event, roles=[ROL_ADMINISTRADOR])  # DFR 7.3: "Acceso restringido"

    id_pedido = entero_positivo(path_param(event, "id"))
    if id_pedido is None or id_pedido > ID_MAX:
        raise ErrorNegocio(404, MSG_PEDIDO_NO_EXISTE)

    datos = leer_body(event)
    estado_texto = campo_texto(datos, "estado")
    if not estado_texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    destino = ESTADOS.get(estado_texto.lower())
    if destino is None:
        raise ErrorNegocio(400, MSG_ESTADO_INVALIDO)
    if destino == "Pendiente":  # ningún pedido vuelve a Pendiente
        raise ErrorNegocio(400, MSG_TRANSICION_INVALIDA)

    conexion = obtener_conexion()
    if destino in CON_SP:
        repuestas = _cancelar_o_devolver(conexion, id_pedido, destino)
        return ok(MSG_ESTADO_ACTUALIZADO, id_pedido=id_pedido, estado=destino,
                  variantes_repuestas=repuestas)

    _enviar_o_entregar(conexion, id_pedido, destino)
    return ok(MSG_ESTADO_ACTUALIZADO, id_pedido=id_pedido, estado=destino)
```

---

## lambda-consultarHistorialCompras: DFR 7.4 Consultar historial de compras (Comprador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /historial/compras?fecha_inicio=AAAA-MM-DD&fecha_fin=AAAA-MM-DD` (ruta nueva) |
| Acceso | Token JWT con rol **Comprador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + **Layer 2 actualizada** (`time_zone = '-06:00'`) |
| Timeout / memoria | 10 s / 128 MB |

**Query string**: `fecha_inicio` y `fecha_fin` obligatorias (DFR 7.4), ambas incluidas, en hora de México.

**Qué hace**
- Ejecuta **`sp_HistorialVentas(p_id_usuario, 'Comprador', p_fecha_inicio, p_fecha_fin)`** con el comprador del token (solo sus pedidos).
- Devuelve cada pedido del periodo con fecha, estado y total, y el `total_comprado` de la fila TOTAL del SP (Cancelados y Devueltos no suman, DFR 7.4).
- Si el SP responde "No tienes pedidos registrados" → 200 con lista vacía (aprobado por Ian).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "pedidos": [{"id_pedido": 345, "fecha": "2026-11-14T19:05:00-06:00", "estado": "Cancelado", "total": 500.0, "suma_al_total": false}, {"id_pedido": 346, "fecha": "...", "estado": "Entregado", "total": 1200.0, "suma_al_total": true}], "total_comprado": 1200.0}` | DFR 7.4 |
| 200 | `{"mensaje": "No tienes pedidos registrados", "pedidos": [], "total_comprado": 0}` | DFR 7.4: sin pedidos en el periodo |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta una fecha |
| 400 | `{"error": "La fecha no es válida"}` | Fecha mal escrita |
| 400 | `{"error": "La fecha inicial no puede ser mayor a la fecha final"}` | DFR 7.4 (mensaje del SP) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Comprador |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token comprador>"}, "queryStringParameters": {"fecha_inicio": "2026-11-01", "fecha_fin": "2026-11-30"}}`

```python
"""
lambda-consultarHistorialCompras
DFR 7.4 Consultar historial de compras (Comprador): pedidos del periodo con
fecha, estado y total, y el total comprado (Cancelados y Devueltos no suman).
La consulta vive en sp_HistorialVentas (tipo 'Comprador'); la Lambda solo
valida el formato de las fechas y da forma a la respuesta. Restricción por
rol (el SP la deja a la aplicación): el id_usuario sale del token.
Reglas de Ian: "No tienes pedidos registrados" del SP -> 200 con lista vacía.
Las fechas se guardan en hora de México (opción A), así que el SP compara
los días correctos.
Ruta: GET /historial/compras (token con rol Comprador).
SP: sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin).
"""
import datetime
import re

import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_COMPRADOR,
    ErrorNegocio,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_PEDIDOS = "No tienes pedidos registrados"  # DFR 7.4 (lo da el SP)
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

ZONA_MEXICO = datetime.timezone(datetime.timedelta(hours=-6))  # etiqueta -06:00
NO_SUMAN = ("Cancelado", "Devuelto")

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_SP = "CALL sp_HistorialVentas(%s, 'Comprador', %s, %s)"


def _fecha(texto):
    texto = (texto or "").strip()
    if not texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)


def _fecha_mexico(fecha):
    return fecha.replace(tzinfo=ZONA_MEXICO).isoformat()


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_COMPRADOR])
    filtros = query_params(event)

    if not (filtros.get("fecha_inicio") or "").strip() or not (filtros.get("fecha_fin") or "").strip():
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    fecha_inicio = _fecha(filtros.get("fecha_inicio"))
    fecha_fin = _fecha(filtros.get("fecha_fin"))
    # "La fecha inicial no puede ser mayor a la fecha final" lo valida el SP.

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (sesion["id_usuario"], fecha_inicio, fecha_fin))
            filas = list(cursor.fetchall())
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_SIN_PEDIDOS:
            return ok(MSG_SIN_PEDIDOS, pedidos=[], total_comprado=0)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)

    pedidos = []
    total_comprado = 0
    for fila in filas:
        if fila["pedido"] == "TOTAL":  # fila de WITH ROLLUP
            total_comprado = fila["total_comprado"]
            continue
        pedidos.append({
            "id_pedido": int(fila["pedido"]),
            "fecha": _fecha_mexico(fila["fecha"]),
            "estado": fila["estado"],
            "total": fila["total_pedido"],
            "suma_al_total": fila["estado"] not in NO_SUMAN,
        })

    return ok(MSG_CONSULTA, pedidos=pedidos, total_comprado=total_comprado)
```

---

## lambda-reporteVentasVendedor: DFR 8.1 Reporte de ventas del vendedor (Vendedor)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /vendedor/ventas?fecha_inicio=AAAA-MM-DD&fecha_fin=AAAA-MM-DD` (ruta nueva) |
| Acceso | Token JWT con rol **Vendedor** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + **Layer 2 actualizada** (`time_zone = '-06:00'`) |
| Timeout / memoria | 10 s / 128 MB |

**Query string**: `fecha_inicio` y `fecha_fin` obligatorias (DFR 8.1), ambas incluidas, en hora de México.

**Qué hace**
- Ejecuta **`sp_HistorialVentas(p_id_usuario, 'Vendedor', p_fecha_inicio, p_fecha_fin)`** con el vendedor del token (solo sus ventas).
- Detalle por producto y total de ventas (fila TOTAL del SP), con precio unitario histórico; Cancelados y Devueltos no cuentan (DFR 8.1).
- Si el SP responde "No hay ventas en el periodo seleccionado" → 200 con lista vacía (mismo criterio aprobado en 7.4).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "productos": [{"id_producto": 120, "producto": "iPhone 18", "unidades_vendidas": 3, "total_vendido": 150000.0}], "total_ventas": 150000.0}` | DFR 8.1 |
| 200 | `{"mensaje": "No hay ventas en el periodo seleccionado", "productos": [], "total_ventas": 0}` | DFR 8.1: sin ventas |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta una fecha |
| 400 | `{"error": "La fecha no es válida"}` | Fecha mal escrita |
| 400 | `{"error": "La fecha inicial no puede ser mayor a la fecha final"}` | DFR 8.1 (mensaje del SP) |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | El rol no es Vendedor |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token vendedor>"}, "queryStringParameters": {"fecha_inicio": "2026-11-01", "fecha_fin": "2026-11-30"}}`

```python
"""
lambda-reporteVentasVendedor
DFR 8.1 Reporte de ventas del vendedor (Vendedor): total de ventas y detalle
por producto en un rango de fechas, con precio unitario histórico; los
pedidos Cancelados y Devueltos no cuentan.
La consulta vive en sp_HistorialVentas (tipo 'Vendedor'); la Lambda valida el
formato de las fechas y da forma a la respuesta. Restricción por rol (el SP la
deja a la aplicación): el id del vendedor sale del token.
Regla de Ian (igual que 7.4): "No hay ventas en el periodo seleccionado" del
SP -> 200 con lista vacía.
La fila TOTAL del ROLLUP se detecta por id_producto nulo (no por el texto,
porque un producto podría llamarse "TOTAL").
Ruta: GET /vendedor/ventas (token con rol Vendedor).
SP: sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin).
"""
import datetime
import re

import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_VENDEDOR,
    ErrorNegocio,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_VENTAS = "No hay ventas en el periodo seleccionado"  # DFR 8.1 (lo da el SP)
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_SP = "CALL sp_HistorialVentas(%s, 'Vendedor', %s, %s)"


def _fecha(texto):
    texto = (texto or "").strip()
    if not texto:
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)


@manejar_errores
def lambda_handler(event, context):
    sesion = validar_token(event, roles=[ROL_VENDEDOR])
    filtros = query_params(event)

    if not (filtros.get("fecha_inicio") or "").strip() or not (filtros.get("fecha_fin") or "").strip():
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    fecha_inicio = _fecha(filtros.get("fecha_inicio"))
    fecha_fin = _fecha(filtros.get("fecha_fin"))
    # "La fecha inicial no puede ser mayor a la fecha final" lo valida el SP.

    conexion = obtener_conexion()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (sesion["id_usuario"], fecha_inicio, fecha_fin))
            filas = list(cursor.fetchall())
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_SIN_VENTAS:
            return ok(MSG_SIN_VENTAS, productos=[], total_ventas=0)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)

    productos = []
    total_ventas = 0
    for fila in filas:
        if fila["id_producto"] is None:  # fila TOTAL de WITH ROLLUP
            total_ventas = fila["total_vendido"]
            continue
        productos.append({
            "id_producto": fila["id_producto"],
            "producto": fila["producto"],
            "unidades_vendidas": fila["unidades_vendidas"],
            "total_vendido": fila["total_vendido"],
        })

    return ok(MSG_CONSULTA, productos=productos, total_ventas=total_ventas)
```

---

## lambda-reporteVentasAdmin: DFR 8.2 Reporte de ventas por vendedor (Administrador)

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Método y ruta | `GET /admin/ventas?id_vendedor=&fecha_inicio=AAAA-MM-DD&fecha_fin=AAAA-MM-DD` (ruta nueva) |
| Acceso | Token JWT con rol **Administrador** |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET |
| Layers | Layer 1 + **Layer 2 actualizada** (`time_zone = '-06:00'`) |
| Timeout / memoria | 10 s / 128 MB |

**Query string**: `id_vendedor`, `fecha_inicio` y `fecha_fin` obligatorios (DFR 8.2). Para elegir al vendedor, Flask puede usar `GET /admin/usuarios?rol=Vendedor` (1.4).

**Qué hace**
- Revisa que `id_vendedor` sea un usuario con rol **Vendedor** (Activo o Inactivo: sus ventas pasadas siguen siendo historial válido). Si no → 404 "El vendedor no existe".
- Ejecuta **`sp_HistorialVentas(p_id_usuario = id_vendedor, 'Vendedor', p_fecha_inicio, p_fecha_fin)`**: mismas reglas de cálculo y fechas que 8.1 (DFR 8.2).

**Respuestas**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Consulta realizada", "vendedor": "Luis Pérez", "productos": [{"id_producto": 120, "producto": "iPhone 18", "unidades_vendidas": 3, "total_vendido": 150000.0}], "total_ventas": 150000.0}` | DFR 8.2 |
| 200 | `{"mensaje": "No hay ventas en el periodo seleccionado", "vendedor": "Luis Pérez", "productos": [], "total_ventas": 0}` | Sin ventas (mismo criterio que 8.1) |
| 400 | `{"error": "Debe completar los campos obligatorios"}` | Falta un dato |
| 400 | `{"error": "La fecha no es válida"}` | Fecha mal escrita |
| 400 | `{"error": "La fecha inicial no puede ser mayor a la fecha final"}` | Mensaje del SP |
| 401 | `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}` | Token ausente, inválido o vencido |
| 403 | `{"error": "Acceso restringido"}` | DFR 8.2: el rol no es Administrador |
| 404 | `{"error": "El vendedor no existe"}` | Id inexistente, no válido o que no es Vendedor (aprobado por Ian) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch) |

**Prueba en consola**: `{"headers": {"Authorization": "Bearer <token admin>"}, "queryStringParameters": {"id_vendedor": "2", "fecha_inicio": "2026-11-01", "fecha_fin": "2026-11-30"}}`

```python
"""
lambda-reporteVentasAdmin
DFR 8.2 Reporte de ventas por vendedor (Administrador): mismas reglas de
cálculo y fechas que 8.1, para el vendedor que elija el administrador.
La consulta vive en sp_HistorialVentas (tipo 'Vendedor'); el SP deja la
restricción por rol a la aplicación: aquí solo entra el Administrador.
Reglas de Ian:
- id_vendedor inexistente, no válido o que no es Vendedor -> 404
  "El vendedor no existe" (evita un "No hay ventas" engañoso). Un vendedor
  Inactivo sí se consulta (su historial sigue siendo válido).
- "No hay ventas en el periodo seleccionado" del SP -> 200 con lista vacía.
La fila TOTAL del ROLLUP se detecta por id_producto nulo.
Ruta: GET /admin/ventas (token con rol Administrador).
Tablas: usuario, rol. SP: sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin).
"""
import datetime
import re

import pymysql

from smavib_common import (
    ERRNO_SIGNAL,
    MSG_CAMPOS_OBLIGATORIOS,
    ROL_ADMINISTRADOR,
    ROL_VENDEDOR,
    ErrorNegocio,
    entero_positivo,
    manejar_errores,
    obtener_conexion,
    ok,
    query_params,
    validar_token,
)

MSG_CONSULTA = "Consulta realizada"
MSG_SIN_VENTAS = "No hay ventas en el periodo seleccionado"  # DFR 8.1 (lo da el SP)
MSG_FECHA_INVALIDA = "La fecha no es válida"  # aprobado por Ian
MSG_VENDEDOR_NO_EXISTE = "El vendedor no existe"  # aprobado por Ian

ID_MAX = 4294967295  # INT UNSIGNED de p_id_usuario

_RE_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

SQL_VENDEDOR = """
    SELECT u.nombre, u.apellido
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
    WHERE u.id_usuario = %s AND r.nombre = %s
"""
SQL_SP = "CALL sp_HistorialVentas(%s, 'Vendedor', %s, %s)"


def _vacio(valor):
    return not (valor or "").strip()


def _fecha(texto):
    texto = (texto or "").strip()
    if not _RE_FECHA.fullmatch(texto):
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:  # p. ej. 2026-02-30
        raise ErrorNegocio(400, MSG_FECHA_INVALIDA)


@manejar_errores
def lambda_handler(event, context):
    validar_token(event, roles=[ROL_ADMINISTRADOR])  # DFR 8.2: solo el administrador
    filtros = query_params(event)

    if any(_vacio(filtros.get(c)) for c in ("id_vendedor", "fecha_inicio", "fecha_fin")):
        raise ErrorNegocio(400, MSG_CAMPOS_OBLIGATORIOS)
    fecha_inicio = _fecha(filtros.get("fecha_inicio"))
    fecha_fin = _fecha(filtros.get("fecha_fin"))
    # "La fecha inicial no puede ser mayor a la fecha final" lo valida el SP.

    id_vendedor = entero_positivo(filtros.get("id_vendedor"))
    if id_vendedor is None or id_vendedor > ID_MAX:
        raise ErrorNegocio(404, MSG_VENDEDOR_NO_EXISTE)

    conexion = obtener_conexion()
    with conexion.cursor() as cursor:
        cursor.execute(SQL_VENDEDOR, (id_vendedor, ROL_VENDEDOR))
        vendedor = cursor.fetchone()
    if vendedor is None:
        raise ErrorNegocio(404, MSG_VENDEDOR_NO_EXISTE)
    nombre_vendedor = f"{vendedor['nombre']} {vendedor['apellido']}"

    try:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_SP, (id_vendedor, fecha_inicio, fecha_fin))
            filas = list(cursor.fetchall())
            while cursor.nextset():  # deja libre la conexión que se reutiliza
                pass
    except pymysql.err.MySQLError as e:
        if len(e.args) >= 2 and e.args[0] == ERRNO_SIGNAL and e.args[1] == MSG_SIN_VENTAS:
            return ok(MSG_SIN_VENTAS, vendedor=nombre_vendedor, productos=[], total_ventas=0)
        raise  # los demás mensajes del SP salen con 400 (manejar_errores)

    productos = []
    total_ventas = 0
    for fila in filas:
        if fila["id_producto"] is None:  # fila TOTAL de WITH ROLLUP
            total_ventas = fila["total_vendido"]
            continue
        productos.append({
            "id_producto": fila["id_producto"],
            "producto": fila["producto"],
            "unidades_vendidas": fila["unidades_vendidas"],
            "total_vendido": fila["total_vendido"],
        })

    return ok(MSG_CONSULTA, vendedor=nombre_vendedor, productos=productos, total_ventas=total_ventas)
```

---

## lambda-cargaDynamo: carga inicial del catálogo en DynamoDB (herramienta, una sola vez)

Lee de RDS los productos que creó `lambdas/carga/01_carga_inicial.sql` y los escribe en DynamoDB con `BatchWriteItem` (DFR, Requerimientos de Eficiencia). **No se conecta a API Gateway**: se invoca a mano desde la consola de Lambda (pestaña *Test*), así que solo la puede ejecutar quien tenga acceso a la cuenta.

**Ficha de configuración**
| Campo | Valor |
|---|---|
| Disparador | **Ninguno** (sin ruta de API Gateway). Invocación manual con el evento de prueba |
| VPC | Sí: subredes de RDS y grupo de seguridad de las Lambdas. **Requiere el VPC Gateway Endpoint de DynamoDB** |
| Variables de entorno | DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, TABLA_PRODUCTOS |
| Layers | Layer 1 + Layer 2 (boto3 ya viene en el runtime) |
| Timeout / memoria | **15 min (900 s) / 512 MB** |

**Evento de prueba** (con el `primer_id` y el `ultimo_id` que mostró el `.sql`)
```json
{"desde_id": 1, "hasta_id": 17000}
```

**Cómo trabaja (optimizado, pedido de Ian)**
- **Una sola conexión** a MySQL (la de `smavib_common`), leída en **bloques de 1,000** por `id_producto` (keyset), sin cargar los 17,000 en memoria.
- Por bloque: `BatchGetItem` (100 llaves por llamada, solo `productoID`) para saber cuáles **ya existen** y **no sobrescribirlos** (si se invoca dos veces, no pisa productos editados). Los que faltan se escriben con `batch_writer` (lotes de 25 con reintento automático de no procesados).
- Ítem con el estándar de Ian: `productoID`, `Nombre`, `NombreBusqueda`, `Descripcion.Resumen` (generado), `Precio`, `Marca`, `Categoria`, `CategoriaID`, `URLImagen` (placehold.co con la categoría), `Stock`, `VendedorID`, `Estado` y `Variantes` (la estándar). Sin `Especificaciones` ni `LogisticaEnvio` (son opcionales).
- Si quedan menos de 60 s antes del timeout, se detiene y devuelve `continuar_desde_id` para volver a invocarla desde ahí.
- Costo aproximado de los 17,000 ítems con 2 GSI: menos de $0.10.

**Respuesta**
| Status | Body | Caso |
|---|---|---|
| 200 | `{"mensaje": "Carga completa", "leidos": 17000, "escritos": 17000, "ya_existian": 0, "sin_variante_estandar": 0, "ultimo_id_procesado": 17000, "continuar_desde_id": null}` | Terminó el rango |
| 200 | `{"mensaje": "Carga parcial: vuelve a invocar con desde_id = continuar_desde_id", ..., "continuar_desde_id": 9001}` | Se acercaba el timeout |
| 400 | `{"error": "Indica desde_id y hasta_id válidos (desde_id <= hasta_id)"}` | Evento incompleto o inválido (herramienta interna; texto de Claude) |
| 500 | `{"error": "Ocurrió un error interno. Intenta más tarde"}` | Error no controlado (queda en CloudWatch; se puede reintentar: no duplica) |

```python
"""
lambda-cargaDynamo
Herramienta de carga inicial (DFR, Requerimientos de Eficiencia: ingesta
masiva en DynamoDB con BatchWriteItem). Lee de RDS los productos que creó
01_carga_inicial.sql y los escribe en el catálogo con el estándar de Ian.
Se invoca UNA vez a mano desde la consola (sin API Gateway):
    {"desde_id": 1, "hasta_id": 17000}
Diseño (pedido de Ian: sin conexiones de más y optimizado):
- Una sola conexión a MySQL (smavib_common), lectura por bloques de 1,000 con
  keyset (id_producto > último leído), sin cargar todo en memoria.
- Por bloque: BatchGetItem (100 llaves por llamada, solo productoID) para no
  sobrescribir ítems que ya existan, y batch_writer (lotes de 25 con
  reintento automático) para los que faltan. Se puede reintentar sin duplicar.
- Si quedan menos de 60 s, se detiene y devuelve desde dónde continuar.
Tablas: producto, categoria, marca, variante_producto (+ DynamoDB).
"""
import os
import time
import unicodedata
from urllib.parse import quote

import boto3

from smavib_common import (
    entero_positivo,
    error,
    manejar_errores,
    obtener_conexion,
    ok,
)

MSG_EVENTO_INVALIDO = "Indica desde_id y hasta_id válidos (desde_id <= hasta_id)"

BLOQUE_RDS = 1000  # productos por lectura
LOTE_LECTURA = 100  # máximo de llaves por BatchGetItem
MARGEN_MS = 60000  # se detiene si quedan menos de 60 s
REINTENTOS = 5

# Variante estándar unida por SKU: un solo renglón por producto
SQL_BLOQUE = """
    SELECT p.id_producto, p.nombre, p.precio, p.estado, p.id_vendedor,
           c.id_categoria, c.nombre AS categoria, m.nombre AS marca,
           v.id_variante, v.sku, v.stock
    FROM producto p
    JOIN categoria c ON c.id_categoria = p.id_categoria
    JOIN marca m ON m.id_marca = p.id_marca
    LEFT JOIN variante_producto v
           ON v.id_producto = p.id_producto
          AND v.sku = CONCAT('P', p.id_producto, '-STD')
    WHERE p.id_producto > %s AND p.id_producto <= %s
    ORDER BY p.id_producto
    LIMIT %s
"""

TABLA_PRODUCTOS = os.environ["TABLA_PRODUCTOS"]
dynamodb = boto3.resource("dynamodb")
tabla_productos = dynamodb.Table(TABLA_PRODUCTOS)


def _texto_busqueda(texto):
    """Igual que en 3.1, 3.3 y 4.1: minúsculas, sin acentos, espacios normalizados."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def _existentes(ids):
    """productoID que ya están en DynamoDB (BatchGetItem de 100 en 100)."""
    encontrados = set()
    for inicio in range(0, len(ids), LOTE_LECTURA):
        pedido = {
            TABLA_PRODUCTOS: {
                "Keys": [{"productoID": str(i)} for i in ids[inicio:inicio + LOTE_LECTURA]],
                "ProjectionExpression": "productoID",
            }
        }
        for intento in range(REINTENTOS):
            respuesta = dynamodb.batch_get_item(RequestItems=pedido)
            for item in respuesta.get("Responses", {}).get(TABLA_PRODUCTOS, []):
                encontrados.add(item["productoID"])
            pedido = respuesta.get("UnprocessedKeys") or {}
            if not pedido:
                break
            time.sleep(0.2 * (intento + 1))  # espera creciente antes de reintentar
        else:
            raise RuntimeError("DynamoDB dejó llaves sin procesar tras varios reintentos")
    return encontrados


def _item(fila):
    """Ítem con el estándar de Ian a partir de una fila de RDS."""
    return {
        "productoID": str(fila["id_producto"]),
        "Nombre": fila["nombre"],
        "NombreBusqueda": _texto_busqueda(fila["nombre"]),
        "Descripcion": {
            "Resumen": f"{fila['categoria']} de la marca {fila['marca']}. Producto de prueba del catálogo SMAVIB."
        },
        "Precio": fila["precio"],  # Decimal de MySQL
        "Marca": fila["marca"],
        "Categoria": fila["categoria"],
        "CategoriaID": fila["id_categoria"],
        "URLImagen": f"https://placehold.co/600x400?text={quote(fila['categoria'])}",
        "Stock": fila["stock"],  # referencia; el exacto vive en RDS
        "VendedorID": fila["id_vendedor"],
        "Estado": fila["estado"],
        "Variantes": [
            {"IdVariante": fila["id_variante"], "SKU": fila["sku"], "Stock": fila["stock"], "Atributos": {}}
        ],
    }


@manejar_errores
def lambda_handler(event, context):
    evento = event if isinstance(event, dict) else {}
    desde_id = entero_positivo(evento.get("desde_id"))
    hasta_id = entero_positivo(evento.get("hasta_id"))
    if desde_id is None or hasta_id is None or desde_id > hasta_id:
        return error(400, MSG_EVENTO_INVALIDO)

    conexion = obtener_conexion()
    ultimo = desde_id - 1  # keyset: id_producto > ultimo
    leidos = escritos = ya_existian = sin_variante = 0
    continuar_desde = None

    while True:
        if context is not None and context.get_remaining_time_in_millis() < MARGEN_MS:
            continuar_desde = ultimo + 1
            break

        with conexion.cursor() as cursor:
            cursor.execute(SQL_BLOQUE, (ultimo, hasta_id, BLOQUE_RDS))
            filas = cursor.fetchall()
        if not filas:
            break

        leidos += len(filas)
        ultimo = filas[-1]["id_producto"]
        completas = [f for f in filas if f["id_variante"] is not None]
        sin_variante += len(filas) - len(completas)

        existentes = _existentes([f["id_producto"] for f in completas])
        nuevos = [f for f in completas if str(f["id_producto"]) not in existentes]
        ya_existian += len(completas) - len(nuevos)

        with tabla_productos.batch_writer() as escritor:  # lotes de 25 + reintentos
            for fila in nuevos:
                escritor.put_item(Item=_item(fila))
        escritos += len(nuevos)
        print(f"Bloque hasta id {ultimo}: {len(nuevos)} escritos, {len(completas) - len(nuevos)} ya existían")

    mensaje = "Carga completa" if continuar_desde is None else (
        "Carga parcial: vuelve a invocar con desde_id = continuar_desde_id"
    )
    return ok(
        mensaje,
        leidos=leidos,
        escritos=escritos,
        ya_existian=ya_existian,
        sin_variante_estandar=sin_variante,
        ultimo_id_procesado=ultimo if leidos else None,
        continuar_desde_id=continuar_desde,
    )
```

---
