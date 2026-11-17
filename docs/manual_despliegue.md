# Manual de despliegue (AWS Academy Learner Lab)

Toda la infraestructura se configura a mano en la consola de AWS, región `us-east-1`. Las funciones usan el rol **LabRole**; no se crean roles de IAM propios (lineamientos §1.3). Las fichas de cada Lambda están en [`backend/LAMBDAS.md`](../backend/LAMBDAS.md).

> Al iniciar cada sesión del Learner Lab cambian las credenciales temporales y la URL de API Gateway puede cambiar. Ningún endpoint ni credencial va en el código: todo se lee de variables de entorno.

## 1. Amazon RDS (MySQL 8.0)

1. Crea una instancia MySQL 8.0 **db.t3.micro o db.t4g.micro**, con 20 GB gp2/gp3 como máximo y acceso público desactivado.
2. Crea dos grupos de seguridad:
   - `sg-lambdas`: lo usan las Lambdas.
   - `sg-rds`: entrada **TCP 3306 solo desde `sg-lambdas`**.
3. Desde DataGrip, MySQL Workbench o el cliente `mysql`, ejecuta los scripts de [`database/`](../database/README.md) en orden: `01_tablas.sql` → `02_stored_procedures.sql` → `03_vendedores_carga.sql` → `04_carga_inicial.sql`. `04` reporta `primer_id` y `ultimo_id`; anótalos para el paso 3.4.
4. Fuera de horario, **detén la instancia** para no agotar el crédito (lineamientos §1.2).

## 2. Amazon DynamoDB

1. Crea la tabla `Productos` con llave de partición `productoID` (Cadena) y capacidad **bajo demanda**.
2. Crea los índices `EstadoPrecio` y `CategoriaPrecio`, uno a la vez. Cada uno debe estar *Activo* antes de crear el otro. Las llaves y proyecciones están en [`database/dynamodb/productos_esquema.json`](../database/dynamodb/productos_esquema.json).
3. En la VPC de RDS, crea un **VPC Gateway Endpoint** de DynamoDB asociado a las tablas de ruteo de las subredes de las Lambdas. Así se evita un NAT Gateway.

## 3. AWS Lambda

1. **Layers** (Python 3.14, x86_64):
   - Layer 1: PyMySQL, bcrypt y PyJWT instalados en una carpeta `python/`, comprimida.
   - Layer 2: comprime la carpeta [`backend/layer/python/`](../backend/layer/python/) tal cual (contiene `smavib_common.py`).
2. Crea cada función de [`backend/lambdas/`](../backend/lambdas/) con estas opciones:
   - Nombre igual al de su carpeta y runtime Python 3.14.
   - Rol **LabRole** y handler `lambda_function.lambda_handler`.
   - Pega el contenido de su `lambda_function.py`.
   - Agrega las dos Layers.
   - Timeout y memoria según la ficha: 128–256 MB. La excepción es `lambda-cargaDynamo` (512 MB): es una herramienta que se ejecuta una sola vez y se borra al terminar la carga (paso 5).
3. **Red:** las funciones que usan RDS van en la VPC, con las subredes de RDS y `sg-lambdas`. `lambda-consultarProductos` (4.1) va **sin VPC**, porque solo usa DynamoDB.
4. **Variables de entorno** (sin valores en el código):

   | Variable | Uso |
   |---|---|
   | `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Conexión a RDS (`DB_NAME=marketplace`) |
   | `JWT_SECRET` | Firma del JWT; 32 caracteres o más e igual en todas las funciones |
   | `TABLA_PRODUCTOS` | Nombre de la tabla DynamoDB (`Productos`) |

5. **Carga del catálogo:** invoca `lambda-cargaDynamo` una vez desde la pestaña *Test* con `{"desde_id": <primer_id>, "hasta_id": <ultimo_id>}`. Si responde `continuar_desde_id`, vuelve a invocarla desde ese valor. Al final compara los conteos de RDS y DynamoDB (17,000) y **borra la función** de la consola: ya no se necesita.

## 4. Amazon API Gateway

1. Crea la API y una ruta por cada operación de [`docs/openapi.json`](openapi.json) (35 rutas), con integración proxy a su Lambda (el nombre viene en la descripción de cada operación).
2. En las rutas `POST /auth/login`, `POST /usuarios/registro` y `POST /compras` **no actives** el registro completo de peticiones y respuestas (*data trace*): guardaría contraseñas y tarjetas en CloudWatch. El registro de errores sí puede quedar.
3. Copia la URL base, sin `/` final, para el paso 6.

## 5. Primer administrador

`POST /usuarios/registro` solo crea Compradores, y `POST /admin/usuarios` exige un token de Administrador. Por eso el primer administrador se crea así:
1. Regístralo desde la aplicación como Comprador.
2. En la base de datos, cambia su rol:

```sql
UPDATE usuario SET id_rol = (SELECT id_rol FROM rol WHERE nombre = 'Administrador')
WHERE email = '<correo del administrador>';
```

## 6. Interfaz web (Flask)

Pasos en el [README](../README.md#ejecutar-la-interfaz-web): copiar `frontend/.env.example` a `frontend/.env` y llenar `API_BASE_URL` (paso 4.3) y `SECRET_KEY`, luego ejecutar `python app.py`.

**En Vercel** (el repositorio de GitHub conectado a un proyecto de Vercel):
1. *Settings* → *General* → **Root Directory = `frontend`**. Vercel detecta Flask por `app.py` (expone `app`) e instala `requirements.txt`.
2. *Storage* → **Create Database** → **Upstash Redis** (plan gratuito, región `us-east-1`) → **Connect to project**. Vercel agrega la variable de conexión; la app lee `REDIS_URL` (`rediss://…`). Sin Redis la app no arranca en Vercel, porque el disco es de solo lectura y no se comparte entre instancias.
3. *Settings* → *Environment Variables*: `API_BASE_URL` y `SECRET_KEY` (la misma regla de 32 caracteres o más). `COOKIE_SECURE` se queda vacío, porque Vercel sirve por HTTPS.
4. Cada push a `main` despliega. El CI de GitHub ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) corre las pruebas de `frontend/tests` y compila las Lambdas.

## 7. Prueba de humo

1. `GET /categorias` sin token debe responder 200.
2. Registra un usuario, inicia sesión y usa el token en `GET /carrito`. Debe responder 200 con "Tu carrito está vacío".
3. Sin token, `GET /carrito` debe responder 401.
