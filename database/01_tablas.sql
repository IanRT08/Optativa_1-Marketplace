-- =====================================================================
-- 01_tablas.sql  (SMAVIB, MySQL 8.0 en Amazon RDS)
-- DDL de las 16 tablas + DML de los catálogos fijos (roles, estados de
-- pedido y atributos). Idempotente: se puede ejecutar varias veces.
-- Generado a partir del script fuente del proyecto (ScriptBD_SP.sql):
--   - sin los bloques duplicados de direccion y pago;
--   - la columna pedido.id_direccion (que el script fuente agrega con
--     ALTER TABLE) va dentro del CREATE TABLE pedido, y direccion se crea
--     antes que pedido por su llave foránea. El esquema resultante es el mismo.
-- Orden de ejecución: 01_tablas -> 02_stored_procedures -> 03 y 04 (carga).
-- =====================================================================
CREATE DATABASE IF NOT EXISTS marketplace;

USE marketplace;

CREATE TABLE IF NOT EXISTS rol (
    id_rol  TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre  VARCHAR(30)      NOT NULL,
    PRIMARY KEY (id_rol),
    UNIQUE KEY uq_rol_nombre (nombre));

CREATE TABLE IF NOT EXISTS usuario (
    id_usuario     INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    id_rol         TINYINT UNSIGNED NOT NULL,
    nombre         VARCHAR(80)      NOT NULL,
    apellido       VARCHAR(80)      NOT NULL,
    email          VARCHAR(150)     NOT NULL,
    password_hash  VARCHAR(255)     NOT NULL,
    estado         ENUM('Activo','Inactivo') NOT NULL DEFAULT 'Activo',
    fecha_registro DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_usuario),
    UNIQUE KEY uq_usuario_email (email),
    CONSTRAINT fk_usuario_rol
        FOREIGN KEY (id_rol) REFERENCES rol (id_rol));

CREATE TABLE IF NOT EXISTS categoria (
    id_categoria     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre           VARCHAR(100) NOT NULL,
    descripcion      VARCHAR(255) NULL,
    id_categoria_padre INT UNSIGNED NULL,
    PRIMARY KEY (id_categoria),
    UNIQUE KEY uq_categoria_nombre (nombre),
    CONSTRAINT fk_categoria_padre
        FOREIGN KEY (id_categoria_padre) REFERENCES categoria (id_categoria)
);

CREATE TABLE IF NOT EXISTS marca (
    id_marca INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre   VARCHAR(100) NOT NULL,
    PRIMARY KEY (id_marca),
    UNIQUE KEY uq_marca_nombre (nombre)
);

CREATE TABLE IF NOT EXISTS producto (
    id_producto    INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    id_vendedor    INT UNSIGNED  NOT NULL,
    id_categoria   INT UNSIGNED  NOT NULL,
    id_marca       INT UNSIGNED  NOT NULL,
    nombre         VARCHAR(200)  NOT NULL,
    precio         DECIMAL(10,2) NOT NULL,
    estado         ENUM('Activo','Inactivo') NOT NULL DEFAULT 'Activo',
    fecha_creacion DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_producto),
    KEY idx_producto_categoria_precio (id_categoria, precio),
    KEY idx_producto_nombre (nombre),
    CONSTRAINT fk_producto_vendedor
        FOREIGN KEY (id_vendedor)  REFERENCES usuario   (id_usuario),
    CONSTRAINT fk_producto_categoria
        FOREIGN KEY (id_categoria) REFERENCES categoria (id_categoria),
    CONSTRAINT fk_producto_marca
        FOREIGN KEY (id_marca)     REFERENCES marca     (id_marca),
    CONSTRAINT ck_producto_precio CHECK (precio > 0)
);

CREATE TABLE IF NOT EXISTS atributo (
    id_atributo INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre      VARCHAR(50)  NOT NULL,
    PRIMARY KEY (id_atributo),
    UNIQUE KEY uq_atributo_nombre (nombre)
);

CREATE TABLE IF NOT EXISTS valor_atributo (
    id_valor    INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_atributo INT UNSIGNED NOT NULL,
    valor       VARCHAR(80)  NOT NULL,
    PRIMARY KEY (id_valor),
    UNIQUE KEY uq_valor_atributo (id_atributo, valor),
    CONSTRAINT fk_valor_atributo
        FOREIGN KEY (id_atributo) REFERENCES atributo (id_atributo)
);

CREATE TABLE IF NOT EXISTS variante_producto (
    id_variante INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_producto INT UNSIGNED NOT NULL,
    sku         VARCHAR(60)  NOT NULL,
    stock       INT          NOT NULL DEFAULT 0,
    PRIMARY KEY (id_variante),
    UNIQUE KEY uq_variante_sku (sku),
    KEY idx_variante_producto (id_producto),
    CONSTRAINT fk_variante_producto
        FOREIGN KEY (id_producto) REFERENCES producto (id_producto),
    CONSTRAINT ck_variante_stock CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS variante_valor (
    id_variante INT UNSIGNED NOT NULL,
    id_valor    INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_variante, id_valor),
    CONSTRAINT fk_vvalor_variante
        FOREIGN KEY (id_variante) REFERENCES variante_producto (id_variante),
    CONSTRAINT fk_vvalor_valor
        FOREIGN KEY (id_valor)    REFERENCES valor_atributo    (id_valor)
);

CREATE TABLE IF NOT EXISTS carrito (
    id_carrito     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario     INT UNSIGNED NOT NULL,
    fecha_creacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_carrito),
    UNIQUE KEY uq_carrito_usuario (id_usuario),
    CONSTRAINT fk_carrito_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario)
);

CREATE TABLE IF NOT EXISTS carrito_detalle (
    id_carrito  INT UNSIGNED NOT NULL,
    id_variante INT UNSIGNED NOT NULL,
    cantidad    INT UNSIGNED NOT NULL,
    PRIMARY KEY (id_carrito, id_variante),
    KEY idx_cdetalle_variante (id_variante),
    CONSTRAINT fk_cdetalle_carrito
        FOREIGN KEY (id_carrito)  REFERENCES carrito           (id_carrito)
        ON DELETE CASCADE,
    CONSTRAINT fk_cdetalle_variante
        FOREIGN KEY (id_variante) REFERENCES variante_producto (id_variante),
    CONSTRAINT ck_cdetalle_cantidad CHECK (cantidad > 0)
);

CREATE TABLE IF NOT EXISTS estado_pedido (
    id_estado TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre    VARCHAR(30)      NOT NULL,
    PRIMARY KEY (id_estado),
    UNIQUE KEY uq_estado_pedido_nombre (nombre)
);

CREATE TABLE IF NOT EXISTS direccion (
    id_direccion  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_usuario    INT UNSIGNED NOT NULL,
    calle         VARCHAR(150) NOT NULL,
    numero        VARCHAR(20)  NOT NULL,
    colonia       VARCHAR(100) NOT NULL,
    ciudad        VARCHAR(100) NOT NULL,
    estado_region VARCHAR(100) NOT NULL,
    codigo_postal CHAR(5)      NOT NULL,
    activa        TINYINT(1)   NOT NULL DEFAULT 1,
    PRIMARY KEY (id_direccion),
    KEY idx_direccion_usuario (id_usuario),
    CONSTRAINT fk_direccion_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario),
    CONSTRAINT ck_direccion_cp CHECK (codigo_postal REGEXP '^[0-9]{5}$')
);

CREATE TABLE IF NOT EXISTS pedido (
    id_pedido  INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    id_usuario INT UNSIGNED     NOT NULL,
    id_estado  TINYINT UNSIGNED NOT NULL,
    id_direccion INT UNSIGNED   NULL,
    fecha      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total      DECIMAL(12,2)    NOT NULL,
    PRIMARY KEY (id_pedido),
    KEY idx_pedido_usuario_fecha (id_usuario, fecha),
    KEY idx_pedido_estado (id_estado),
    KEY idx_pedido_fecha (fecha),
    KEY idx_pedido_direccion (id_direccion),
    CONSTRAINT fk_pedido_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario       (id_usuario),
    CONSTRAINT fk_pedido_estado
        FOREIGN KEY (id_estado)  REFERENCES estado_pedido (id_estado),
    CONSTRAINT fk_pedido_direccion
        FOREIGN KEY (id_direccion) REFERENCES direccion (id_direccion),
    CONSTRAINT ck_pedido_total CHECK (total >= 0)
);

CREATE TABLE IF NOT EXISTS detalle_pedido (
    id_detalle      INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    id_pedido       INT UNSIGNED  NOT NULL,
    id_variante     INT UNSIGNED  NOT NULL,
    cantidad        INT UNSIGNED  NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (id_detalle),
    UNIQUE KEY uq_detalle_pedido_variante (id_pedido, id_variante),
    KEY idx_detalle_variante (id_variante),
    CONSTRAINT fk_detalle_pedido
        FOREIGN KEY (id_pedido)   REFERENCES pedido            (id_pedido),
    CONSTRAINT fk_detalle_variante
        FOREIGN KEY (id_variante) REFERENCES variante_producto (id_variante),
    CONSTRAINT ck_detalle_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_detalle_precio   CHECK (precio_unitario >= 0)
);

CREATE TABLE IF NOT EXISTS pago (
    id_pago   INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    id_pedido INT UNSIGNED  NOT NULL,
    token     VARCHAR(100)  NOT NULL,
    ultimos4  CHAR(4)       NOT NULL,
    monto     DECIMAL(12,2) NOT NULL,
    estado    ENUM('Aprobado','Reembolsado') NOT NULL DEFAULT 'Aprobado',
    fecha     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_pago),
    UNIQUE KEY uq_pago_pedido (id_pedido),
    UNIQUE KEY uq_pago_token (token),
    CONSTRAINT fk_pago_pedido
        FOREIGN KEY (id_pedido) REFERENCES pedido (id_pedido),
    CONSTRAINT ck_pago_monto    CHECK (monto >= 0),
    CONSTRAINT ck_pago_ultimos4 CHECK (ultimos4 REGEXP '^[0-9]{4}$')
);

-- Datos iniciales de catálogos (sin esto no se puede registrar usuarios,
-- pedidos ni variantes, porque dependen de estas llaves foráneas).
INSERT INTO rol (id_rol, nombre) VALUES
    (1, 'Administrador'),
    (2, 'Vendedor'),
    (3, 'Comprador')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO estado_pedido (id_estado, nombre) VALUES
    (1, 'Pendiente'),
    (2, 'Enviado'),
    (3, 'Entregado'),
    (4, 'Cancelado'),
    (5, 'Devuelto')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

INSERT INTO atributo (id_atributo, nombre) VALUES
    (1, 'Talla'),
    (2, 'Color')
ON DUPLICATE KEY UPDATE nombre = VALUES(nombre);

-- Verificación: debe devolver 16
SELECT COUNT(*) AS total_tablas
FROM information_schema.tables
WHERE table_schema = 'marketplace' AND table_type = 'BASE TABLE';
