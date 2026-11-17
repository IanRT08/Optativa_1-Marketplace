-- =====================================================================
-- 02_stored_procedures.sql  (SMAVIB, MySQL 8.0)
-- Los 4 stored procedures transaccionales que llaman las Lambdas:
--   sp_RegistrarCompra       (DFR 6.1)  compra + descuento de stock
--   sp_CancelarPedido        (DFR 7.3)  cancelación/devolución + reabasto
--   sp_HistorialVentas       (DFR 7.4, 8.1, 8.2) historial consolidado
--   sp_ActualizarStockMasivo (DFR 3.5)  reabasto masivo por categoría
-- Copiado del script fuente (ScriptBD_SP.sql) sin cambios en los cuerpos;
-- se agregó DELIMITER para el cliente mysql y MySQL Workbench (DataGrip lo
-- acepta igual). Requiere 01_tablas.sql.
-- =====================================================================
USE marketplace;

-- El procedimiento anterior se reemplaza por sp_HistorialVentas
DROP PROCEDURE IF EXISTS sp_ReporteVentasVendedor;

-- =====================================================================
-- 1. sp_RegistrarCompra
--    Convierte el carrito del comprador en un pedido, en UNA transacción:
--      - cabecera del pedido (estado Pendiente) con su dirección de envío
--      - detalle con el precio unitario histórico
--      - descuento de stock de cada variante
--      - registro del pago simulado (solo token y últimos 4 dígitos)
--      - vaciado del carrito
--    Si algo falla, se hace ROLLBACK y no se guarda ningún cambio.
--
--    Parámetros:
--      p_id_usuario    comprador que confirma la compra
--      p_id_direccion  dirección de envío (debe ser suya y estar activa)
--      p_token         token del pago simulado (lo genera la aplicación)
--      p_ultimos4      últimos 4 dígitos de la tarjeta
--      p_id_pedido     (OUT) número de la orden generada
-- =====================================================================
DROP PROCEDURE IF EXISTS sp_RegistrarCompra;

DELIMITER $$
CREATE PROCEDURE sp_RegistrarCompra(
    IN  p_id_usuario   INT UNSIGNED,
    IN  p_id_direccion INT UNSIGNED,
    IN  p_token        VARCHAR(100),
    IN  p_ultimos4     CHAR(4),
    OUT p_id_pedido    INT UNSIGNED
)
BEGIN
    DECLARE v_id_carrito  INT UNSIGNED;
    DECLARE v_n_items     INT DEFAULT 0;
    DECLARE v_i           INT DEFAULT 0;
    DECLARE v_id_variante INT UNSIGNED;
    DECLARE v_cantidad    INT;
    DECLARE v_stock       INT;
    DECLARE v_precio      DECIMAL(10,2);
    DECLARE v_estado      VARCHAR(10);
    DECLARE v_nombre      VARCHAR(200);
    DECLARE v_total       DECIMAL(12,2) DEFAULT 0;
    DECLARE v_dir_valida  INT DEFAULT 0;
    DECLARE v_msg         VARCHAR(255);

    -- Ante cualquier error: deshacer todo y volver a lanzar el error original
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_id_usuario IS NULL OR p_id_direccion IS NULL
       OR p_token IS NULL OR p_token = '' OR p_ultimos4 IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Debe completar los campos obligatorios';
    END IF;

    IF p_ultimos4 NOT REGEXP '^[0-9]{4}$' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Datos de pago no válidos';
    END IF;

    START TRANSACTION;

    -- Bloquea el carrito del usuario: evita que dos compras simultáneas
    -- (doble clic) procesen el mismo carrito dos veces.
    SELECT id_carrito INTO v_id_carrito
    FROM carrito
    WHERE id_usuario = p_id_usuario
    FOR UPDATE;

    IF v_id_carrito IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Tu carrito está vacío';
    END IF;

    SELECT COUNT(*) INTO v_n_items
    FROM carrito_detalle
    WHERE id_carrito = v_id_carrito;

    IF v_n_items = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Tu carrito está vacío';
    END IF;

    -- La dirección debe ser del comprador y estar activa
    SELECT COUNT(*) INTO v_dir_valida
    FROM direccion
    WHERE id_direccion = p_id_direccion
      AND id_usuario   = p_id_usuario
      AND activa       = 1;

    IF v_dir_valida = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La dirección de envío no es válida';
    END IF;

    -- Cabecera del pedido (el total se calcula al final)
    INSERT INTO pedido (id_usuario, id_estado, id_direccion, fecha, total)
    VALUES (
        p_id_usuario,
        (SELECT id_estado FROM estado_pedido WHERE nombre = 'Pendiente'),
        p_id_direccion,
        NOW(),
        0
    );
    SET p_id_pedido = LAST_INSERT_ID();

    -- Recorre los ítems del carrito en orden de id_variante.
    -- El orden fijo evita bloqueos cruzados (deadlocks) entre operaciones simultáneas.
    WHILE v_i < v_n_items DO
        SET v_id_variante = NULL;
        SET v_cantidad    = NULL;
        SET v_nombre      = NULL;

        SELECT id_variante, cantidad
          INTO v_id_variante, v_cantidad
        FROM carrito_detalle
        WHERE id_carrito = v_id_carrito
        ORDER BY id_variante
        LIMIT v_i, 1;

        -- Bloquea la fila de la variante para validar y descontar el stock
        SELECT v.stock, p.precio, p.estado, p.nombre
          INTO v_stock, v_precio, v_estado, v_nombre
        FROM variante_producto v
        JOIN producto p ON p.id_producto = v.id_producto
        WHERE v.id_variante = v_id_variante
        FOR UPDATE OF v;

        IF v_nombre IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un producto del carrito ya no está disponible';
        END IF;

        IF v_estado <> 'Activo' THEN
            SET v_msg = CONCAT('El producto ', v_nombre, ' ya no está disponible');
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
        END IF;

        IF v_stock < v_cantidad THEN
            SET v_msg = CONCAT('Stock insuficiente para el producto ', v_nombre);
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
        END IF;

        -- Detalle con el precio unitario histórico (el precio de hoy)
        INSERT INTO detalle_pedido (id_pedido, id_variante, cantidad, precio_unitario)
        VALUES (p_id_pedido, v_id_variante, v_cantidad, v_precio);

        -- Descuento automático de stock
        UPDATE variante_producto
        SET stock = stock - v_cantidad
        WHERE id_variante = v_id_variante;

        SET v_total = v_total + (v_cantidad * v_precio);
        SET v_i = v_i + 1;
    END WHILE;

    UPDATE pedido SET total = v_total WHERE id_pedido = p_id_pedido;

    -- Pago simulado, tokenizado: sin número de tarjeta ni CVV
    INSERT INTO pago (id_pedido, token, ultimos4, monto, estado)
    VALUES (p_id_pedido, p_token, p_ultimos4, v_total, 'Aprobado');

    -- El carrito queda vacío después de la compra
    DELETE FROM carrito_detalle WHERE id_carrito = v_id_carrito;

    COMMIT;
END$$
DELIMITER ;


-- =====================================================================
-- 2. sp_CancelarPedido
--    Cancela o marca como devuelto un pedido y REABASTECE el stock de cada
--    variante, todo en UNA transacción. El pago pasa a "Reembolsado".
--
--    Transiciones permitidas:
--      Pendiente -> Cancelado      Enviado -> Cancelado      Entregado -> Devuelto
--    (Pendiente -> Enviado y Enviado -> Entregado no tocan stock: se hacen
--     con un UPDATE simple desde la aplicación.)
--
--    Parámetros:
--      p_id_pedido     pedido a cancelar o devolver
--      p_nuevo_estado  'Cancelado' o 'Devuelto'
-- =====================================================================
DROP PROCEDURE IF EXISTS sp_CancelarPedido;

DELIMITER $$
CREATE PROCEDURE sp_CancelarPedido(
    IN p_id_pedido    INT UNSIGNED,
    IN p_nuevo_estado VARCHAR(20)
)
BEGIN
    DECLARE v_estado_actual VARCHAR(30);
    DECLARE v_n_items       INT DEFAULT 0;
    DECLARE v_i             INT DEFAULT 0;
    DECLARE v_id_variante   INT UNSIGNED;
    DECLARE v_cantidad      INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_id_pedido IS NULL OR p_nuevo_estado IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Debe completar los campos obligatorios';
    END IF;

    IF p_nuevo_estado NOT IN ('Cancelado', 'Devuelto') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El pedido no puede cambiar a ese estado';
    END IF;

    START TRANSACTION;

    -- Bloquea el pedido: evita cancelarlo dos veces al mismo tiempo
    SELECT e.nombre INTO v_estado_actual
    FROM pedido ped
    JOIN estado_pedido e ON e.id_estado = ped.id_estado
    WHERE ped.id_pedido = p_id_pedido
    FOR UPDATE OF ped;

    IF v_estado_actual IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El pedido no existe';
    END IF;

    IF NOT (
           (p_nuevo_estado = 'Cancelado' AND v_estado_actual IN ('Pendiente', 'Enviado'))
        OR (p_nuevo_estado = 'Devuelto'  AND v_estado_actual = 'Entregado')
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El pedido no puede cambiar a ese estado';
    END IF;

    SELECT COUNT(*) INTO v_n_items
    FROM detalle_pedido
    WHERE id_pedido = p_id_pedido;

    -- Reabastece el stock variante por variante, en orden de id_variante
    WHILE v_i < v_n_items DO
        SELECT id_variante, cantidad
          INTO v_id_variante, v_cantidad
        FROM detalle_pedido
        WHERE id_pedido = p_id_pedido
        ORDER BY id_variante
        LIMIT v_i, 1;

        UPDATE variante_producto
        SET stock = stock + v_cantidad
        WHERE id_variante = v_id_variante;

        SET v_i = v_i + 1;
    END WHILE;

    UPDATE pedido
    SET id_estado = (SELECT id_estado FROM estado_pedido WHERE nombre = p_nuevo_estado)
    WHERE id_pedido = p_id_pedido;

    UPDATE pago
    SET estado = 'Reembolsado'
    WHERE id_pedido = p_id_pedido;

    COMMIT;

    SELECT p_id_pedido    AS id_pedido,
           p_nuevo_estado AS nuevo_estado,
           v_n_items      AS variantes_repuestas;
END$$
DELIMITER ;


-- =====================================================================
-- 3. sp_HistorialVentas
--    Historial consolidado de un rango de fechas (ambas incluidas).
--    p_tipo = 'Vendedor': una fila por producto vendido + fila TOTAL
--             (unidades_vendidas y total_vendido con precio unitario histórico).
--    p_tipo = 'Comprador': una fila por pedido + fila TOTAL
--             (total_comprado).
--    En ambos casos, los pedidos Cancelados y Devueltos no suman al total.
--    La restricción por rol (el vendedor solo ve lo suyo, el comprador solo
--    sus pedidos, el administrador cualquiera) la hace la aplicación.
-- =====================================================================
DROP PROCEDURE IF EXISTS sp_HistorialVentas;

DELIMITER $$
CREATE PROCEDURE sp_HistorialVentas(
    IN p_id_usuario   INT UNSIGNED,
    IN p_tipo         VARCHAR(10),
    IN p_fecha_inicio DATE,
    IN p_fecha_fin    DATE
)
BEGIN
    DECLARE v_hay INT DEFAULT 0;

    IF p_id_usuario IS NULL OR p_tipo IS NULL
       OR p_fecha_inicio IS NULL OR p_fecha_fin IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Debe completar los campos obligatorios';
    END IF;

    IF p_tipo NOT IN ('Comprador', 'Vendedor') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Tipo de consulta no válido';
    END IF;

    IF p_fecha_inicio > p_fecha_fin THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La fecha inicial no puede ser mayor a la fecha final';
    END IF;

    IF p_tipo = 'Vendedor' THEN

        SELECT COUNT(*) INTO v_hay
        FROM pedido ped
        JOIN estado_pedido e      ON e.id_estado   = ped.id_estado
        JOIN detalle_pedido d     ON d.id_pedido   = ped.id_pedido
        JOIN variante_producto v  ON v.id_variante = d.id_variante
        JOIN producto p           ON p.id_producto = v.id_producto
        WHERE p.id_vendedor = p_id_usuario
          AND ped.fecha >= p_fecha_inicio
          AND ped.fecha <  DATE_ADD(p_fecha_fin, INTERVAL 1 DAY)
          AND e.nombre NOT IN ('Cancelado', 'Devuelto');

        IF v_hay = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No hay ventas en el periodo seleccionado';
        END IF;

        SELECT
            p.id_producto,
            IF(GROUPING(p.id_producto) = 1, 'TOTAL', MAX(p.nombre)) AS producto,
            SUM(d.cantidad)                                         AS unidades_vendidas,
            SUM(d.cantidad * d.precio_unitario)                     AS total_vendido
        FROM pedido ped
        JOIN estado_pedido e      ON e.id_estado   = ped.id_estado
        JOIN detalle_pedido d     ON d.id_pedido   = ped.id_pedido
        JOIN variante_producto v  ON v.id_variante = d.id_variante
        JOIN producto p           ON p.id_producto = v.id_producto
        WHERE p.id_vendedor = p_id_usuario
          AND ped.fecha >= p_fecha_inicio
          AND ped.fecha <  DATE_ADD(p_fecha_fin, INTERVAL 1 DAY)
          AND e.nombre NOT IN ('Cancelado', 'Devuelto')
        GROUP BY p.id_producto WITH ROLLUP;

    ELSE

        SELECT COUNT(*) INTO v_hay
        FROM pedido ped
        WHERE ped.id_usuario = p_id_usuario
          AND ped.fecha >= p_fecha_inicio
          AND ped.fecha <  DATE_ADD(p_fecha_fin, INTERVAL 1 DAY);

        IF v_hay = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No tienes pedidos registrados';
        END IF;

        SELECT
            IF(GROUPING(ped.id_pedido) = 1, 'TOTAL', CAST(ped.id_pedido AS CHAR)) AS pedido,
            IF(GROUPING(ped.id_pedido) = 1, NULL, MAX(ped.fecha))                 AS fecha,
            IF(GROUPING(ped.id_pedido) = 1, NULL, MAX(e.nombre))                  AS estado,
            IF(GROUPING(ped.id_pedido) = 1, NULL, MAX(ped.total))                 AS total_pedido,
            SUM(IF(e.nombre IN ('Cancelado', 'Devuelto'), 0, ped.total))          AS total_comprado
        FROM pedido ped
        JOIN estado_pedido e ON e.id_estado = ped.id_estado
        WHERE ped.id_usuario = p_id_usuario
          AND ped.fecha >= p_fecha_inicio
          AND ped.fecha <  DATE_ADD(p_fecha_fin, INTERVAL 1 DAY)
        GROUP BY ped.id_pedido WITH ROLLUP;

    END IF;
END$$
DELIMITER ;


-- =====================================================================
-- 4. sp_ActualizarStockMasivo
--    Reabastece, en una sola transacción, el stock de TODAS las variantes de
--    los productos de un vendedor que pertenecen a una categoría.
--    Si algo falla, no se modifica el stock de ningún producto.
--
--    Parámetros:
--      p_id_vendedor   vendedor dueño de los productos
--      p_id_categoria  categoría seleccionada
--      p_cantidad      unidades a agregar a cada variante (> 0)
-- =====================================================================
DROP PROCEDURE IF EXISTS sp_ActualizarStockMasivo;

DELIMITER $$
CREATE PROCEDURE sp_ActualizarStockMasivo(
    IN p_id_vendedor  INT UNSIGNED,
    IN p_id_categoria INT UNSIGNED,
    IN p_cantidad     INT
)
BEGIN
    DECLARE v_actualizadas INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_id_vendedor IS NULL OR p_id_categoria IS NULL OR p_cantidad IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Debe completar los campos obligatorios';
    END IF;

    IF p_cantidad <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La cantidad debe ser mayor a cero';
    END IF;

    START TRANSACTION;

    UPDATE variante_producto v
    JOIN producto p ON p.id_producto = v.id_producto
    SET v.stock = v.stock + p_cantidad
    WHERE p.id_vendedor  = p_id_vendedor
      AND p.id_categoria = p_id_categoria;

    SET v_actualizadas = ROW_COUNT();

    IF v_actualizadas = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se encontraron productos para actualizar';
    END IF;

    COMMIT;

    SELECT v_actualizadas AS variantes_actualizadas;
END$$
DELIMITER ;
