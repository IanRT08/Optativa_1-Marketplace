-- 05_pruebas_sp.sql  (SMAVIB): pruebas manuales de los 4 stored procedures,
-- copiadas del script fuente. Usan IDs 9001+ y se limpian al final.
-- Ejecutar bloque por bloque (los marcados "DEBE FALLAR" fallan a propósito).
USE marketplace;

-- =====================================================================
-- PRUEBAS de los stored procedures v2
-- Ejecuta cada bloque por separado (selecciónalo y Ctrl+Enter), EN ORDEN y en la
-- misma consola (las variables @pedido y @pedido2 viven en la sesión).
-- Los bloques marcados "DEBE FALLAR" lanzan un error a propósito: es lo esperado.
-- Usa IDs 9001+ para no mezclarse con datos reales; al final se limpia todo.
-- Requiere ajustes_v2_tablas.sql y stored_procedures_v2.sql ya ejecutados,
-- y los catálogos cargados (roles y estados de pedido).
-- =====================================================================
-- ---------------------------------------------------------------------
-- 0. DATOS DE PRUEBA
-- ---------------------------------------------------------------------
INSERT INTO usuario (id_usuario, id_rol, nombre, apellido, email, password_hash) VALUES
    (9001, 2, 'Vendedor',  'Prueba', 'vendedor.prueba@test.com',  'x'),
    (9002, 3, 'Comprador', 'Prueba', 'comprador.prueba@test.com', 'x');
INSERT INTO direccion (id_direccion, id_usuario, calle, numero, colonia, ciudad, estado_region, codigo_postal) VALUES
    (9001, 9002, 'Calle Prueba', '10', 'Centro', 'Cuernavaca', 'Morelos', '62000'),  -- del comprador
    (9002, 9001, 'Calle Ajena',  '20', 'Centro', 'Cuernavaca', 'Morelos', '62000');  -- del vendedor
INSERT INTO categoria (id_categoria, nombre) VALUES (9001, 'Categoria Prueba'), (9002, 'Categoria Vacia Prueba');
INSERT INTO marca (id_marca, nombre) VALUES (9001, 'Marca Prueba');
INSERT INTO producto (id_producto, id_vendedor, id_categoria, id_marca, nombre, precio) VALUES
    (9001, 9001, 9001, 9001, 'Producto A', 100.00),
    (9002, 9001, 9001, 9001, 'Producto B', 250.50);
INSERT INTO variante_producto (id_variante, id_producto, sku, stock) VALUES
    (9001, 9001, 'TEST-A', 10),
    (9002, 9002, 'TEST-B', 5);
INSERT INTO carrito (id_carrito, id_usuario) VALUES (9001, 9002);
INSERT INTO carrito_detalle (id_carrito, id_variante, cantidad) VALUES
    (9001, 9001, 2),
    (9001, 9002, 1);

-- =====================================================================
-- sp_RegistrarCompra
-- =====================================================================

-- T1. Compra correcta. Esperado: pedido Pendiente, total 450.50
CALL sp_RegistrarCompra(9002, 9001, 'tok_test_0001', '4242', @pedido);
SELECT @pedido AS id_pedido;
SELECT * FROM pedido          WHERE id_pedido = @pedido;     -- total 450.50, id_direccion 9001
SELECT * FROM detalle_pedido  WHERE id_pedido = @pedido;     -- precios 100.00 y 250.50
SELECT * FROM pago            WHERE id_pedido = @pedido;     -- Aprobado, 450.50, ultimos4 4242, token (sin tarjeta ni CVV)
SELECT id_variante, stock FROM variante_producto WHERE id_variante IN (9001, 9002);   -- 8 y 4
SELECT COUNT(*) AS items_en_carrito FROM carrito_detalle WHERE id_carrito = 9001;     -- 0

-- T2. DEBE FALLAR: carrito vacío. Esperado: "Tu carrito está vacío"
CALL sp_RegistrarCompra(9002, 9001, 'tok_test_0002', '4242', @pedido_x);

-- T3. DEBE FALLAR: stock insuficiente y nada debe cambiar.
--     Esperado: "Stock insuficiente para el producto Producto A"
INSERT INTO carrito_detalle (id_carrito, id_variante, cantidad) VALUES (9001, 9001, 99);
CALL sp_RegistrarCompra(9002, 9001, 'tok_test_0002', '4242', @pedido_x);
-- Verificación del ROLLBACK:
SELECT COUNT(*) AS pedidos_del_comprador FROM pedido WHERE id_usuario = 9002;                        -- 1
SELECT COUNT(*) AS pagos FROM pago WHERE id_pedido IN (SELECT id_pedido FROM pedido WHERE id_usuario = 9002);  -- 1
SELECT stock FROM variante_producto WHERE id_variante = 9001;                                         -- 8

-- Deja el carrito con 1 unidad de Producto A para las siguientes pruebas
UPDATE carrito_detalle SET cantidad = 1 WHERE id_carrito = 9001 AND id_variante = 9001;

-- T4. DEBE FALLAR: dirección de otro usuario. Esperado: "La dirección de envío no es válida"
CALL sp_RegistrarCompra(9002, 9002, 'tok_test_0002', '4242', @pedido_x);

-- T5. DEBE FALLAR: datos de pago inválidos. Esperado: "Datos de pago no válidos"
CALL sp_RegistrarCompra(9002, 9001, 'tok_test_0002', 'abcd', @pedido_x);

-- T6. Segunda compra correcta (Producto A x1). Esperado: total 100.00; stock A = 7
CALL sp_RegistrarCompra(9002, 9001, 'tok_test_0002', '1111', @pedido2);
SELECT @pedido2 AS id_pedido2;
SELECT * FROM pedido WHERE id_pedido = @pedido2;
SELECT stock FROM variante_producto WHERE id_variante = 9001;   -- 7

-- =====================================================================
-- sp_HistorialVentas
-- =====================================================================

-- H1. Vendedor, hoy. Esperado: Producto A 3 uds = 300.00 | Producto B 1 ud = 250.50 | TOTAL 4 uds = 550.50
CALL sp_HistorialVentas(9001, 'Vendedor', CURDATE(), CURDATE());

-- H2. Comprador, hoy. Esperado: 2 pedidos (450.50 y 100.00) y fila TOTAL con total_comprado = 550.50
CALL sp_HistorialVentas(9002, 'Comprador', CURDATE(), CURDATE());

-- H3. DEBE FALLAR: fechas invertidas. Esperado: "La fecha inicial no puede ser mayor a la fecha final"
CALL sp_HistorialVentas(9001, 'Vendedor', '2026-12-31', '2026-01-01');

-- H4. DEBE FALLAR: sin ventas. Esperado: "No hay ventas en el periodo seleccionado"
CALL sp_HistorialVentas(9001, 'Vendedor', '2000-01-01', '2000-01-31');

-- H5. DEBE FALLAR: sin pedidos. Esperado: "No tienes pedidos registrados"
CALL sp_HistorialVentas(9002, 'Comprador', '2000-01-01', '2000-01-31');

-- H6. DEBE FALLAR: tipo inválido. Esperado: "Tipo de consulta no válido"
CALL sp_HistorialVentas(9001, 'Otro', CURDATE(), CURDATE());

-- =====================================================================
-- sp_CancelarPedido
-- =====================================================================

-- C1. Cancelar el primer pedido (Pendiente -> Cancelado).
--     Esperado: stock A = 9 y B = 5; pedido Cancelado; pago Reembolsado
CALL sp_CancelarPedido(@pedido, 'Cancelado');
SELECT id_variante, stock FROM variante_producto WHERE id_variante IN (9001, 9002);   -- 9 y 5
SELECT p.id_pedido, e.nombre AS estado FROM pedido p JOIN estado_pedido e ON e.id_estado = p.id_estado WHERE p.id_pedido = @pedido;
SELECT id_pedido, estado FROM pago WHERE id_pedido = @pedido;                          -- Reembolsado

-- C2. DEBE FALLAR: cancelar un pedido ya cancelado.
--     Esperado: "El pedido no puede cambiar a ese estado"
CALL sp_CancelarPedido(@pedido, 'Cancelado');

-- C3. DEBE FALLAR: devolver un pedido que sigue Pendiente.
--     Esperado: "El pedido no puede cambiar a ese estado"
CALL sp_CancelarPedido(@pedido2, 'Devuelto');

-- C4. DEBE FALLAR: pedido inexistente. Esperado: "El pedido no existe"
CALL sp_CancelarPedido(999999999, 'Cancelado');

-- C5. Devolución (Entregado -> Devuelto). Primero marcamos el segundo pedido como Entregado.
--     Esperado: stock A = 10 y B = 5 (igual que al inicio)
UPDATE pedido SET id_estado = (SELECT id_estado FROM estado_pedido WHERE nombre = 'Entregado')
WHERE id_pedido = @pedido2;
CALL sp_CancelarPedido(@pedido2, 'Devuelto');
SELECT id_variante, stock FROM variante_producto WHERE id_variante IN (9001, 9002);   -- 10 y 5

-- H7. Historial después de cancelar/devolver todo.
--     Vendedor DEBE FALLAR con "No hay ventas en el periodo seleccionado" (no cuentan cancelados ni devueltos)
CALL sp_HistorialVentas(9001, 'Vendedor', CURDATE(), CURDATE());
--     Comprador: 2 pedidos (Cancelado y Devuelto) y TOTAL con total_comprado = 0.00
CALL sp_HistorialVentas(9002, 'Comprador', CURDATE(), CURDATE());

-- =====================================================================
-- sp_ActualizarStockMasivo
-- =====================================================================

-- M1. Esperado: variantes_actualizadas = 2; stock A = 30 y B = 25
CALL sp_ActualizarStockMasivo(9001, 9001, 20);
SELECT id_variante, stock FROM variante_producto WHERE id_variante IN (9001, 9002);

-- M2. DEBE FALLAR: cantidad 0. Esperado: "La cantidad debe ser mayor a cero"
CALL sp_ActualizarStockMasivo(9001, 9001, 0);

-- M3. DEBE FALLAR: categoría sin productos del vendedor.
--     Esperado: "No se encontraron productos para actualizar"
CALL sp_ActualizarStockMasivo(9001, 9002, 5);

-- =====================================================================
-- LIMPIEZA (borra solo los datos de prueba, en orden por las llaves foráneas)
-- =====================================================================
DELETE FROM pago           WHERE id_pedido IN (SELECT id_pedido FROM pedido WHERE id_usuario = 9002);
DELETE FROM detalle_pedido WHERE id_pedido IN (SELECT id_pedido FROM pedido WHERE id_usuario = 9002);
DELETE FROM pedido         WHERE id_usuario = 9002;
DELETE FROM carrito_detalle WHERE id_carrito = 9001;
DELETE FROM carrito        WHERE id_carrito = 9001;
DELETE FROM variante_producto WHERE id_variante IN (9001, 9002);
DELETE FROM producto       WHERE id_producto IN (9001, 9002);
DELETE FROM marca          WHERE id_marca = 9001;
DELETE FROM categoria      WHERE id_categoria IN (9001, 9002);
DELETE FROM direccion      WHERE id_direccion IN (9001, 9002);
DELETE FROM usuario        WHERE id_usuario IN (9001, 9002);
