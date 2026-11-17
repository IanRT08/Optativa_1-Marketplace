# SMAVIB: Sistema de Marketplace en AWS

Marketplace web con tres roles (**Comprador**, **Vendedor** y **Administrador**) construido sobre AWS Academy Learner Lab. Proyecto B de Optativa I: Bases de Datos en la Nube.

**Navegador → Flask → Amazon API Gateway → AWS Lambda → Amazon RDS (MySQL) + Amazon DynamoDB**

| | |
|---|---|
| Base transaccional | MySQL 8.0 en Amazon RDS: **16 tablas** y **4 stored procedures** transaccionales |
| Catálogo | Amazon DynamoDB: tabla `Productos` con **17,000 productos** y 2 índices secundarios globales |
| API | 35 rutas REST en API Gateway, una Lambda por requerimiento (Python 3.14) |
| Seguridad | JWT con control de acceso por rol (RBAC), contraseñas con bcrypt, pago tokenizado, SQL parametrizado, CSRF, CSP y sesión del lado del servidor |
| Interfaz | Flask + Jinja, CSS propio con variables, adaptable de 360 a 1280 px; Lighthouse de accesibilidad 100 en las pantallas medidas |

## Estructura del repositorio

```
├── backend/
│   ├── lambdas/<nombre>/lambda_function.py   36 funciones Lambda (una carpeta por función)
│   ├── layer/python/smavib_common.py          Layer compartida: conexión, JWT, respuestas, validaciones
│   └── LAMBDAS.md                             Ficha de configuración de cada Lambda
├── database/
│   ├── 01_tablas.sql                          DDL de las 16 tablas + catálogos (DML)
│   ├── 02_stored_procedures.sql               Los 4 stored procedures
│   ├── 03_vendedores_carga.sql, 04_carga_inicial.sql   Datos iniciales (17,000 productos)
│   ├── 05_pruebas_sp.sql                      Pruebas de los stored procedures
│   └── dynamodb/                              Esquema de la tabla Productos e índices (JSON)
├── docs/
│   ├── DER.png                                Diagrama entidad-relación (MySQL + DynamoDB)
│   ├── arquitectura.md                        Arquitectura AWS y diagramas C4
│   ├── openapi.json                           Especificación OpenAPI 3 de las 35 rutas
│   └── manual_despliegue.md                   Configuración paso a paso en el Learner Lab
└── frontend/                                  Aplicación Flask (rutas por rol, plantillas, pruebas)
```

## Ejecutar la interfaz web

Requisitos: Python 3.14 (versión con la que se probó) y la API desplegada (ver el [manual de despliegue](docs/manual_despliegue.md)).

```bash
cd frontend
python -m venv ../venv
../venv/Scripts/activate          # Windows (en Linux/macOS: source ../venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # y llena los valores
python app.py                     # http://127.0.0.1:5000
```

Variables de `frontend/.env` (el archivo está en `.gitignore`):

| Variable | Valor |
|---|---|
| `API_BASE_URL` | URL de API Gateway, `https://…`, sin `/` al final. Cambia con cada sesión del Learner Lab |
| `SECRET_KEY` | 32 caracteres o más: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `COOKIE_SECURE` | Vacío. Escribe `false` solo si el navegador rechaza la cookie en `http://localhost` |

Flask no guarda credenciales de la base de datos ni de AWS: solo habla con API Gateway.

## Pruebas locales

Las pruebas de la interfaz simulan la API, así que no necesitan AWS:

```bash
cd frontend
pip install -r requirements-dev.txt
python -m pytest
```

Para la base de datos, los scripts de `database/` se pueden probar en un MySQL 8.0 local. El orden y la validación están en [database/README.md](database/README.md). Las fichas de [backend/LAMBDAS.md](backend/LAMBDAS.md) incluyen un evento de prueba para la pestaña *Test* de la consola de Lambda.

## Despliegue en AWS

Paso a paso en [docs/manual_despliegue.md](docs/manual_despliegue.md): RDS, DynamoDB con sus índices, Layers, Lambdas con LabRole y variables de entorno, API Gateway, primer administrador y prueba de humo.

## Documentación

- [Arquitectura y C4](docs/arquitectura.md)
- [Diagrama entidad-relación](docs/DER.png)
- [API (OpenAPI 3)](docs/openapi.json): se puede abrir en [editor.swagger.io](https://editor.swagger.io)
- [Base de datos y stored procedures](database/README.md)
- [Fichas de las Lambdas](backend/LAMBDAS.md)
