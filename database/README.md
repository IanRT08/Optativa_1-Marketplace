# Base de datos SMAVIB

Base de datos híbrida. **MySQL 8.0 en Amazon RDS** es la fuente de verdad de usuarios, inventario, carrito, pedidos y pagos: 16 tablas y 4 stored procedures. **Amazon DynamoDB** guarda el catálogo de búsqueda: la tabla `Productos`, con 17,000 ítems.

## Scripts MySQL (ejecutar en este orden)

| Archivo | Contenido | ¿Se puede repetir? |
|---|---|---|
| `01_tablas.sql` | Crea la base `marketplace` y sus 16 tablas (PK, FK, UNIQUE, CHECK e índices de consulta). Carga los catálogos fijos: roles, estados de pedido y atributos | Sí |
| `02_stored_procedures.sql` | `sp_RegistrarCompra`, `sp_CancelarPedido`, `sp_HistorialVentas`, `sp_ActualizarStockMasivo` | Sí (`DROP PROCEDURE IF EXISTS`) |
| `03_vendedores_carga.sql` | Crea los 4 vendedores dueños de la carga. No pueden iniciar sesión: no tienen un hash bcrypt válido | Sí |
| `04_carga_inicial.sql` | Carga 27 marcas, 12 categorías, valores de atributo y **17,000 productos**, cada uno con su variante estándar | Sí: no vuelve a insertar si ya hay 17,000 productos o más |
| `05_pruebas_sp.sql` | Pruebas manuales de los 4 SPs, con IDs 9001 en adelante. Limpia todo al terminar | Sí |

Con el cliente `mysql`:

```bash
mysql -h <endpoint-rds> -u <usuario> -p --comments < 01_tablas.sql
mysql -h <endpoint-rds> -u <usuario> -p --comments < 02_stored_procedures.sql
mysql -h <endpoint-rds> -u <usuario> -p marketplace < 03_vendedores_carga.sql
mysql -h <endpoint-rds> -u <usuario> -p marketplace < 04_carga_inicial.sql
```

- `--comments` conserva los comentarios dentro de los SPs.
- En DataGrip o MySQL Workbench, ejecuta cada archivo completo.
- `05_pruebas_sp.sql` va **bloque por bloque**. Los bloques marcados "DEBE FALLAR" lanzan a propósito el error del DFR.

**Validación (2026-11-16, MySQL 8.0.44 local):**
- `01` y `02` se ejecutan sin errores y se pueden repetir.
- El esquema de tablas es idéntico al del script fuente del proyecto.
- El código de los 4 SPs también es idéntico.
- `04` carga 17,000 productos y 17,000 variantes.
- Los 14 casos de `05` que deben fallar responden con su mensaje exacto del DFR.

## Stored procedures

| SP | Requerimiento | Qué hace en una transacción |
|---|---|---|
| `sp_RegistrarCompra(p_id_usuario, p_id_direccion, p_token, p_ultimos4, OUT p_id_pedido)` | DFR 6.1 | Crea el pedido y su detalle con el precio histórico, descuenta stock, registra el pago tokenizado y vacía el carrito. Bloquea el carrito con `FOR UPDATE` (evita una compra doble). Si algo falla, hace `ROLLBACK` |
| `sp_CancelarPedido(p_id_pedido, p_nuevo_estado)` | DFR 7.3 | Pasa el pedido a Cancelado o Devuelto, repone el stock de cada variante y marca el pago como Reembolsado |
| `sp_HistorialVentas(p_id_usuario, p_tipo, p_fecha_inicio, p_fecha_fin)` | DFR 7.4, 8.1, 8.2 | Historial consolidado con `WITH ROLLUP`. `p_tipo` es `'Comprador'` (por pedido) o `'Vendedor'` (por producto). Los pedidos Cancelados y Devueltos no suman |
| `sp_ActualizarStockMasivo(p_id_vendedor, p_id_categoria, p_cantidad)` | DFR 3.5 | Suma la cantidad a todas las variantes de los productos del vendedor en la categoría |

Los errores de negocio salen con `SIGNAL SQLSTATE '45000'` y el texto exacto del DFR. Las Lambdas los devuelven con estado 400.

## DynamoDB: tabla `Productos`

- `dynamodb/productos_esquema.json`: llave, atributos indexados y los dos índices secundarios globales (GSI) con su proyección. Tiene el formato de la API de DynamoDB y **sirve como documentación del esquema**; la tabla se configura en la consola (ver `docs/manual_despliegue.md`).
- `dynamodb/productos_item_ejemplo.json`: un ítem completo con el estándar del proyecto.

| Llave | Tipo | Valor |
|---|---|---|
| `productoID` (partición) | S | `id_producto` de MySQL, como texto |

| Índice (GSI) | Partición | Ordenación | Consulta que resuelve (DFR 4.1) |
|---|---|---|---|
| `EstadoPrecio` | `Estado` (S) | `Precio` (N) | Catálogo de productos Activos ordenado por precio, con filtro de rango de precio y palabra clave (`NombreBusqueda`) |
| `CategoriaPrecio` | `CategoriaID` (N) | `Precio` (N) | Lo mismo, dentro de una categoría |

Los dos índices proyectan solo lo que muestra la tarjeta del catálogo. Así la consulta no lee el ítem completo y consume menos capacidad. El stock exacto **siempre se lee de RDS**: `Stock` y `Variantes[].Stock` en DynamoDB son una copia de referencia que los SPs no actualizan.
