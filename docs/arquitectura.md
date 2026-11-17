# Arquitectura de SMAVIB

Marketplace sobre **AWS Academy Learner Lab** (región `us-east-1`). Flujo único:

**Navegador → Flask → Amazon API Gateway → AWS Lambda → Amazon RDS (MySQL) y Amazon DynamoDB**

GitHub muestra los diagramas de este archivo como imágenes (Mermaid).

## 1. Diagrama de arquitectura AWS

```mermaid
flowchart LR
    U["Navegador<br/>(Comprador · Vendedor · Administrador)"]
    F["Servidor web Flask (Vercel)<br/>sesión del lado del servidor · CSRF · CSP<br/>API_BASE_URL en variable de entorno"]
    R[("Upstash Redis<br/>sesiones de Flask (vencen a las 2 h)")]

    subgraph AWS["AWS Learner Lab · us-east-1 · rol LabRole"]
        APIGW["Amazon API Gateway<br/>35 rutas REST (HTTPS)"]
        subgraph L["AWS Lambda · Python 3.14 · 128-256 MB"]
            LP["lambda-consultarProductos<br/>(4.1, sin VPC)"]
            LR["34 Lambdas de negocio<br/>Layer 1: PyMySQL, bcrypt, PyJWT<br/>Layer 2: smavib_common.py"]
            LC["lambda-cargaDynamo<br/>(carga única, sin API Gateway;<br/>se borra al terminar)"]
        end
        subgraph VPC["VPC"]
            RDS[("Amazon RDS · MySQL 8.0<br/>BD marketplace: 16 tablas<br/>4 stored procedures")]
            EP["VPC Gateway Endpoint<br/>de DynamoDB"]
        end
        DDB[("Amazon DynamoDB<br/>tabla Productos (bajo demanda)<br/>GSI EstadoPrecio · CategoriaPrecio")]
        CW["Amazon CloudWatch Logs"]
    end

    U -- "HTTPS (cookie de sesión HttpOnly)" --> F
    F -- "rediss:// (TLS)" --> R
    F -- "HTTPS + Authorization: Bearer JWT" --> APIGW
    APIGW --> LP
    APIGW --> LR
    LR -- "3306 (solo desde el SG de las Lambdas)" --> RDS
    LR -- "GetItem · UpdateItem · BatchGetItem" --> EP --> DDB
    LP -- "Query sobre GSI" --> DDB
    LC --> RDS
    LC -- "BatchWriteItem" --> EP
    L -. "print / errores" .-> CW
```

| Componente | Decisión | Motivo |
|---|---|---|
| API Gateway | Una ruta por requerimiento del DFR (35); sin authorizer | Cada Lambda valida el JWT y el rol con `smavib_common.validar_token` |
| Lambda | Una función por requerimiento; conexión MySQL creada fuera del handler y reutilizada; reconexión si se cae | Menos conexiones a RDS y menor latencia en invocaciones calientes |
| Red | Las Lambdas que usan RDS van en la VPC. El grupo de seguridad de RDS acepta el puerto 3306 solo desde el de las Lambdas. DynamoDB se alcanza por el VPC Gateway Endpoint | Sin NAT Gateway ni RDS Proxy (costo en el Learner Lab) |
| Secretos | `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `JWT_SECRET` y `TABLA_PRODUCTOS` en variables de entorno de cada Lambda. Flask solo tiene `API_BASE_URL`, `SECRET_KEY` y, en Vercel, `REDIS_URL` | Nada de credenciales en el código. Sin Secrets Manager (costo) |
| RDS | Fuente de verdad de usuarios, stock, carrito, pedidos y pagos. Transacciones en stored procedures | Integridad y atomicidad (rubro 3) |
| DynamoDB | Catálogo de búsqueda de 17,000 productos, bajo demanda, con 2 GSI con proyección parcial | Búsqueda por precio y categoría sin cargar RDS |
| Costos | Lambda de 128 a 256 MB, RDS micro y apagado fuera de horario, DynamoDB bajo demanda | Restricciones del Learner Lab (lineamientos §1) |
| Interfaz web | Flask en Vercel; sesión en Upstash Redis (plan gratuito) con conexión cifrada (`rediss://`). En local, la sesión se guarda en archivos | En Vercel el disco es de solo lectura y no se comparte entre instancias. El JWT sigue sin llegar al navegador |

## 2. C4 · Nivel 1: contexto

```mermaid
flowchart TB
    C["Comprador<br/>[Persona]<br/>Busca productos, compra y consulta sus pedidos"]
    V["Vendedor<br/>[Persona]<br/>Administra sus productos, stock y ventas"]
    A["Administrador<br/>[Persona]<br/>Gestiona usuarios, categorías y pedidos"]
    S["SMAVIB<br/>[Sistema]<br/>Marketplace web sobre AWS"]
    C --> S
    V --> S
    A --> S
    classDef persona fill:#00525A,color:#FFFFFF,stroke:#002A2E
    classDef sistema fill:#002A2E,color:#FFFFFF,stroke:#002A2E
    class C,V,A persona
    class S sistema
```

No hay sistemas externos de negocio (la interfaz se aloja en Vercel y su sesión en Upstash Redis, que son infraestructura): el pago es simulado y tokenizado. Solo se guardan un token aleatorio y los últimos 4 dígitos; nunca la tarjeta completa ni el CVV.

## 3. C4 · Nivel 2: contenedores

```mermaid
flowchart TB
    P["Usuarios<br/>[Personas: Comprador, Vendedor, Administrador]"]
    subgraph SMAVIB["SMAVIB [Sistema]"]
        WEB["Aplicación web<br/>[Contenedor: Python 3 · Flask · Jinja, en Vercel]<br/>Pantallas por rol, DTOs de validación,<br/>sesión en el servidor (Flask-Session)"]
        SES[("Sesiones<br/>[Contenedor: Upstash Redis]<br/>id de sesión → JWT y datos del usuario")]
        API["API REST<br/>[Contenedor: Amazon API Gateway]<br/>35 rutas, JSON"]
        FN["Funciones de negocio<br/>[Contenedor: AWS Lambda · Python 3.14]<br/>JWT + RBAC, validaciones del DFR"]
        SQL[("Base transaccional<br/>[Contenedor: MySQL 8.0 en RDS]<br/>16 tablas, 4 stored procedures")]
        NOSQL[("Catálogo<br/>[Contenedor: DynamoDB]<br/>Productos + 2 GSI")]
    end
    P -- "HTTPS" --> WEB
    WEB -- "rediss:// (TLS)" --> SES
    WEB -- "HTTPS/JSON + JWT" --> API
    API -- "Invocación proxy" --> FN
    FN -- "SQL parametrizado / CALL sp_*" --> SQL
    FN -- "boto3" --> NOSQL
```

## 4. Seguridad por capa (rubro 4)

| Capa | Control |
|---|---|
| Navegador ↔ Flask | Cookie `HttpOnly`, `Secure` y `SameSite=Lax`. El JWT vive solo en el servidor. CSRF en cada POST. CSP sin scripts ni estilos inline. Además, `X-Frame-Options: DENY` y `nosniff` |
| Flask | Rutas protegidas por rol (`rol_requerido`). Jinja escapa toda salida (sin `|safe`), lo que previene XSS. Redirecciones solo a rutas internas. Los DTOs validan la forma de los datos |
| API / Lambda | JWT HS256 de 2 horas validado en cada Lambda. Rol permitido por función (403 "Acceso restringido"). La identidad sale del token, nunca del body. Cada usuario solo ve sus propios datos |
| Datos | Consultas parametrizadas con `%s` de PyMySQL, sin concatenar texto del usuario, lo que evita inyección SQL. Contraseñas con bcrypt generado en Lambda. Pago tokenizado. Bajas lógicas de usuarios, productos y direcciones |
