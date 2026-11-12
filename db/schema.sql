-- =====================================================================
--  EntreCOL+  |  Esquema MySQL 8.x (3FN)
--  Orden: SEGURIDAD -> NOMINA -> ENTRETENIMIENTO
-- =====================================================================

DROP DATABASE IF EXISTS entrecol;
CREATE DATABASE entrecol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE entrecol;

SET FOREIGN_KEY_CHECKS = 0;

-- =====================================================================
--  1. SEGURIDAD, ROLES Y AUDITORIA
-- =====================================================================

-- rol = perfil de permisos
CREATE TABLE rol (
    id_rol       INT AUTO_INCREMENT PRIMARY KEY,
    nombre       VARCHAR(40)  NOT NULL UNIQUE,
    descripcion  VARCHAR(200) NOT NULL
) ENGINE=InnoDB;

-- permiso = modulo + accion
CREATE TABLE permiso (
    id_permiso  INT AUTO_INCREMENT PRIMARY KEY,
    modulo      VARCHAR(30) NOT NULL,
    accion      VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_permiso (modulo, accion)
) ENGINE=InnoDB;

CREATE TABLE rol_permiso (
    id_rol      INT NOT NULL,
    id_permiso  INT NOT NULL,
    PRIMARY KEY (id_rol, id_permiso),
    CONSTRAINT fk_rp_rol     FOREIGN KEY (id_rol)     REFERENCES rol(id_rol)         ON DELETE CASCADE,
    CONSTRAINT fk_rp_permiso FOREIGN KEY (id_permiso) REFERENCES permiso(id_permiso) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE usuario (
    id_usuario         INT AUTO_INCREMENT PRIMARY KEY,
    id_rol             INT          NOT NULL,
    username           VARCHAR(40)  NOT NULL UNIQUE,
    password_hash      VARCHAR(255) NOT NULL,          -- bcrypt, nunca la clave en claro
    nombre_completo    VARCHAR(120) NOT NULL,
    email              VARCHAR(120) NOT NULL UNIQUE,
    activo             TINYINT(1)   NOT NULL DEFAULT 1,
    intentos_fallidos  TINYINT UNSIGNED NOT NULL DEFAULT 0,
    CONSTRAINT fk_usuario_rol FOREIGN KEY (id_rol) REFERENCES rol(id_rol)
) ENGINE=InnoDB;

-- id_usuario admite NULL para registrar intentos de login con un usuario inexistente
CREATE TABLE auditoria (
    id_auditoria    BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_usuario      INT NULL,
    accion          VARCHAR(40)  NOT NULL,             -- LOGIN, CREAR, EDITAR, ELIMINAR, CARGAR, LIQUIDAR, EXPORTAR...
    tabla_afectada  VARCHAR(40)  NULL,
    detalle         VARCHAR(500) NULL,
    ip              VARCHAR(45)  NULL,                 -- 45 caracteres alcanzan para IPv6
    fecha_hora      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_aud_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    INDEX idx_aud_fecha (fecha_hora)
) ENGINE=InnoDB;

-- Registro de cada archivo cargado (une Seguridad con Nomina y Entretenimiento)
CREATE TABLE carga_archivo (
    id_carga              INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario            INT NOT NULL,
    tipo_archivo          ENUM('NOMINA','PELICULAS','LIBROS') NOT NULL,
    nombre_archivo        VARCHAR(200) NOT NULL,
    fecha_hora            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    registros_cargados    INT NOT NULL DEFAULT 0,
    registros_rechazados  INT NOT NULL DEFAULT 0,
    estado                ENUM('PROCESADA','CON_ERRORES','FALLIDA') NOT NULL DEFAULT 'PROCESADA',
    CONSTRAINT fk_carga_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;

-- =====================================================================
--  2. NOMINA
-- =====================================================================

CREATE TABLE dependencia (
    id_dependencia INT AUTO_INCREMENT PRIMARY KEY,
    nombre         VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE cargo (
    id_cargo        INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(80) NOT NULL,
    id_dependencia  INT NOT NULL,
    UNIQUE KEY uq_cargo_dep (nombre, id_dependencia),  -- un mismo cargo puede existir en varias dependencias
    CONSTRAINT fk_cargo_dep FOREIGN KEY (id_dependencia) REFERENCES dependencia(id_dependencia)
) ENGINE=InnoDB;

CREATE TABLE eps (
    id_eps  INT AUTO_INCREMENT PRIMARY KEY,
    nombre  VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE arl (
    id_arl  INT AUTO_INCREMENT PRIMARY KEY,
    nombre  VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE pension (
    id_pension  INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE empleado (
    codigo           INT PRIMARY KEY,                  -- codigo personal del Excel (5001, 5002...)
    nombre_completo  VARCHAR(120) NOT NULL,
    fecha_ingreso    DATE NOT NULL,
    sueldo           DECIMAL(12,2) NOT NULL CHECK (sueldo >= 0),
    id_cargo         INT NOT NULL,
    id_eps           INT NOT NULL,
    id_arl           INT NOT NULL,
    id_pension       INT NOT NULL,
    CONSTRAINT fk_emp_cargo   FOREIGN KEY (id_cargo)   REFERENCES cargo(id_cargo),
    CONSTRAINT fk_emp_eps     FOREIGN KEY (id_eps)     REFERENCES eps(id_eps),
    CONSTRAINT fk_emp_arl     FOREIGN KEY (id_arl)     REFERENCES arl(id_arl),
    CONSTRAINT fk_emp_pension FOREIGN KEY (id_pension) REFERENCES pension(id_pension)
) ENGINE=InnoDB;

-- Parametros que cambian cada anio
CREATE TABLE parametro_anual (
    id_parametro            INT AUTO_INCREMENT PRIMARY KEY,
    anio                    SMALLINT NOT NULL UNIQUE,
    smmlv                   DECIMAL(12,2) NOT NULL,
    aux_transporte          DECIMAL(12,2) NOT NULL,
    pct_salud_empleado      DECIMAL(5,2) NOT NULL,
    pct_pension_empleado    DECIMAL(5,2) NOT NULL,
    pct_salud_empleador     DECIMAL(5,2) NOT NULL,
    pct_pension_empleador   DECIMAL(5,2) NOT NULL,
    pct_caja                DECIMAL(5,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE periodo_nomina (
    id_periodo    INT AUTO_INCREMENT PRIMARY KEY,
    id_parametro  INT NOT NULL,
    mes           TINYINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    fecha_inicio  DATE NOT NULL,
    fecha_fin     DATE NOT NULL,
    estado        ENUM('ABIERTO','LIQUIDADO','CERRADO') NOT NULL DEFAULT 'ABIERTO',
    UNIQUE KEY uq_periodo (id_parametro, mes),         -- un solo periodo por mes y anio
    CONSTRAINT fk_per_param FOREIGN KEY (id_parametro) REFERENCES parametro_anual(id_parametro),
    CONSTRAINT ck_per_fechas CHECK (fecha_fin >= fecha_inicio)
) ENGINE=InnoDB;

CREATE TABLE tipo_novedad (
    id_tipo_novedad  INT AUTO_INCREMENT PRIMARY KEY,
    nombre           VARCHAR(30) NOT NULL UNIQUE,
    porcentaje_pago  DECIMAL(5,2) NOT NULL             -- % del sueldo que se paga durante la novedad
) ENGINE=InnoDB;

CREATE TABLE novedad (
    id_novedad       INT AUTO_INCREMENT PRIMARY KEY,
    codigo           INT NOT NULL,
    id_periodo       INT NOT NULL,
    id_tipo_novedad  INT NOT NULL,
    fecha_inicio     DATE NOT NULL,
    fecha_fin        DATE NOT NULL,
    CONSTRAINT fk_nov_emp   FOREIGN KEY (codigo)          REFERENCES empleado(codigo),
    CONSTRAINT fk_nov_per   FOREIGN KEY (id_periodo)      REFERENCES periodo_nomina(id_periodo),
    CONSTRAINT fk_nov_tipo  FOREIGN KEY (id_tipo_novedad) REFERENCES tipo_novedad(id_tipo_novedad),
    CONSTRAINT ck_nov_fechas CHECK (fecha_fin >= fecha_inicio),
    INDEX idx_nov_periodo (id_periodo)
) ENGINE=InnoDB;

CREATE TABLE concepto_nomina (
    id_concepto  INT AUTO_INCREMENT PRIMARY KEY,
    nombre       VARCHAR(50) NOT NULL UNIQUE,
    tipo         ENUM('DEVENGO','DEDUCCION') NOT NULL
) ENGINE=InnoDB;

-- Una liquidacion por empleado y periodo
CREATE TABLE liquidacion (
    id_liquidacion     INT AUTO_INCREMENT PRIMARY KEY,
    codigo             INT NOT NULL,
    id_periodo         INT NOT NULL,
    id_usuario         INT NOT NULL,                   -- quien ejecuto la liquidacion
    dias_trabajados    TINYINT UNSIGNED NOT NULL,
    total_devengado    DECIMAL(14,2) NOT NULL DEFAULT 0,
    total_deducciones  DECIMAL(14,2) NOT NULL DEFAULT 0,
    neto_pagar         DECIMAL(14,2) NOT NULL DEFAULT 0,
    fecha_liquidacion  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_liq (codigo, id_periodo),
    CONSTRAINT fk_liq_emp FOREIGN KEY (codigo)     REFERENCES empleado(codigo),
    CONSTRAINT fk_liq_per FOREIGN KEY (id_periodo) REFERENCES periodo_nomina(id_periodo),
    CONSTRAINT fk_liq_usr FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario),
    CONSTRAINT ck_liq_dias CHECK (dias_trabajados <= 30)
) ENGINE=InnoDB;

-- Cada linea de la liquidacion (sueldo, transporte, bonificacion, salud, pension...)
CREATE TABLE movimiento_nomina (
    id_movimiento   INT AUTO_INCREMENT PRIMARY KEY,
    id_liquidacion  INT NOT NULL,
    id_concepto     INT NOT NULL,
    dias            TINYINT UNSIGNED NOT NULL DEFAULT 0,
    valor           DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_mov_liq  FOREIGN KEY (id_liquidacion) REFERENCES liquidacion(id_liquidacion) ON DELETE CASCADE,
    CONSTRAINT fk_mov_conc FOREIGN KEY (id_concepto)    REFERENCES concepto_nomina(id_concepto)
) ENGINE=InnoDB;

-- =====================================================================
--  3. ENTRETENIMIENTO
-- =====================================================================

CREATE TABLE genero (
    id_genero  INT AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- anio sale del titulo, ej. "Toy Story (1995)"
CREATE TABLE pelicula (
    id_pelicula  INT AUTO_INCREMENT PRIMARY KEY,       -- se conserva el id del archivo .dat
    titulo       VARCHAR(255) NOT NULL,
    anio         SMALLINT NULL,
    id_carga     INT NULL,
    CONSTRAINT fk_peli_carga FOREIGN KEY (id_carga) REFERENCES carga_archivo(id_carga) ON DELETE SET NULL,
    INDEX idx_peli_anio (anio)
) ENGINE=InnoDB;

CREATE TABLE pelicula_genero (
    id_pelicula  INT NOT NULL,
    id_genero    INT NOT NULL,
    PRIMARY KEY (id_pelicula, id_genero),
    CONSTRAINT fk_pg_peli   FOREIGN KEY (id_pelicula) REFERENCES pelicula(id_pelicula) ON DELETE CASCADE,
    CONSTRAINT fk_pg_genero FOREIGN KEY (id_genero)   REFERENCES genero(id_genero)
) ENGINE=InnoDB;

CREATE TABLE editorial (
    id_editorial  INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE autor (
    id_autor  INT AUTO_INCREMENT PRIMARY KEY,
    nombre    VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- fecha_publicacion admite NULL: hay libros con fecha invalida en el JSON
CREATE TABLE libro (
    id_libro            INT AUTO_INCREMENT PRIMARY KEY, -- se conserva el bookID del JSON
    id_editorial        INT NOT NULL,
    id_carga            INT NULL,
    titulo              VARCHAR(500) NOT NULL,
    rating_promedio     DECIMAL(3,2) NOT NULL DEFAULT 0 CHECK (rating_promedio BETWEEN 0 AND 5),
    isbn                VARCHAR(10) NULL,
    isbn13              VARCHAR(13) NULL,
    idioma              VARCHAR(15) NULL,
    num_paginas         INT NULL,
    num_calificaciones  INT NOT NULL DEFAULT 0,
    num_resenas         INT NOT NULL DEFAULT 0,
    fecha_publicacion   DATE NULL,
    CONSTRAINT fk_libro_edit  FOREIGN KEY (id_editorial) REFERENCES editorial(id_editorial),
    CONSTRAINT fk_libro_carga FOREIGN KEY (id_carga)     REFERENCES carga_archivo(id_carga) ON DELETE SET NULL,
    INDEX idx_libro_rating (rating_promedio),
    INDEX idx_libro_fecha  (fecha_publicacion)
) ENGINE=InnoDB;

CREATE TABLE libro_autor (
    id_libro  INT NOT NULL,
    id_autor  INT NOT NULL,
    PRIMARY KEY (id_libro, id_autor),
    CONSTRAINT fk_la_libro FOREIGN KEY (id_libro) REFERENCES libro(id_libro) ON DELETE CASCADE,
    CONSTRAINT fk_la_autor FOREIGN KEY (id_autor) REFERENCES autor(id_autor)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================
--  4. DATOS SEMILLA
-- =====================================================================

-- Roles
INSERT INTO rol (nombre, descripcion) VALUES
 ('ADMINISTRADOR',            'Gestiona usuarios, roles y todo el sistema'),
 ('ANALISTA_NOMINA',          'Gestiona periodos, novedades y liquidacion'),
 ('ANALISTA_ENTRETENIMIENTO', 'Carga y consulta peliculas y libros'),
 ('AUDITOR',                  'Solo consulta reportes y auditoria');

-- Permisos: cada modulo x cada accion
INSERT INTO permiso (modulo, accion)
SELECT m.modulo, a.accion
FROM (SELECT 'usuarios' AS modulo UNION SELECT 'empleados' UNION SELECT 'nomina'
      UNION SELECT 'entretenimiento' UNION SELECT 'cargas' UNION SELECT 'reportes'
      UNION SELECT 'auditoria') m
CROSS JOIN
     (SELECT 'crear' AS accion UNION SELECT 'leer' UNION SELECT 'actualizar'
      UNION SELECT 'eliminar' UNION SELECT 'exportar') a;

-- ADMINISTRADOR: todo
INSERT INTO rol_permiso (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso FROM rol r CROSS JOIN permiso p WHERE r.nombre = 'ADMINISTRADOR';

-- ANALISTA_NOMINA
INSERT INTO rol_permiso (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso FROM rol r JOIN permiso p
WHERE r.nombre = 'ANALISTA_NOMINA'
  AND ( p.modulo IN ('empleados','nomina')
     OR (p.modulo = 'cargas'   AND p.accion IN ('crear','leer'))
     OR (p.modulo = 'reportes' AND p.accion IN ('leer','exportar')) );

-- ANALISTA_ENTRETENIMIENTO
INSERT INTO rol_permiso (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso FROM rol r JOIN permiso p
WHERE r.nombre = 'ANALISTA_ENTRETENIMIENTO'
  AND ( p.modulo = 'entretenimiento'
     OR (p.modulo = 'cargas'   AND p.accion IN ('crear','leer'))
     OR (p.modulo = 'reportes' AND p.accion IN ('leer','exportar')) );

-- AUDITOR: solo lectura
INSERT INTO rol_permiso (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso FROM rol r JOIN permiso p
WHERE r.nombre = 'AUDITOR'
  AND ( (p.modulo = 'reportes'  AND p.accion IN ('leer','exportar'))
     OR (p.modulo = 'auditoria' AND p.accion = 'leer') );

-- Tipos de novedad (incapacidad paga 66.67 %; ajustar si el grupo usa otra regla)
INSERT INTO tipo_novedad (nombre, porcentaje_pago) VALUES
 ('VACACIONES',   100.00),
 ('INCAPACIDAD',   66.67);

-- Conceptos de nomina
INSERT INTO concepto_nomina (nombre, tipo) VALUES
 ('SUELDO',               'DEVENGO'),
 ('AUXILIO_TRANSPORTE',   'DEVENGO'),
 ('BONIFICACION',         'DEVENGO'),
 ('VACACIONES',           'DEVENGO'),
 ('INCAPACIDAD',          'DEVENGO'),
 ('SALUD_EMPLEADO',       'DEDUCCION'),
 ('PENSION_EMPLEADO',     'DEDUCCION');

-- Parametros 2022 (los datos de novedades del Excel son de marzo de 2022).
-- Revisar y ajustar los porcentajes del empleador segun lo que vea el grupo en clase.
INSERT INTO parametro_anual
 (anio, smmlv, aux_transporte, pct_salud_empleado, pct_pension_empleado,
  pct_salud_empleador, pct_pension_empleador, pct_caja)
VALUES (2022, 1000000.00, 117172.00, 4.00, 4.00, 8.50, 12.00, 4.00);

-- NOTA: el primer usuario ADMINISTRADOR no se inserta aqui porque password_hash
-- debe generarse con bcrypt. Se crea desde Python (script crear_admin).
