-- =====================================================================
-- 00_vendedores_carga.sql  (SMAVIB)
-- Vendedores dueños de los productos de prueba que crea 01_carga_inicial.sql.
-- Ejecutar en DataGrip ANTES de 01_carga_inicial.sql (base: marketplace).
--
-- Seguridad:
--   - password_hash = '!' NO es un hash bcrypt válido: estas cuentas no
--     pueden iniciar sesión (1.2 responde "contraseña incorrecta").
--   - En este archivo no hay ninguna contraseña. Las cuentas con las que se
--     prueba la aplicación se crean con las Lambdas (bcrypt se genera en
--     Lambda, regla 4 de CLAUDE.md).
--   - Dominio .test: reservado para pruebas, nunca recibe correo real.
-- Se puede volver a ejecutar: no duplica (email es UNIQUE).
-- =====================================================================

INSERT INTO usuario (id_rol, nombre, apellido, email, password_hash, estado)
SELECT r.id_rol, v.nombre, v.apellido, v.email, '!', 'Activo'
FROM rol r
JOIN (
              SELECT 'Tienda' AS nombre, 'Norte'  AS apellido, 'tienda.norte@carga.smavib.test'  AS email
    UNION ALL SELECT 'Tienda',           'Centro',             'tienda.centro@carga.smavib.test'
    UNION ALL SELECT 'Tienda',           'Sur',                'tienda.sur@carga.smavib.test'
    UNION ALL SELECT 'Tienda',           'Bajío',              'tienda.bajio@carga.smavib.test'
) v
WHERE r.nombre = 'Vendedor'
ON DUPLICATE KEY UPDATE id_usuario = id_usuario;

-- Verificación: deben aparecer los 4 (más cualquier vendedor que ya existiera)
SELECT u.id_usuario, u.nombre, u.apellido, u.email, u.estado
FROM usuario u
JOIN rol r ON r.id_rol = u.id_rol
WHERE r.nombre = 'Vendedor'
ORDER BY u.id_usuario;

-- ---------------------------------------------------------------------
-- (Opcional, después de desplegar 1.1) Primer administrador:
-- 1.3 exige un token de Administrador y 1.1 solo crea Compradores, así que
-- el primer administrador se crea así: regístrate con POST /usuarios/registro
-- (la contraseña se hashea en la Lambda) y luego promueve tu cuenta.
-- Cambia el correo por el tuyo antes de ejecutarlo:
--
-- UPDATE usuario
-- SET id_rol = (SELECT id_rol FROM rol WHERE nombre = 'Administrador')
-- WHERE email = 'tu.correo@ejemplo.com';
-- ---------------------------------------------------------------------
