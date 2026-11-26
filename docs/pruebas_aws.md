# Reporte de pruebas contra AWS

Pruebas de punta a punta de SMAVIB contra la API real de AWS (API Gateway → Lambda → RDS y DynamoDB), desde la interfaz desplegada y desde AWS CloudShell. Son la evidencia de los rubros 3 ("probados y funcionan correctamente desde la aplicación") y 4 ("protección demostrada") de los lineamientos. Las pruebas automáticas sin AWS están en `frontend/tests/` y corren en el CI.

Cada prueba indica el resultado esperado, el resultado obtenido (✅ correcto, ❌ con la falla observada) y la captura correspondiente en [`evidencias/`](evidencias/).

| Dato | Valor |
|---|---|
| Fecha de ejecución | 17/11/2026 |
| Ejecutó | Ian Alejandro Rivera Torres |
| Entorno de la interfaz | https://optativa-1-marketplace.vercel.app |
| Commit probado | `2e13f8e` |

## 0. Condiciones de ejecución

- AWS Academy Learner Lab y la instancia de RDS encendidos.
- Cuenta de **Administrador** creada como indica el [manual §5](manual_despliegue.md#5-primer-administrador). Las cuentas de Vendedor y de Comprador se crean durante las pruebas.
- Tarjeta de prueba: `4111 1111 1111 1111`, CVV `123`. El pago es simulado: no se cobra y la tarjeta no se guarda.
- Sección 1: variable `URL` de CloudShell con la URL base de API Gateway.

## 1. Seguridad sin sesión (rubro 4, desde CloudShell)

Resultado esperado en las 5 pruebas: **401** con `{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"}`.

| # | Prueba | Comando | Resultado | Evidencia |
|---|---|---|---|---|
| 1.1 | Eliminar categoría sin token | `curl -s -w " %{http_code}\n" -X DELETE $URL/categorias/1` | ✅ | [01-sin-token.png](evidencias/01-sin-token.png) |
| 1.2 | Desactivar usuario sin token | `curl -s -w " %{http_code}\n" -X PATCH $URL/admin/usuarios/1/desactivar` | ✅ | [01-sin-token.png](evidencias/01-sin-token.png) |
| 1.3 | Editar producto sin token | `curl -s -w " %{http_code}\n" -X PUT $URL/vendedor/productos/9003 -d '{}'` | ✅ | [01-sin-token.png](evidencias/01-sin-token.png) |
| 1.4 | Comprar sin token | `curl -s -w " %{http_code}\n" -X POST $URL/compras -d '{}'` | ✅ | [01-sin-token.png](evidencias/01-sin-token.png) |
| 1.5 | Token falsificado | `curl -s -w " %{http_code}\n" $URL/carrito -H "Authorization: Bearer abc.def.ghi"` | ✅ | [01-sin-token.png](evidencias/01-sin-token.png) |

Salida obtenida:

```
1.1 DELETE categoria:
{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"} 401
1.2 PATCH desactivar usr:
{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"} 401
1.3 PUT producto:
{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"} 401
1.4 POST compras:
{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"} 401
1.5 token falso:
{"error": "Tu sesión no es válida o ya venció. Inicia sesión nuevamente"} 401
```

## 2. Administrador: usuarios y categorías

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 2.1 | 1.3 | Usuarios → Nuevo: rol **Vendedor**, correo nuevo, contraseña válida | "Usuario creado exitosamente" | ✅ | [2.1-crearUsuario.png](evidencias/2.1-crearUsuario.png) |
| 2.2 | 1.3 | Repetir con el mismo correo | "El correo electrónico ya está registrado" | ✅ | [2.2-correoYaRegistrado.png](evidencias/2.2-correoYaRegistrado.png) |
| 2.3 | 1.3 | Contraseña `abc` | "La contraseña debe tener mínimo 8 caracteres, una mayúscula, un número y un carácter especial" | ✅ | [2.3-contraseniaABC.png](evidencias/2.3-contraseniaABC.png) |
| 2.4 | 1.4 | Filtrar por rol Vendedor | Aparece el vendedor de 2.1; sin `password_hash` | ✅ | [2.4-filtrarRolVendedor.png](evidencias/2.4-filtrarRolVendedor.png) |
| 2.5 | 1.5 | Editar el apellido del vendedor | "Usuario actualizado correctamente" | ✅ | [2.5-editarApellidoVendedor.png](evidencias/2.5-editarApellidoVendedor.png) |
| 2.6 | 1.5 | Editar tu propia cuenta | No aparecen los campos de rol ni de estado | ✅ | [2.6-editarCuentaPropia.png](evidencias/2.6-editarCuentaPropia.png) |
| 2.7 | 2.1 | Categorías → Nueva: `Libros` | "Categoría creada correctamente" | ✅ | [2.7-crearCategoria.png](evidencias/2.7-crearCategoria.png) |
| 2.8 | 2.1 | Repetir el mismo nombre | "La categoría ya existe" | ✅ | [2.8-nombreCategoriaExistente.png](evidencias/2.8-nombreCategoriaExistente.png) |
| 2.9 | 2.1 | **XSS:** nueva categoría `<b>Prueba XSS</b>` | Se crea y el texto se ve tal cual, **sin negritas** (Jinja escapa la salida) | ✅ | [2.9-pruebaXSS.png](evidencias/2.9-pruebaXSS.png) |
| 2.10 | 2.2 | Ver la lista de categorías | Aparecen las dos nuevas | ✅ | [2.10-listaCategorias.png](evidencias/2.10-listaCategorias.png) |

## 3. Vendedor: productos y stock masivo

Sesión: el vendedor creado en 2.1.

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 3.1 | 3.1 | Nuevo producto en `Pruebas SMAVIB`, precio `0` | "El precio debe ser mayor a cero" | ✅ | [3.1-precioMayor0.png](evidencias/3.1-precioMayor0.png) |
| 3.2 | 3.1 | Stock `-1` | "El stock no puede ser negativo" | ✅ | [3.2-stockNegativo.png](evidencias/3.2-stockNegativo.png) |
| 3.3 | 3.1 | Producto válido: precio `28499`, stock `20`, URL de imagen https | "Producto registrado correctamente" | ✅ | [3.3-productoRegistrado.png](evidencias/3.3-productoRegistrado.png) |
| 3.4 | 3.2 | Mis productos | El producto aparece Activo con stock 20 | ✅ | [3.4-misProductos.png](evidencias/3.4-misProductos.png) |
| 3.5 | 3.2 | **Inyección SQL:** buscar `' OR '1'='1` | "No se encontraron registros" (no lista todos los productos) | ✅ | [3.5-inyeccionSQL.png](evidencias/3.5-inyeccionSQL.png) |
| 3.6 | 3.6 | Variantes: elegir una talla/color, stock `1` | "Variante registrada correctamente" | ✅ | [3.6-varianteRegistrada.png](evidencias/3.6-varianteRegistrada.png) |
| 3.7 | 3.6 | Repetir la misma combinación | "La variante ya existe para este producto" | ✅ | [3.7-varianteRepetida.png](evidencias/3.7-varianteRepetida.png) |
| 3.8 | 3.3 | Editar el precio a `459.90` | "Producto actualizado correctamente" | ✅ | [3.8-actualizarProducto.png](evidencias/3.8-actualizarProducto.png) |
| 3.9 | 3.3 | **Solo sus datos:** abrir `/vendedor/productos/9003/editar` (producto de otro vendedor) y guardar | "Acceso restringido" | ✅ | [3.9-actualizarProductoOtroVendedor.png](evidencias/3.9-actualizarProductoOtroVendedor.png) |
| 3.10 | 3.5 | **SP `sp_ActualizarStockMasivo`:** Stock masivo, categoría `Pruebas SMAVIB`, cantidad `0` | "La cantidad debe ser mayor a cero" (mensaje del SP) | ✅ | [3.10-actualizarStockMasivo0.png](evidencias/3.10-actualizarStockMasivo0.png) |
| 3.11 | 3.5 | Misma categoría, cantidad `5` | "Stock actualizado correctamente"; en Mis productos el stock subió | ✅ | [3.11-actualizarStockMasivo5.png](evidencias/3.11-actualizarStockMasivo5.png) |
| 3.12 | 3.4 | Desactivar el producto | "Estado del producto actualizado correctamente" | ✅ | [3.12-desactivarProducto.png](evidencias/3.12-desactivarProducto.png) |
| 3.13 | 4.2 | Sin sesión, abrir `/productos/<id>` | "Este producto ya no está disponible" | ✅ | [3.13-intertarVerProductoDesactivado.png](evidencias/3.13-intertarVerProductoDesactivado.png) |
| 3.14 | 3.4 | Volver a activarlo | "Estado del producto actualizado correctamente" | ✅ | [3.14-volverActivarProducto.png](evidencias/3.14-volverActivarProducto.png) |

## 4. Visitante: catálogo

Sin sesión (ventana privada).

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 4.1 | 4.1 | Abrir el catálogo y pasar a la página siguiente | 20 productos por página, ordenados por precio | ✅ | [4.1-abrirCatalogoPaginaSiguiente.png](evidencias/4.1-abrirCatalogoPaginaSiguiente.png) |
| 4.2 | 4.1 | Filtrar por la categoría `Celulares` | Aparece el producto de 3.3 | ✅ | [4.2-filtrarPorCategoria.png](evidencias/4.2-filtrarPorCategoria.png) |
| 4.3 | 4.1 | Precio mínimo `500`, máximo `100` | "El precio mínimo no puede ser mayor al máximo" | ✅ | [4.3-buscarPrecioMinimoMaximo.png](evidencias/4.3-buscarPrecioMinimoMaximo.png) |
| 4.4 | 4.1 | Buscar `zzzz` | "No se encontraron productos" | ✅ | [4.4-buscarProductoZZZZ.png](evidencias/4.4-buscarProductoZZZZ.png) |
| 4.5 | 4.2 | Detalle del producto | Muestra "Disponible", no el número de unidades | ✅ | [4.5-detalleProductoSinSesion.png](evidencias/4.5-detalleProductoSinSesion.png) |
| 4.6 | 5.1 | "Agregar al carrito" sin sesión | Manda al inicio de sesión y, al entrar, regresa al producto | ✅ | [4.6-agregarAlCarritoSinSesion.png](evidencias/4.6-agregarAlCarritoSinSesion.png) |

## 5. Comprador: registro, direcciones, carrito y compra

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 5.1 | 1.1 | Registro con contraseñas distintas | "Las contraseñas no coinciden" | ✅ | [5.1-registroContrasenasDiferentes.png](evidencias/5.1-registroContrasenasDiferentes.png) |
| 5.2 | 1.1 | Registro válido (comprador A) | Entra con la sesión iniciada al catálogo | ✅ | [5.2-registroExitoso.png](evidencias/5.2-registroExitoso.png) |
| 5.3 | 1.2 | Cerrar sesión y entrar con contraseña incorrecta | "Contraseña incorrecta" | ✅ | [5.3-iniciarSesionContraseniaIncorrecta.png](evidencias/5.3-iniciarSesionContraseniaIncorrecta.png) |
| 5.4 | 1.2 | **Inyección SQL:** correo `a@a.com' OR '1'='1` | "El formato del correo electrónico no es válido" | ✅ | [5.4-inyeccionSQLregistro.png](evidencias/5.4-inyeccionSQLregistro.png) |
| 5.5 | 9.1 | Nueva dirección con código postal 4 digitos | "El código postal debe tener 5 dígitos" | ✅ | [5.5-nuevaDireccionCP4digitos.png](evidencias/5.5-nuevaDireccionCP4digitos.png) |
| 5.6 | 9.1 | Dirección válida | "Dirección registrada correctamente" | ✅ | [5.6-direccionValida.png](evidencias/5.6-direccionValida.png) |
| 5.7 | 9.2 | Mis direcciones | Aparece la dirección | ✅ | [5.7-misDirecciones.png](evidencias/5.7-misDirecciones.png) |
| 5.8 | 4.2 | Detalle del producto de 3.3 con sesión | Muestra el stock exacto ("N unidades") | ✅ | [5.8-detalleProductoConSesion.png](evidencias/5.8-detalleProductoConSesion.png) |
| 5.9 | 5.1 | Agregar más unidades que el stock | "La cantidad solicitada supera el stock disponible" | ✅ | [5.9-masStockdelDisponible.png](evidencias/5.9-masStockdelDisponible.png) |
| 5.10 | 5.1 | Agregar 2 unidades de la variante estándar | "Producto agregado al carrito" | ✅ | [5.10-agregar2Unidades.png](evidencias/5.10-agregar2Unidades.png) |
| 5.11 | 5.1 | Agregar 1 unidad de otro producto cualquiera | "Producto agregado al carrito" | ✅ | [5.11-agregarOtroProductoAlCarrito.png](evidencias/5.11-agregarOtroProductoAlCarrito.png) |
| 5.12 | 5.3 | Cambiar la cantidad del primero a 3 | "Carrito actualizado correctamente" | ✅ | [5.12-cambiarCantidadCarrito1.png](evidencias/5.12-cambiarCantidadCarrito1.png) |
| 5.13 | 5.4 | Quitar el segundo producto | "Producto/s eliminado/s del carrito" | ✅ | [5.13-quitarProductoCarrito.png](evidencias/5.13-quitarProductoCarrito.png) |
| 5.14 | 6.1 | Pagar con tarjeta de 15 dígitos | "Datos de pago no válidos" | ✅ | [5.14-tarjeta15Digitos.png](evidencias/5.14-tarjeta15Digitos.png) |
| 5.15 | 6.1 | **SP `sp_RegistrarCompra`:** pagar con la tarjeta de prueba (**pedido A**) | "Compra realizada correctamente" con número de orden y total | ✅ | [5.15-compraCorrecta.png](evidencias/5.15-compraCorrecta.png) |
| 5.16 | 4.2 | Ver el detalle del producto | El stock bajó 3 unidades | ✅ | [5.16-bajoStockProducto.png](evidencias/5.16-bajoStockProducto.png) |
| 5.17 | 5.2 | Ver el carrito | "Tu carrito está vacío" | ✅ | [5.17-carritoVacioDespuesDeCompra.png](evidencias/5.17-carritoVacioDespuesDeCompra.png) |
| 5.18 | 6.1 | Agregar 1 unidad y pagar (**pedido B**, se cancela en 6.5) | "Compra realizada correctamente" | ✅ | [5.18-pedidoBparaCancelar.png](evidencias/5.18-pedidoBparaCancelar.png) |

## 6. Administrador: pedidos, estados y reportes

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 6.1 | A3 | Pedidos | Abre filtrado en Pendiente; aparecen los pedidos A y B | ✅ | [6.1-pedidosPendientes.png](evidencias/6.1-pedidosPendientes.png) |
| 6.2 | 7.2 | Detalle del pedido A | Comprador, ciudad, estado y CP; **sin datos de pago** | ✅ | [6.2-detalleDePedido.png](evidencias/6.2-detalleDePedido.png) |
| 6.3 | 7.3 | Pedido A: Pendiente → Enviado | "Estado del pedido actualizado correctamente" | ✅ | [6.3-cambioEstadoPredidoEnviado.png](evidencias/6.3-cambioEstadoPredidoEnviado.png) |
| 6.4 | 7.3 | Pedido A: Enviado → Entregado | "Estado del pedido actualizado correctamente"; ya no se ofrece Enviado ni Pendiente | ✅ | [6.4-cambioEstadoPedidoEntregado.png](evidencias/6.4-cambioEstadoPedidoEntregado.png) |
| 6.5 | 7.3 | **SP `sp_CancelarPedido`:** pedido B → Cancelado | "Estado del pedido actualizado correctamente" | ✅ | [6.5-cambioEstadoPedidoCancelado.png](evidencias/6.5-cambioEstadoPedidoCancelado.png) |
| 6.6 | 3.2 | Como vendedor, revisar el stock del producto | Regresó la unidad del pedido B | ✅ | [6.6-regresoStock.png](evidencias/6.6-regresoStock.png) |
| 6.7 | 8.2 | **SP `sp_HistorialVentas` ('Vendedor'):** ventas del vendedor del producto del pedido A (se hizo con Tienda Centro, vendedor 9004 de la carga), fechas de hoy | Aparece el producto con las unidades del pedido A; el cancelado B no suma | ✅ | [6.7-historialVentas.png](evidencias/6.7-historialVentas.png) |
| 6.8 | 8.2 | Fecha inicial mayor que la final | "La fecha inicial no puede ser mayor a la fecha final" | ✅ | [6.8-fechaInicialMayor.png](evidencias/6.8-fechaInicialMayor.png) |
| 6.9 | 2.3 | Editar `Pruebas SMAVIB` y elegirla como su propia categoría padre | "Una categoría no puede ser su propia categoría padre" | ✅ | [6.9-categoriaPadreDeSiMisma.png](evidencias/6.9-categoriaPadreDeSiMisma.png) |
| 6.10 | 2.4 | Eliminar una categoria (que tiene productos) | "No se puede eliminar una categoría con productos asociados" | ✅ | [6.10-eliminarCategoriaConProductos.png](evidencias/6.10-eliminarCategoriaConProductos.png) |
| 6.11 | 2.4 | Eliminar `<b>Prueba XSS</b>` | "Categoría eliminada correctamente" | ✅ | [6.11-eliminarCategoriaXSS.png](evidencias/6.11-eliminarCategoriaXSS.png) |
| 6.12 | 1.6 | Eliminar al comprador B (o una cuenta de prueba) | "Usuario eliminado correctamente"; en la lista queda Inactivo (baja lógica) | ✅ | [6.12-eliminarUsuario.png](evidencias/6.12-eliminarUsuario.png) |
| 6.13 | 1.2 | Iniciar sesión con esa cuenta | "La cuenta se encuentra inactiva" | ✅ | [6.13-inicioSesionCuentaInactiva.png](evidencias/6.13-inicioSesionCuentaInactiva.png) |
| 6.14 | RBAC | Como Comprador, abrir `/admin/usuarios` | Página "Acceso restringido" | ✅ | [6.14-abrirUsuariosComoComprador.png](evidencias/6.14-abrirUsuariosComoComprador.png) |

## 7. Vendedor y Comprador: reportes e historial

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 7.1 | 8.1 | **SP `sp_HistorialVentas` ('Vendedor'):** como vendedor de 2.1, Mis ventas de hoy. Antes, como comprador A, comprar 1 unidad de su producto (el de 3.3; si no tiene stock, subirlo con 3.5): **pedido C** | El producto de 3.3 con 1 unidad y el total del pedido C. (Primer intento: "No hay ventas en el periodo seleccionado", porque los pedidos A y B eran de un producto de Tienda Centro) | ✅ | [7.1-misVentasHoy.png](evidencias/7.1-misVentasHoy.png) |
| 7.2 | 7.1 | Como comprador A, Mis pedidos | A en Entregado y B en Cancelado | ✅ | [7.2-misPedidos.png](evidencias/7.2-misPedidos.png) |
| 7.3 | 7.1 | Filtrar por estado Cancelado | Solo el pedido B | ✅ | [7.3-filtrarPorEstado.png](evidencias/7.3-filtrarPorEstado.png) |
| 7.4 | 7.2 | Detalle del pedido A | Productos, precio unitario histórico, dirección completa y últimos 4 dígitos | ✅ | [7.4-detallePedido.png](evidencias/7.4-detallePedido.png) |
| 7.5 | 7.2 | **Solo sus datos:** abrir `/pedidos/<id>` de un pedido de otro comprador | "Acceso restringido" | ✅ | [7.5-abrirPedidoQueNoEsTuyo.png](evidencias/7.5-abrirPedidoQueNoEsTuyo.png) |
| 7.6 | 7.4 | **SP `sp_HistorialVentas` ('Comprador'):** historial de hoy | Pedidos A y B; B marcado "(no suma)"; "Total comprado" = total de A | ✅ | [7.6-historialPedidos.png](evidencias/7.6-historialPedidos.png) |

## 8. Base de datos (DataGrip, rubros 3 y 4)

```sql
-- Contraseñas: solo hash bcrypt (empieza con $2b$ y mide 60)
SELECT id_usuario, email, LEFT(password_hash, 4) AS prefijo, CHAR_LENGTH(password_hash) AS largo
FROM usuario ORDER BY id_usuario DESC LIMIT 5;

-- Pago tokenizado: token aleatorio y últimos 4; no hay columna de tarjeta ni de CVV
SELECT id_pago, id_pedido, token, ultimos4, monto, estado FROM pago ORDER BY id_pago DESC LIMIT 5;

-- Estados y cancelación: el pago del pedido B queda "Reembolsado"
SELECT p.id_pedido, e.nombre AS estado, p.total, pg.estado AS pago
FROM pedido p
JOIN estado_pedido e ON e.id_estado = p.id_estado
LEFT JOIN pago pg ON pg.id_pedido = p.id_pedido
ORDER BY p.id_pedido DESC LIMIT 5;

-- Volumen del catálogo (lineamientos, Proyecto B: al menos 17,000 productos)
SELECT COUNT(*) AS productos_rds FROM producto;
```

Conteo de DynamoDB para 8.4, desde AWS CloudShell (la CLI recorre todas las páginas y suma el total):

```bash
aws dynamodb scan --table-name Productos --select COUNT --query Count
```

| # | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|
| 8.1 | `prefijo` = `$2b$` y `largo` = 60 en todas las cuentas creadas | ✅ | [8.1-contrasenaHasheada.png](evidencias/8.1-contrasenaHasheada.png) |
| 8.2 | `token` empieza con `tok_`; `ultimos4` = últimos 4 de la tarjeta usada (`4567` en los pedidos A, B y C; `4242` en el pedido 4 de las pruebas de humo) | ✅ | [8.2-pagoTokenizado.png](evidencias/8.2-pagoTokenizado.png) |
| 8.3 | Pedido A Entregado con pago "Aprobado"; pedido B Cancelado con pago "Reembolsado" | ✅ | [8.3-estadosYcancelacion.png](evidencias/8.3-estadosYcancelacion.png) |
| 8.4 | `productos_rds` ≥ 17,000 y el conteo de DynamoDB igual al de RDS (los productos creados en las pruebas también se escriben en DynamoDB) | ✅ | [8.4-conteoCatalogo.png](evidencias/8.4-conteoCatalogo.png), [8.4-conteoCatalogoDynamoDB.png](evidencias/8.4-conteoCatalogoDynamoDB.png) |

## 9. Interfaz (cookie y token)

| # | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|
| 9.1 | DevTools → Application → Cookies, con sesión iniciada | Solo `smavib_sesion`, con HttpOnly, Secure y SameSite=Lax; el JWT no aparece en cookies, `localStorage` ni el HTML | ✅ | [9.1-cookiesSesion.png](evidencias/9.1-cookiesSesion.png) |
| 9.2 | Cerrar sesión y usar "Atrás" del navegador | No muestra datos de la sesión anterior (`Cache-Control: no-store`) | ✅ | [9.2-atrasDespuesDeCerrarSesion.png](evidencias/9.2-atrasDespuesDeCerrarSesion.png) |

## 10. Concurrencia sobre la última unidad (rubro 3: "sin condiciones de carrera")

Dos compradores pagan **al mismo tiempo** el único artículo en stock. `sp_RegistrarCompra` bloquea la fila de la variante con `FOR UPDATE OF v` y revisa el stock dentro de la transacción. La segunda compra espera a que termine la primera, ya encuentra stock 0 y se revierte completa (`ROLLBACK`). Nunca deben salir dos pedidos ni stock negativo.

**Preparación (interfaz):** la compradora A de la sección 5 y una segunda cuenta de comprador (**comprador 2**, con correo `@smavib.test`), cada uno en su propia ventana privada. Los dos carritos deben empezar vacíos: el SP compra todo lo que haya en el carrito.

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 10.1 | 3.1 | Como vendedor, registrar el producto `Proyecto Hail Mary` en la categoría `Libros`, con **stock 1** | "Producto registrado correctamente" | ✅ | [10.1-productoNuevo.png](evidencias/10.1-productoNuevo.png) |
| 10.2 | 1.1, 9.1 | Registrar al comprador 2 y darle una dirección | "Dirección registrada correctamente" | ✅ | [10.2-nuevaDireccion.png](evidencias/10.2-nuevaDireccion.png) |
| 10.3 | 5.1 | La compradora A y el comprador 2 agregan 1 unidad de `Proyecto Hail Mary` a su carrito | Los dos: "Producto agregado al carrito" (el stock solo se descuenta al pagar) | ✅ | [10.3.1-agregarAlCarrito.png](evidencias/10.3.1-agregarAlCarrito.png), [10.3.2-agregarAlCarrito.png](evidencias/10.3.2-agregarAlCarrito.png) |
| 10.4 | 6.1 | **SP `sp_RegistrarCompra` en paralelo:** dos `POST /compras` lanzados a la vez desde CloudShell | Exactamente **una** respuesta `201` con "Compra realizada correctamente" y **una** `400` con "Stock insuficiente para el producto Proyecto Hail Mary" | ✅ | [10.4-comprasEnParalelo.txt](evidencias/10.4-comprasEnParalelo.txt) |
| 10.5 | 3.2 | Como vendedor, Mis productos | `Proyecto Hail Mary` con stock **0** (no -1) | ✅ | [10.5-stock0.png](evidencias/10.5-stock0.png) |
| 10.6 | 7.1, 5.2 | Ganador: Mis pedidos. Perdedor: Mis pedidos y Carrito | El ganador tiene el pedido nuevo. El perdedor no tiene pedido nuevo y su carrito conserva el producto (la transacción se revirtió) | ✅ | [10.6-stockInsuficiente.png](evidencias/10.6-stockInsuficiente.png) |


**Cómo se ejecutó 10.4.** Se iniciaron las dos sesiones con `POST /auth/login`, se revisó que cada carrito tuviera solo `Proyecto Hail Mary` (`GET /carrito`), se tomó la dirección de cada cuenta (`GET /direcciones`) y se lanzaron los dos `POST /compras` desde dos hilos liberados al mismo instante (`threading.Barrier`). Salieron con 11 ms de diferencia y las dos respuestas llegaron a los ~1.5 s: el comprador 2 salió primero, pero A obtuvo el bloqueo de la fila y el comprador 2 esperó y recibió el 400. El script no se incluye en el reporte; la salida está en la evidencia.

Cualquiera de los dos puede ganar: lo que se comprueba es que solo uno compra.

## 11. Reseñas

Sesión: el comprador A de la sección 5 (tiene el pedido A en estado Entregado con el producto de 3.3).

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 11.1 | Consultar | Sin sesión, abrir `/productos/<id>/resenas` del producto de 3.3 | Lista vacía: "Este producto aún no tiene reseñas"; el formulario de nueva reseña **no** aparece | ✅ | [11.1-resenas-sin-sesion.png](evidencias/11.1-resenas-sin-sesion.png) |
| 11.2 | Crear | Como comprador A, abrir la misma página | Aparece el formulario "Escribir una reseña" | ✅ | [11.2-formulario-resena.png](evidencias/11.2-formulario-resena.png) |
| 11.3 | Crear | Enviar el formulario con el comentario vacío | "Debe completar los campos obligatorios" debajo del campo correspondiente | ✅ | [11.3-resena-campos-vacios.png](evidencias/11.3-resena-campos-vacios.png) |
| 11.4 | Crear | Calificación 4, comentario válido | "Reseña publicada correctamente"; la reseña aparece en la lista con el nombre del comprador, 5 estrellas y la fecha de hoy | ✅ | [11.4-resena-creada.png](evidencias/11.4-resena-creada.png) |
| 11.5 | Crear | Intentar publicar una segunda reseña para el mismo producto | "Ya escribiste una reseña para este producto" | ✅ | [11.5-resena-duplicada.png](evidencias/11.5-resena-duplicada.png) |
| 11.6 | Crear | Como comprador 2 (de la sección 10, sin pedido Entregado con ese producto), intentar publicar una reseña | "Solo puedes reseñar productos que hayas recibido" | ✅ | [11.6-resena-sin-pedido.png](evidencias/11.6-resena-sin-pedido.png) |
| 11.7 | Editar | Como comprador A, abrir "Editar" en su reseña y cambiar la calificación a 4 | "Reseña actualizada correctamente"; la lista muestra 5 estrellas | ✅ | [11.7-resena-editada.png](evidencias/11.7-resena-editada.png) |
| 11.8 | Editar | **Solo sus datos:** como comprador 2, intentar editar la reseña del comprador A (PUT `/resenas/<id>` con token del comprador 2) | 403 "Acceso restringido" | ✅ | [11.8-editar-resena-ajena.png](evidencias/11.8-editar-resena-ajena.png) |
| 11.9 | Eliminar | Como Administrador, eliminar la reseña del comprador A | "Reseña eliminada correctamente"; la lista queda vacía | ✅ | [11.9-resena-eliminada-admin.png](evidencias/11.9-resena-eliminada-admin.png) |
| 11.10 | Promedio | Crear dos reseñas nuevas (comprador A: 4 estrellas; comprador 2, que ya tiene pedido Entregado del producto de 3.3 tras el pedido C de 7.1: 2 estrellas) | El promedio que aparece en la página es **3.0 / 5** | ✅ | [11.10-promedio-resenas.png](evidencias/11.10-promedio-resenas.png) |
| 11.11 | RBAC | Como Vendedor, intentar publicar una reseña | No aparece la opción | ✅ | [11.11-resena-como-vendedor.png](evidencias/11.11-resena-como-vendedor.png) |