-- =====================================================================
-- 06_resenas.sql  (SMAVIB, MySQL 8.0 en Amazon RDS)
-- Schema separado para reseñas de productos.
-- Se ejecuta en la MISMA instancia RDS que marketplace, pero en un
-- schema distinto (DB_NAME_RESENAS). Idempotente: se puede repetir.
-- Orden: después de 01_tablas.sql (no hay FK entre schemas).
-- =====================================================================
CREATE DATABASE IF NOT EXISTS resenas;

USE resenas;

-- Una reseña por comprador por producto (uq_resena_usuario_producto).
-- id_usuario e id_producto son referencias lógicas a marketplace:
-- no hay FK entre schemas en MySQL, la integridad la garantiza la Lambda
-- (verifica que el comprador haya recibido el producto antes de reseñar).
CREATE TABLE IF NOT EXISTS resena (
    id_resena    INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    id_usuario   INT UNSIGNED  NOT NULL,
    id_producto  INT UNSIGNED  NOT NULL,
    calificacion TINYINT       NOT NULL,
    comentario   TEXT          NOT NULL,
    fecha        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activa       TINYINT(1)    NOT NULL DEFAULT 1,
    PRIMARY KEY (id_resena),
    UNIQUE KEY uq_resena_usuario_producto (id_usuario, id_producto),
    KEY idx_resena_producto (id_producto),
    CONSTRAINT ck_resena_calificacion CHECK (calificacion BETWEEN 1 AND 5)
);

-- Verificación: debe devolver 1
SELECT COUNT(*) AS total_tablas
FROM information_schema.tables
WHERE table_schema = 'resenas' AND table_type = 'BASE TABLE';
