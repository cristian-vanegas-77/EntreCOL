"""MODELO: todas las consultas SQL del proyecto. No sabe nada de HTML ni de Flask.
Cada función hace UNA cosa y recibe los valores como parámetros (%s) para evitar la inyección SQL."""
from db import consultar, ejecutar

# ======================================================================
#  EMPLEADOS
# ======================================================================
ORDEN_EMPLEADOS = {
    "codigo": "e.codigo",
    "nombre": "e.nombre_completo",
    "dependencia": "d.nombre",
    "cargo": "c.nombre",
    "ingreso": "e.fecha_ingreso",
    "sueldo": "e.sueldo",
}

_FROM_EMPLEADOS = (
    "FROM empleado e "
    "JOIN cargo c ON c.id_cargo = e.id_cargo "
    "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
    "JOIN eps ON eps.id_eps = e.id_eps "
    "JOIN arl ON arl.id_arl = e.id_arl "
    "JOIN pension pen ON pen.id_pension = e.id_pension "
)


def listar_empleados(q="", id_dependencia=None, orden="nombre", sentido="ASC", pagina=1, por_pagina=15):
    """Devuelve (filas, total). Busca por nombre o código, filtra por dependencia y pagina."""
    pagina = max(1, int(pagina))
    condiciones, params = [], []
    if q:
        condiciones.append("(e.nombre_completo LIKE %s OR CAST(e.codigo AS CHAR) LIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if id_dependencia:
        condiciones.append("d.id_dependencia = %s")
        params.append(id_dependencia)
    where = ("WHERE " + " AND ".join(condiciones) + " ") if condiciones else ""

    columna = ORDEN_EMPLEADOS.get(orden, ORDEN_EMPLEADOS["nombre"])
    sentido = "DESC" if str(sentido).upper() == "DESC" else "ASC"

    total = consultar(f"SELECT COUNT(*) AS n {_FROM_EMPLEADOS}{where}", params, uno=True)["n"]
    filas = consultar(
        "SELECT e.codigo, e.nombre_completo, e.fecha_ingreso, e.sueldo, c.nombre AS cargo, "
        "d.nombre AS dependencia, eps.nombre AS eps, arl.nombre AS arl, pen.nombre AS pension "
        f"{_FROM_EMPLEADOS}{where}ORDER BY {columna} {sentido}, e.codigo ASC LIMIT %s OFFSET %s",
        params + [por_pagina, (pagina - 1) * por_pagina],
    )
    return filas, total


def obtener_empleado(codigo):
    return consultar(
        "SELECT codigo, nombre_completo, fecha_ingreso, sueldo, id_cargo, id_eps, id_arl, id_pension "
        "FROM empleado WHERE codigo = %s",
        (codigo,),
        uno=True,
    )


def existe_empleado(codigo):
    return consultar("SELECT 1 AS x FROM empleado WHERE codigo = %s", (codigo,), uno=True) is not None


def crear_empleado(d):
    ejecutar(
        "INSERT INTO empleado (codigo, nombre_completo, fecha_ingreso, sueldo, id_cargo, id_eps, id_arl, "
        "id_pension) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            d["codigo"],
            d["nombre"],
            d["fecha_ingreso"],
            d["sueldo"],
            d["id_cargo"],
            d["id_eps"],
            d["id_arl"],
            d["id_pension"],
        ),
    )


def actualizar_empleado(codigo, d):
    ejecutar(
        "UPDATE empleado SET nombre_completo=%s, fecha_ingreso=%s, sueldo=%s, id_cargo=%s, id_eps=%s, "
        "id_arl=%s, id_pension=%s WHERE codigo=%s",
        (
            d["nombre"],
            d["fecha_ingreso"],
            d["sueldo"],
            d["id_cargo"],
            d["id_eps"],
            d["id_arl"],
            d["id_pension"],
            codigo,
        ),
    )


def contar_dependientes(codigo):
    """Cuántas novedades y liquidaciones tiene un empleado (si tiene, no se puede borrar)."""
    return consultar(
        "SELECT (SELECT COUNT(*) FROM novedad WHERE codigo = %s) AS novedades, "
        "(SELECT COUNT(*) FROM liquidacion WHERE codigo = %s) AS liquidaciones",
        (codigo, codigo),
        uno=True,
    )


def eliminar_empleado(codigo):
    ejecutar("DELETE FROM empleado WHERE codigo = %s", (codigo,))


# ======================================================================
#  CATÁLOGOS (para llenar los <select> de los formularios)
# ======================================================================
def catalogos():
    return dict(
        dependencias=consultar("SELECT id_dependencia, nombre FROM dependencia ORDER BY nombre"),
        cargos=consultar(
            "SELECT c.id_cargo, c.nombre, d.nombre AS dependencia FROM cargo c "
            "JOIN dependencia d ON d.id_dependencia = c.id_dependencia ORDER BY d.nombre, c.nombre"
        ),
        eps=consultar("SELECT id_eps, nombre FROM eps ORDER BY nombre"),
        arl=consultar("SELECT id_arl, nombre FROM arl ORDER BY nombre"),
        pensiones=consultar("SELECT id_pension, nombre FROM pension ORDER BY nombre"),
        roles=consultar("SELECT id_rol, nombre FROM rol ORDER BY nombre"),
    )


# ======================================================================
#  USUARIOS Y AUDITORÍA
# ======================================================================
def listar_usuarios():
    return consultar(
        "SELECT u.id_usuario, u.username, u.nombre_completo, u.email, u.activo, "
        "u.intentos_fallidos, r.nombre AS rol, r.id_rol "
        "FROM usuario u JOIN rol r ON r.id_rol = u.id_rol ORDER BY u.username"
    )


def crear_usuario(username, password_hash, nombre_completo, email, id_rol):
    ejecutar(
        "INSERT INTO usuario (id_rol, username, password_hash, nombre_completo, email, activo) "
        "VALUES (%s, %s, %s, %s, %s, 1)",
        (id_rol, username, password_hash, nombre_completo, email),
    )


def cambiar_estado_usuario(id_usuario, activo):
    ejecutar("UPDATE usuario SET activo = %s, intentos_fallidos = 0 WHERE id_usuario = %s", (activo, id_usuario))


def listar_auditoria(limite=100):
    return consultar(
        "SELECT a.id_auditoria, a.fecha_hora, COALESCE(u.username, 'Sistema/Anónimo') AS usuario, "
        "a.accion, a.tabla_afectada, a.detalle, a.ip "
        "FROM auditoria a LEFT JOIN usuario u ON u.id_usuario = a.id_usuario "
        "ORDER BY a.fecha_hora DESC LIMIT %s",
        (int(limite),),
    )


# ======================================================================
#  NÓMINA: PERIODOS, NOVEDADES Y LIQUIDACIÓN
# ======================================================================
def listar_periodos():
    return consultar(
        "SELECT p.id_periodo, pa.anio, p.mes, p.fecha_inicio, p.fecha_fin, p.estado, "
        "pa.smmlv, pa.aux_transporte, pa.pct_salud_empleado, pa.pct_pension_empleado "
        "FROM periodo_nomina p "
        "JOIN parametro_anual pa ON pa.id_parametro = p.id_parametro "
        "ORDER BY pa.anio DESC, p.mes DESC"
    )


def listar_tipos_novedad():
    return consultar("SELECT id_tipo_novedad, nombre, porcentaje_pago FROM tipo_novedad ORDER BY nombre")


def listar_novedades(id_periodo=None):
    sql = (
        "SELECT n.id_novedad, n.codigo, e.nombre_completo, tn.nombre AS tipo_novedad, "
        "tn.porcentaje_pago, n.fecha_inicio, n.fecha_fin, "
        "(DATEDIFF(n.fecha_fin, n.fecha_inicio) + 1) AS dias, "
        "pa.anio, p.mes "
        "FROM novedad n "
        "JOIN empleado e ON e.codigo = n.codigo "
        "JOIN tipo_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad "
        "JOIN periodo_nomina p ON p.id_periodo = n.id_periodo "
        "JOIN parametro_anual pa ON pa.id_parametro = p.id_parametro "
    )
    params = []
    if id_periodo:
        sql += "WHERE n.id_periodo = %s "
        params.append(id_periodo)
    sql += "ORDER BY n.fecha_inicio DESC, e.nombre_completo ASC"
    return consultar(sql, params)


def crear_novedad(codigo, id_periodo, id_tipo_novedad, fecha_inicio, fecha_fin):
    ejecutar(
        "INSERT INTO novedad (codigo, id_periodo, id_tipo_novedad, fecha_inicio, fecha_fin) "
        "VALUES (%s, %s, %s, %s, %s)",
        (codigo, id_periodo, id_tipo_novedad, fecha_inicio, fecha_fin),
    )


def eliminar_novedad(id_novedad):
    ejecutar("DELETE FROM novedad WHERE id_novedad = %s", (id_novedad,))


def listar_liquidaciones(id_periodo=None):
    sql = (
        "SELECT l.id_liquidacion, l.codigo, e.nombre_completo, d.nombre AS dependencia, "
        "pa.anio, p.mes, l.dias_trabajados, l.total_devengado, l.total_deducciones, "
        "l.neto_pagar, l.fecha_liquidacion "
        "FROM liquidacion l "
        "JOIN empleado e ON e.codigo = l.codigo "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN periodo_nomina p ON p.id_periodo = l.id_periodo "
        "JOIN parametro_anual pa ON pa.id_parametro = p.id_parametro "
    )
    params = []
    if id_periodo:
        sql += "WHERE l.id_periodo = %s "
        params.append(id_periodo)
    sql += "ORDER BY pa.anio DESC, p.mes DESC, e.nombre_completo ASC"
    return consultar(sql, params)


def obtener_movimientos_liquidacion(id_liquidacion):
    """Detalle línea por línea (sueldo, auxilio, novedades, salud, pensión) de una liquidación."""
    return consultar(
        "SELECT cn.nombre AS concepto, cn.tipo, m.dias, m.valor "
        "FROM movimiento_nomina m "
        "JOIN concepto_nomina cn ON cn.id_concepto = m.id_concepto "
        "WHERE m.id_liquidacion = %s ORDER BY cn.tipo ASC, m.id_movimiento ASC",
        (id_liquidacion,),
    )


def liquidar_periodo(id_periodo, id_usuario):
    """Calcula la nómina del periodo con base en 30 días, novedades y parámetros anuales."""
    param = consultar(
        "SELECT pa.* FROM periodo_nomina p "
        "JOIN parametro_anual pa ON pa.id_parametro = p.id_parametro "
        "WHERE p.id_periodo = %s",
        (id_periodo,),
        uno=True,
    )
    if not param:
        return 0

    conceptos = {c["nombre"]: c["id_concepto"] for c in consultar("SELECT id_concepto, nombre FROM concepto_nomina")}
    smmlv = float(param["smmlv"])
    aux_trans = float(param["aux_transporte"])
    pct_salud = float(param["pct_salud_empleado"]) / 100.0
    pct_pension = float(param["pct_pension_empleado"]) / 100.0

    # Si se recalcula el periodo, limpia la liquidación anterior
    ejecutar("DELETE FROM liquidacion WHERE id_periodo = %s", (id_periodo,))

    empleados = consultar("SELECT codigo, sueldo FROM empleado")
    for emp in empleados:
        cod = emp["codigo"]
        sueldo = float(emp["sueldo"])
        valor_dia = sueldo / 30.0

        novedades = consultar(
            "SELECT tn.nombre, tn.porcentaje_pago, (DATEDIFF(n.fecha_fin, n.fecha_inicio) + 1) AS dias "
            "FROM novedad n JOIN tipo_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad "
            "WHERE n.codigo = %s AND n.id_periodo = %s",
            (cod, id_periodo),
        )

        dias_novedad = sum(int(n["dias"]) for n in novedades)
        dias_trabajados = max(0, 30 - dias_novedad)

        movimientos = []
        # 1. Sueldo días laborados
        val_sueldo = round(valor_dia * dias_trabajados, 2)
        movimientos.append((conceptos["SUELDO"], dias_trabajados, val_sueldo))

        # 2. Auxilio de transporte (si gana hasta 2 SMMLV, proporcional a días trabajados)
        val_aux = round((aux_trans / 30.0) * dias_trabajados, 2) if sueldo <= (2 * smmlv) else 0.0
        if val_aux > 0:
            movimientos.append((conceptos["AUXILIO_TRANSPORTE"], dias_trabajados, val_aux))

        # 3. Novedades (VACACIONES / INCAPACIDAD)
        val_novedades = 0.0
        for nov in novedades:
            dias_nov = int(nov["dias"])
            pct = float(nov["porcentaje_pago"]) / 100.0
            monto = round(valor_dia * dias_nov * pct, 2)
            val_novedades += monto
            id_conc = conceptos.get(nov["nombre"], conceptos["BONIFICACION"])
            movimientos.append((id_conc, dias_nov, monto))

        # 4. Deducciones de ley (sobre ingreso base sin auxilio de transporte)
        ibc = val_sueldo + val_novedades
        val_salud = round(ibc * pct_salud, 2)
        val_pension = round(ibc * pct_pension, 2)
        movimientos.append((conceptos["SALUD_EMPLEADO"], 30, val_salud))
        movimientos.append((conceptos["PENSION_EMPLEADO"], 30, val_pension))

        total_devengado = round(val_sueldo + val_aux + val_novedades, 2)
        total_deducciones = round(val_salud + val_pension, 2)
        neto_pagar = round(total_devengado - total_deducciones, 2)

        ejecutar(
            "INSERT INTO liquidacion (codigo, id_periodo, id_usuario, dias_trabajados, "
            "total_devengado, total_deducciones, neto_pagar) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cod, id_periodo, id_usuario, dias_trabajados, total_devengado, total_deducciones, neto_pagar),
        )
        liq = consultar(
            "SELECT id_liquidacion FROM liquidacion WHERE codigo = %s AND id_periodo = %s",
            (cod, id_periodo),
            uno=True,
        )
        for id_conc, d_mov, v_mov in movimientos:
            ejecutar(
                "INSERT INTO movimiento_nomina (id_liquidacion, id_concepto, dias, valor) VALUES (%s,%s,%s,%s)",
                (liq["id_liquidacion"], id_conc, d_mov, v_mov),
            )

    ejecutar("UPDATE periodo_nomina SET estado = 'LIQUIDADO' WHERE id_periodo = %s", (id_periodo,))
    return len(empleados)


# ======================================================================
#  ENTRETENIMIENTO (PELÍCULAS Y LIBROS)
# ======================================================================
def listar_peliculas(q="", pagina=1, por_pagina=15):
    pagina = max(1, int(pagina))
    where, params = "", []
    if q:
        where = "WHERE p.titulo LIKE %s "
        params = [f"%{q}%"]

    total = consultar(f"SELECT COUNT(*) AS n FROM pelicula p {where}", params, uno=True)["n"]
    filas = consultar(
        "SELECT p.id_pelicula, p.titulo, p.anio, "
        "COALESCE(GROUP_CONCAT(g.nombre ORDER BY g.nombre SEPARATOR ', '), 'Sin género') AS generos "
        "FROM pelicula p "
        "LEFT JOIN pelicula_genero pg ON pg.id_pelicula = p.id_pelicula "
        "LEFT JOIN genero g ON g.id_genero = pg.id_genero "
        f"{where}GROUP BY p.id_pelicula, p.titulo, p.anio "
        "ORDER BY p.titulo ASC LIMIT %s OFFSET %s",
        params + [por_pagina, (pagina - 1) * por_pagina],
    )
    return filas, total


def listar_libros(q="", pagina=1, por_pagina=15):
    pagina = max(1, int(pagina))
    where, params = "", []
    if q:
        where = "WHERE l.titulo LIKE %s OR a.nombre LIKE %s "
        params = [f"%{q}%", f"%{q}%"]

    total = consultar(
        "SELECT COUNT(DISTINCT l.id_libro) AS n FROM libro l "
        "LEFT JOIN libro_autor la ON la.id_libro = l.id_libro "
        f"LEFT JOIN autor a ON a.id_autor = la.id_autor {where}",
        params,
        uno=True,
    )["n"]
    filas = consultar(
        "SELECT l.id_libro, l.titulo, e.nombre AS editorial, l.rating_promedio, l.idioma, "
        "l.num_paginas, l.fecha_publicacion, "
        "COALESCE(GROUP_CONCAT(a.nombre SEPARATOR ', '), 'Desconocido') AS autores "
        "FROM libro l "
        "JOIN editorial e ON e.id_editorial = l.id_editorial "
        "LEFT JOIN libro_autor la ON la.id_libro = l.id_libro "
        "LEFT JOIN autor a ON a.id_autor = la.id_autor "
        f"{where}GROUP BY l.id_libro, l.titulo, e.nombre, l.rating_promedio, l.idioma, l.num_paginas, l.fecha_publicacion "
        "ORDER BY l.titulo ASC LIMIT %s OFFSET %s",
        params + [por_pagina, (pagina - 1) * por_pagina],
    )
    return filas, total


# ======================================================================
#  CONSULTAS PARA LOS 5 REPORTES (TODAS DEVUELVEN 'etiqueta' + VALORES)
# ======================================================================
def reporte_1_empleados_dependencia():
    """Reporte 1: Cantidad de empleados y masa salarial por dependencia."""
    return consultar(
        "SELECT d.nombre AS etiqueta, COUNT(e.codigo) AS cantidad, COALESCE(SUM(e.sueldo), 0) AS total_sueldo "
        "FROM dependencia d "
        "LEFT JOIN cargo c ON c.id_dependencia = d.id_dependencia "
        "LEFT JOIN empleado e ON e.id_cargo = c.id_cargo "
        "GROUP BY d.id_dependencia, d.nombre ORDER BY cantidad DESC"
    )


def reporte_2_peliculas_genero(limite=10):
    """Reporte 2: Top N géneros con más películas registradas."""
    return consultar(
        "SELECT g.nombre AS etiqueta, COUNT(pg.id_pelicula) AS cantidad "
        "FROM genero g "
        "JOIN pelicula_genero pg ON pg.id_genero = g.id_genero "
        "GROUP BY g.id_genero, g.nombre ORDER BY cantidad DESC LIMIT %s",
        (int(limite),),
    )


def reporte_3_libros_editorial(limite=10):
    """Reporte 3: Top N editoriales con más libros y su rating promedio."""
    return consultar(
        "SELECT e.nombre AS etiqueta, COUNT(l.id_libro) AS cantidad, "
        "ROUND(AVG(l.rating_promedio), 2) AS rating_promedio "
        "FROM editorial e "
        "JOIN libro l ON l.id_editorial = e.id_editorial "
        "GROUP BY e.id_editorial, e.nombre ORDER BY cantidad DESC LIMIT %s",
        (int(limite),),
    )


def reporte_4_top_libros_rating(limite=10):
    """Reporte 4: Top N libros mejor calificados (con mínimo 1000 calificaciones)."""
    return consultar(
        "SELECT LEFT(titulo, 35) AS etiqueta, rating_promedio AS valor, num_calificaciones "
        "FROM libro WHERE num_calificaciones >= 1000 "
        "ORDER BY rating_promedio DESC, num_calificaciones DESC LIMIT %s",
        (int(limite),),
    )


def reporte_5_nomina_por_periodo():
    """Reporte 5: Total devengado, deducciones y neto pagado por periodo liquidado."""
    return consultar(
        "SELECT CONCAT(pa.anio, '-', LPAD(p.mes, 2, '0')) AS etiqueta, "
        "COALESCE(SUM(l.total_devengado), 0) AS devengado, "
        "COALESCE(SUM(l.total_deducciones), 0) AS deducciones, "
        "COALESCE(SUM(l.neto_pagar), 0) AS neto "
        "FROM periodo_nomina p "
        "JOIN parametro_anual pa ON pa.id_parametro = p.id_parametro "
        "LEFT JOIN liquidacion l ON l.id_periodo = p.id_periodo "
        "GROUP BY p.id_periodo, pa.anio, p.mes ORDER BY pa.anio ASC, p.mes ASC"
    )