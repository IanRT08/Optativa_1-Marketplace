-- =====================================================================
-- 01_carga_inicial.sql  (SMAVIB)
-- Carga de prueba en RDS MySQL:
--   1. Marcas (27), categorías (12) y valores de atributo (Talla y Color).
--   2. 17,000 productos Activos con su variante estándar P{id}-STD.
-- Después se ejecuta lambda-cargaDynamo con el primer_id y el ultimo_id que
-- muestra este script al final (paso 6).
--
-- Cómo ejecutarlo en DataGrip:
--   - Base marketplace seleccionada. Ejecuta el ARCHIVO COMPLETO de una vez
--     (no por partes): las variables @ viven en la sesión.
--   - Requisito: 00_vendedores_carga.sql ya ejecutado (o al menos un usuario
--     con rol Vendedor y estado Activo).
--
-- Diseño:
--   - Una sola conexión y una sola transacción (si algo falla, ROLLBACK y no
--     queda nada a medias).
--   - Sin 17,000 líneas de INSERT: los productos se generan dentro de MySQL
--     con INSERT ... SELECT a partir de una tabla de dígitos cruzada
--     (sin recursión, sin tablas temporales, sin procedimientos extra).
--   - Catálogos idempotentes (WHERE NOT EXISTS): se puede volver a ejecutar.
--   - Protección: si ya hay 17,000 productos o más, no inserta productos.
--   - Datos deterministas (mismas entradas -> mismos datos), sin RAND().
--   - fecha_creacion la pone MySQL (DEFAULT CURRENT_TIMESTAMP).
-- =====================================================================

START TRANSACTION;

-- ---------------------------------------------------------------------
-- 1. Marcas
-- ---------------------------------------------------------------------
INSERT INTO marca (nombre)
SELECT t.nombre
FROM (
              SELECT 'Samsung' AS nombre UNION ALL SELECT 'Apple'     UNION ALL SELECT 'Xiaomi'
    UNION ALL SELECT 'Motorola'          UNION ALL SELECT 'Lenovo'    UNION ALL SELECT 'HP'
    UNION ALL SELECT 'Dell'              UNION ALL SELECT 'Asus'      UNION ALL SELECT 'Sony'
    UNION ALL SELECT 'JBL'               UNION ALL SELECT 'LG'        UNION ALL SELECT 'Hisense'
    UNION ALL SELECT 'Nintendo'          UNION ALL SELECT 'Microsoft' UNION ALL SELECT 'Nike'
    UNION ALL SELECT 'Adidas'            UNION ALL SELECT 'Puma'      UNION ALL SELECT 'New Balance'
    UNION ALL SELECT 'Levis'             UNION ALL SELECT 'Philips'   UNION ALL SELECT 'Tramontina'
    UNION ALL SELECT 'Oster'             UNION ALL SELECT 'Mabe'      UNION ALL SELECT 'Voit'
    UNION ALL SELECT 'Mattel'            UNION ALL SELECT 'Hasbro'    UNION ALL SELECT 'Lego'
) t
WHERE NOT EXISTS (SELECT 1 FROM marca m WHERE m.nombre = t.nombre);

-- ---------------------------------------------------------------------
-- 2. Categorías (principales, sin subcategorías)
-- ---------------------------------------------------------------------
INSERT INTO categoria (nombre, descripcion)
SELECT t.nombre, t.descripcion
FROM (
              SELECT 'Celulares' AS nombre, 'Teléfonos inteligentes' AS descripcion
    UNION ALL SELECT 'Laptops',     'Computadoras portátiles'
    UNION ALL SELECT 'Tablets',     'Tabletas'
    UNION ALL SELECT 'Audio',       'Audífonos y bocinas'
    UNION ALL SELECT 'Televisores', 'Pantallas y televisores'
    UNION ALL SELECT 'Videojuegos', 'Consolas y accesorios'
    UNION ALL SELECT 'Tenis',       'Calzado deportivo'
    UNION ALL SELECT 'Ropa',        'Ropa para dama y caballero'
    UNION ALL SELECT 'Hogar',       'Artículos para el hogar'
    UNION ALL SELECT 'Cocina',      'Electrodomésticos de cocina'
    UNION ALL SELECT 'Deportes',    'Artículos deportivos'
    UNION ALL SELECT 'Juguetes',    'Juguetes y juegos'
) t
WHERE NOT EXISTS (SELECT 1 FROM categoria c WHERE c.nombre = t.nombre);

-- ---------------------------------------------------------------------
-- 3. Valores de atributo (los atributos Talla y Color ya los siembra
--    ScriptBD_SP.sql). Se insertan en orden: A2 los lista por id_valor.
-- ---------------------------------------------------------------------
INSERT INTO valor_atributo (id_atributo, valor)
SELECT a.id_atributo, t.valor
FROM (
              SELECT 1 AS orden, 'Talla' AS atributo, 'CH' AS valor
    UNION ALL SELECT 2,  'Talla', 'M'
    UNION ALL SELECT 3,  'Talla', 'G'
    UNION ALL SELECT 4,  'Talla', 'EG'
    UNION ALL SELECT 5,  'Color', 'Negro'
    UNION ALL SELECT 6,  'Color', 'Blanco'
    UNION ALL SELECT 7,  'Color', 'Rojo'
    UNION ALL SELECT 8,  'Color', 'Azul'
    UNION ALL SELECT 9,  'Color', 'Verde'
    UNION ALL SELECT 10, 'Color', 'Gris'
) t
JOIN atributo a ON a.nombre = t.atributo
WHERE NOT EXISTS (
    SELECT 1 FROM valor_atributo va
    WHERE va.id_atributo = a.id_atributo AND va.valor = t.valor
)
ORDER BY t.orden;

-- ---------------------------------------------------------------------
-- 4. Productos (17,000)
-- ---------------------------------------------------------------------
SET @max_antes      := (SELECT COALESCE(MAX(id_producto), 0) FROM producto);
SET @productos_antes := (SELECT COUNT(*) FROM producto);
SET @vendedores     := (SELECT COUNT(*) FROM usuario u JOIN rol r ON r.id_rol = u.id_rol
                        WHERE r.nombre = 'Vendedor' AND u.estado = 'Activo');

INSERT INTO producto (id_vendedor, id_categoria, id_marca, nombre, precio, estado)
WITH
digitos AS (
              SELECT 0 AS d UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
    UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7
    UNION ALL SELECT 8 UNION ALL SELECT 9
),
numeros AS (            -- 1 .. 20,000 (se filtra a 17,000 abajo)
    SELECT u.d + 10 * de.d + 100 * ce.d + 1000 * mi.d + 10000 * dm.d + 1 AS n
    FROM digitos u
    CROSS JOIN digitos de
    CROSS JOIN digitos ce
    CROSS JOIN digitos mi
    CROSS JOIN digitos dm
    WHERE dm.d < 2
),
config AS (             -- tipo de producto y rango de precio por categoría
              SELECT 0 AS pos, 'Celulares' AS categoria, 'Celular' AS tipo, 3000 AS pmin, 40000 AS pmax
    UNION ALL SELECT 1,  'Laptops',     'Laptop',     8000, 60000
    UNION ALL SELECT 2,  'Tablets',     'Tablet',     2500, 30000
    UNION ALL SELECT 3,  'Audio',       'Audífonos',   300,  9000
    UNION ALL SELECT 4,  'Televisores', 'Televisor',  4000, 45000
    UNION ALL SELECT 5,  'Videojuegos', 'Consola',    3000, 15000
    UNION ALL SELECT 6,  'Tenis',       'Tenis',       900,  4500
    UNION ALL SELECT 7,  'Ropa',        'Playera',     200,  1500
    UNION ALL SELECT 8,  'Hogar',       'Lámpara',     250,  3000
    UNION ALL SELECT 9,  'Cocina',      'Licuadora',   400,  5000
    UNION ALL SELECT 10, 'Deportes',    'Balón',       200,  1800
    UNION ALL SELECT 11, 'Juguetes',    'Juguete',     150,  2000
),
cfg AS (
    SELECT c.pos, c.categoria, c.tipo, c.pmin, c.pmax, cat.id_categoria
    FROM config c
    JOIN categoria cat ON cat.nombre = c.categoria
),
marcas_categoria AS (   -- marcas que encajan con cada categoría
    SELECT x.categoria, m.id_marca, m.nombre AS marca,
           ROW_NUMBER() OVER (PARTITION BY x.categoria ORDER BY m.nombre) - 1 AS pos,
           COUNT(*)     OVER (PARTITION BY x.categoria)                       AS total
    FROM (
                  SELECT 'Celulares' AS categoria, 'Samsung' AS marca
        UNION ALL SELECT 'Celulares',   'Apple'      UNION ALL SELECT 'Celulares',   'Xiaomi'
        UNION ALL SELECT 'Celulares',   'Motorola'
        UNION ALL SELECT 'Laptops',     'Lenovo'     UNION ALL SELECT 'Laptops',     'HP'
        UNION ALL SELECT 'Laptops',     'Dell'       UNION ALL SELECT 'Laptops',     'Asus'
        UNION ALL SELECT 'Laptops',     'Apple'
        UNION ALL SELECT 'Tablets',     'Samsung'    UNION ALL SELECT 'Tablets',     'Apple'
        UNION ALL SELECT 'Tablets',     'Lenovo'     UNION ALL SELECT 'Tablets',     'Xiaomi'
        UNION ALL SELECT 'Audio',       'Sony'       UNION ALL SELECT 'Audio',       'JBL'
        UNION ALL SELECT 'Audio',       'Samsung'    UNION ALL SELECT 'Audio',       'Apple'
        UNION ALL SELECT 'Televisores', 'Samsung'    UNION ALL SELECT 'Televisores', 'LG'
        UNION ALL SELECT 'Televisores', 'Sony'       UNION ALL SELECT 'Televisores', 'Hisense'
        UNION ALL SELECT 'Videojuegos', 'Sony'       UNION ALL SELECT 'Videojuegos', 'Nintendo'
        UNION ALL SELECT 'Videojuegos', 'Microsoft'
        UNION ALL SELECT 'Tenis',       'Nike'       UNION ALL SELECT 'Tenis',       'Adidas'
        UNION ALL SELECT 'Tenis',       'Puma'       UNION ALL SELECT 'Tenis',       'New Balance'
        UNION ALL SELECT 'Ropa',        'Levis'      UNION ALL SELECT 'Ropa',        'Nike'
        UNION ALL SELECT 'Ropa',        'Adidas'     UNION ALL SELECT 'Ropa',        'Puma'
        UNION ALL SELECT 'Hogar',       'Philips'    UNION ALL SELECT 'Hogar',       'Tramontina'
        UNION ALL SELECT 'Hogar',       'Mabe'
        UNION ALL SELECT 'Cocina',      'Oster'      UNION ALL SELECT 'Cocina',      'Mabe'
        UNION ALL SELECT 'Cocina',      'Philips'    UNION ALL SELECT 'Cocina',      'Tramontina'
        UNION ALL SELECT 'Deportes',    'Voit'       UNION ALL SELECT 'Deportes',    'Adidas'
        UNION ALL SELECT 'Deportes',    'Nike'       UNION ALL SELECT 'Deportes',    'Puma'
        UNION ALL SELECT 'Juguetes',    'Mattel'     UNION ALL SELECT 'Juguetes',    'Hasbro'
        UNION ALL SELECT 'Juguetes',    'Lego'
    ) x
    JOIN marca m ON m.nombre = x.marca
),
vendedores AS (         -- se reparten entre todos los vendedores Activos
    SELECT u.id_usuario,
           ROW_NUMBER() OVER (ORDER BY u.id_usuario) - 1 AS pos,
           COUNT(*)     OVER ()                          AS total
    FROM usuario u
    JOIN rol r ON r.id_rol = u.id_rol
    WHERE r.nombre = 'Vendedor' AND u.estado = 'Activo'
)
SELECT
    v.id_usuario,
    cfg.id_categoria,
    mc.id_marca,
    CONCAT(cfg.tipo, ' ', mc.marca, ' Modelo ', LPAD(n.n, 5, '0')),
    -- precio determinista dentro del rango de la categoría, terminado en .99
    CAST(cfg.pmin + FLOOR((cfg.pmax - cfg.pmin) * ((n.n * 7919) MOD 1000) / 999) + 0.99
         AS DECIMAL(10, 2)),
    'Activo'
FROM numeros n
JOIN cfg              ON cfg.pos = n.n MOD 12
JOIN marcas_categoria mc ON mc.categoria = cfg.categoria
                        AND mc.pos = (n.n DIV 12) MOD mc.total
JOIN vendedores v     ON v.pos = (n.n DIV 7) MOD v.total
WHERE n.n <= 17000
  AND @productos_antes < 17000          -- protección contra doble carga
ORDER BY n.n;

-- ---------------------------------------------------------------------
-- 5. Variante estándar de cada producto nuevo (SKU P{id}-STD).
--    Stock determinista de 0 a 200; cada producto con id múltiplo de 50
--    queda en 0 para probar "agotado".
-- ---------------------------------------------------------------------
INSERT INTO variante_producto (id_producto, sku, stock)
SELECT p.id_producto,
       CONCAT('P', p.id_producto, '-STD'),
       CASE WHEN p.id_producto MOD 50 = 0 THEN 0 ELSE (p.id_producto * 37) MOD 201 END
FROM producto p
WHERE p.id_producto > @max_antes
  AND NOT EXISTS (SELECT 1 FROM variante_producto v WHERE v.id_producto = p.id_producto)
ORDER BY p.id_producto;

COMMIT;

-- ---------------------------------------------------------------------
-- 6. Resultado: pasa primer_id y ultimo_id a lambda-cargaDynamo
-- ---------------------------------------------------------------------
SELECT
    CASE
        WHEN @vendedores = 0         THEN 'No hay vendedores Activos: ejecuta 00_vendedores_carga.sql'
        WHEN @productos_antes >= 17000 THEN 'La carga ya se había hecho: no se insertaron productos'
        ELSE 'Carga completa'
    END                                   AS resultado,
    COUNT(p.id_producto)                  AS productos_nuevos,
    MIN(p.id_producto)                    AS primer_id,
    MAX(p.id_producto)                    AS ultimo_id
FROM producto p
WHERE p.id_producto > @max_antes;

-- Comprobación: cada producto nuevo tiene exactamente una variante estándar
SELECT COUNT(*) AS productos_sin_variante
FROM producto p
WHERE p.id_producto > @max_antes
  AND NOT EXISTS (SELECT 1 FROM variante_producto v WHERE v.id_producto = p.id_producto);
