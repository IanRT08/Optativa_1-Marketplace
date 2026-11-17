# LAMBDAS: SMAVIB

Fichas de configuración de las 36 funciones: ruta, acceso, VPC, variables de entorno, Layers, timeout y memoria, body y respuestas. El código de cada función está en `lambdas/<nombre>/lambda_function.py` y se pega tal cual en el editor de la consola de Lambda (handler `lambda_function.lambda_handler`). Las rutas también están en [`docs/openapi.json`](../docs/openapi.json).

Todas las funciones usan dos Layers:
- **Layer 1**: PyMySQL, bcrypt, PyJWT (la armas tú).
- **Layer 2**: `smavib_common.py`. El archivo está en [`layer/python/smavib_common.py`](layer/python/smavib_common.py); comprime la carpeta `python/` tal cual.

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

**Código:** [`lambdas/lambda-consultarCategorias/lambda_function.py`](lambdas/lambda-consultarCategorias/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-registrarUsuario/lambda_function.py`](lambdas/lambda-registrarUsuario/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-iniciarSesion/lambda_function.py`](lambdas/lambda-iniciarSesion/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-crearCategoria/lambda_function.py`](lambdas/lambda-crearCategoria/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-editarCategoria/lambda_function.py`](lambdas/lambda-editarCategoria/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-eliminarCategoria/lambda_function.py`](lambdas/lambda-eliminarCategoria/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-crearUsuario/lambda_function.py`](lambdas/lambda-crearUsuario/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarUsuarios/lambda_function.py`](lambdas/lambda-consultarUsuarios/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-editarUsuario/lambda_function.py`](lambdas/lambda-editarUsuario/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-eliminarUsuario/lambda_function.py`](lambdas/lambda-eliminarUsuario/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarMarcas/lambda_function.py`](lambdas/lambda-consultarMarcas/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarAtributos/lambda_function.py`](lambdas/lambda-consultarAtributos/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-registrarDireccion/lambda_function.py`](lambdas/lambda-registrarDireccion/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarDirecciones/lambda_function.py`](lambdas/lambda-consultarDirecciones/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-desactivarDireccion/lambda_function.py`](lambdas/lambda-desactivarDireccion/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-crearProducto/lambda_function.py`](lambdas/lambda-crearProducto/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarMisProductos/lambda_function.py`](lambdas/lambda-consultarMisProductos/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-editarProducto/lambda_function.py`](lambdas/lambda-editarProducto/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-estadoProducto/lambda_function.py`](lambdas/lambda-estadoProducto/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-registrarVariante/lambda_function.py`](lambdas/lambda-registrarVariante/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-actualizarStockMasivo/lambda_function.py`](lambdas/lambda-actualizarStockMasivo/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarProductos/lambda_function.py`](lambdas/lambda-consultarProductos/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarProducto/lambda_function.py`](lambdas/lambda-consultarProducto/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-agregarAlCarrito/lambda_function.py`](lambdas/lambda-agregarAlCarrito/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarCarrito/lambda_function.py`](lambdas/lambda-consultarCarrito/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-modificarCantidadCarrito/lambda_function.py`](lambdas/lambda-modificarCantidadCarrito/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-eliminarDelCarrito/lambda_function.py`](lambdas/lambda-eliminarDelCarrito/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-confirmarCompra/lambda_function.py`](lambdas/lambda-confirmarCompra/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarMisPedidos/lambda_function.py`](lambdas/lambda-consultarMisPedidos/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarDetallePedido/lambda_function.py`](lambdas/lambda-consultarDetallePedido/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarPedidosAdmin/lambda_function.py`](lambdas/lambda-consultarPedidosAdmin/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-actualizarEstadoPedido/lambda_function.py`](lambdas/lambda-actualizarEstadoPedido/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-consultarHistorialCompras/lambda_function.py`](lambdas/lambda-consultarHistorialCompras/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-reporteVentasVendedor/lambda_function.py`](lambdas/lambda-reporteVentasVendedor/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

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

**Código:** [`lambdas/lambda-reporteVentasAdmin/lambda_function.py`](lambdas/lambda-reporteVentasAdmin/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

---

## lambda-cargaDynamo: carga inicial del catálogo en DynamoDB (herramienta, una sola vez)

Lee de RDS los productos que creó [`database/04_carga_inicial.sql`](../database/04_carga_inicial.sql) y los escribe en DynamoDB con `BatchWriteItem` (DFR, Requerimientos de Eficiencia). **No se conecta a API Gateway**: se invoca a mano desde la consola de Lambda (pestaña *Test*), así que solo la puede ejecutar quien tenga acceso a la cuenta.

> **Estado en AWS (2026-11-17):** se borró de la cuenta después de cargar y verificar los 17,000 ítems (los 2 GSI también tienen 17,000). El código se conserva aquí como evidencia de la ingesta masiva. Si hay que volver a cargar, se crea de nuevo con esta ficha y se borra al terminar. Así ninguna función desplegada sale del rango de 128–256 MB de los lineamientos.

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

**Código:** [`lambdas/lambda-cargaDynamo/lambda_function.py`](lambdas/lambda-cargaDynamo/lambda_function.py) (pegar tal cual en el editor de la consola de Lambda).

---
