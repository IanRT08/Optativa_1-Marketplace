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

### 5b. Concurrencia sobre la última unidad (rubro 3, opcional)

Datos: la variante de 3.6, con stock 1, y dos compradores (A y B) en ventanas distintas.

| # | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|
| 5b.1 | A y B agregan la variante (1 unidad) a su carrito | Ambos: "Producto agregado al carrito" | | |
| 5b.2 | A paga | "Compra realizada correctamente" | | |
| 5b.3 | B paga | "Stock insuficiente para el producto [nombre]" (el SP bloquea las filas con `FOR UPDATE` y revisa el stock dentro de la transacción) | | |

## 6. Administrador: pedidos, estados y reportes

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 6.1 | A3 | Pedidos | Abre filtrado en Pendiente; aparecen los pedidos A y B | | |
| 6.2 | 7.2 | Detalle del pedido A | Comprador, ciudad, estado y CP; **sin datos de pago** | | |
| 6.3 | 7.3 | Pedido A: Pendiente → Enviado | "Estado del pedido actualizado correctamente" | | |
| 6.4 | 7.3 | Pedido A: Enviado → Entregado | "Estado del pedido actualizado correctamente"; ya no se ofrece Enviado ni Pendiente | | |
| 6.5 | 7.3 | **SP `sp_CancelarPedido`:** pedido B → Cancelado | "Estado del pedido actualizado correctamente" | | |
| 6.6 | 3.2 | Como vendedor, revisar el stock del producto | Regresó la unidad del pedido B | | |
| 6.7 | 8.2 | **SP `sp_HistorialVentas` ('Vendedor'):** ventas del vendedor de 2.1, fechas de hoy | Aparece el producto con las unidades del pedido A; el cancelado B no suma | | |
| 6.8 | 8.2 | Fecha inicial mayor que la final | "La fecha inicial no puede ser mayor a la fecha final" | | |
| 6.9 | 2.3 | Editar `Pruebas SMAVIB` y elegirla como su propia categoría padre | "Una categoría no puede ser su propia categoría padre" | | |
| 6.10 | 2.4 | Eliminar `Pruebas SMAVIB` (tiene productos) | "No se puede eliminar una categoría con productos asociados" | | |
| 6.11 | 2.4 | Eliminar `<b>Prueba XSS</b>` | "Categoría eliminada correctamente" | | |
| 6.12 | 1.6 | Eliminar al comprador B (o una cuenta de prueba) | "Usuario eliminado correctamente"; en la lista queda Inactivo (baja lógica) | | |
| 6.13 | 1.2 | Iniciar sesión con esa cuenta | "La cuenta se encuentra inactiva" | | |
| 6.14 | RBAC | Como Comprador, abrir `/admin/usuarios` | Página "Acceso restringido" | | |

## 7. Vendedor y Comprador: reportes e historial

| # | Req. | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|---|
| 7.1 | 8.1 | **SP `sp_HistorialVentas` ('Vendedor'):** como vendedor, Mis ventas de hoy | Mismo total que en 6.7 | | |
| 7.2 | 7.1 | Como comprador A, Mis pedidos | A en Entregado y B en Cancelado | | |
| 7.3 | 7.1 | Filtrar por estado Cancelado | Solo el pedido B | | |
| 7.4 | 7.2 | Detalle del pedido A | Productos, precio unitario histórico, dirección completa y últimos 4 dígitos | | |
| 7.5 | 7.2 | **Solo sus datos:** abrir `/pedidos/<id>` de un pedido de otro comprador | "Acceso restringido" | | |
| 7.6 | 7.4 | **SP `sp_HistorialVentas` ('Comprador'):** historial de hoy | Pedidos A y B; B marcado "(no suma)"; "Total comprado" = total de A | | |

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
```

| # | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|
| 8.1 | `prefijo` = `$2b$` y `largo` = 60 en todas las cuentas creadas | | |
| 8.2 | `token` empieza con `tok_`; `ultimos4` = `1111` | | |
| 8.3 | Pedido A Entregado con pago "Aprobado"; pedido B Cancelado con pago "Reembolsado" | | |

## 9. Interfaz (cookie y token)

| # | Pasos | Resultado esperado | Resultado | Evidencia |
|---|---|---|---|---|
| 9.1 | DevTools → Application → Cookies, con sesión iniciada | Solo `smavib_sesion`, con HttpOnly, Secure y SameSite=Lax; el JWT no aparece en cookies, `localStorage` ni el HTML | | |
| 9.2 | Cerrar sesión y usar "Atrás" del navegador | No muestra datos de la sesión anterior (`Cache-Control: no-store`) | | |
