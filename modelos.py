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


def cambiar_rol_usuario(id_usuario, id_rol):
    ejecutar("UPDATE usuario SET id_rol = %s WHERE id_usuario = %s", (id_rol, id_usuario))


def actualizar_password_usuario(id_usuario, password_hash):
    ejecutar("UPDATE usuario SET password_hash = %s, intentos_fallidos = 0 WHERE id_usuario = %s", (password_hash, id_usuario))


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


def listar_parametros_anuales():
    return consultar("SELECT id_parametro, anio, smmlv, aux_transporte FROM parametro_anual ORDER BY anio DESC")


def crear_periodo(id_parametro, mes, fecha_inicio, fecha_fin):
    ejecutar(
        "INSERT INTO periodo_nomina (id_parametro, mes, fecha_inicio, fecha_fin, estado) "
        "VALUES (%s, %s, %s, %s, 'ABIERTO')",
        (id_parametro, mes, fecha_inicio, fecha_fin),
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
        val_sueldo = round(valor_dia * dias_trabajados, 2)
        movimientos.append((conceptos["SUELDO"], dias_trabajados, val_sueldo))

        val_aux = round((aux_trans / 30.0) * dias_trabajados, 2) if sueldo <= (2 * smmlv) else 0.0
        if val_aux > 0:
            movimientos.append((conceptos["AUXILIO_TRANSPORTE"], dias_trabajados, val_aux))

        val_novedades = 0.0
        for nov in novedades:
            dias_nov = int(nov["dias"])
            pct = float(nov["porcentaje_pago"]) / 100.0
            monto = round(valor_dia * dias_nov * pct, 2)
            val_novedades += monto
            id_conc = conceptos.get(nov["nombre"], conceptos["BONIFICACION"])
            movimientos.append((id_conc, dias_nov, monto))

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
#  REPORTES OFICIALES DEL PROYECTO
# ======================================================================
def reporte_1_nomina_listados(orden_nombre="ASC"):
    """Reporte 1: Nómina por empresa, dependencia y cargo (nombres ASC/DESC)."""
    sentido = "DESC" if str(orden_nombre).upper() == "DESC" else "ASC"

    por_dependencia = consultar(
        "SELECT d.nombre AS etiqueta, COUNT(e.codigo) AS cantidad, COALESCE(SUM(e.sueldo), 0) AS total_sueldo "
        "FROM dependencia d "
        "LEFT JOIN cargo c ON c.id_dependencia = d.id_dependencia "
        "LEFT JOIN empleado e ON e.id_cargo = c.id_cargo "
        "GROUP BY d.id_dependencia, d.nombre "
        "ORDER BY d.nombre ASC"
    )

    por_cargo_dep = consultar(
        "SELECT d.nombre AS dependencia, c.nombre AS cargo, COUNT(e.codigo) AS cantidad "
        "FROM dependencia d "
        "JOIN cargo c ON c.id_dependencia = d.id_dependencia "
        "LEFT JOIN empleado e ON e.id_cargo = c.id_cargo "
        "GROUP BY d.id_dependencia, d.nombre, c.id_cargo, c.nombre "
        "ORDER BY d.nombre ASC, c.nombre ASC"
    )

    empleados_empresa = consultar(
        "SELECT e.codigo, e.nombre_completo, d.nombre AS dependencia, c.nombre AS cargo, e.sueldo "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        f"ORDER BY e.nombre_completo {sentido}, e.codigo ASC"
    )

    empleados_por_dep = consultar(
        "SELECT e.codigo, e.nombre_completo, d.nombre AS dependencia, c.nombre AS cargo, e.sueldo "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        f"ORDER BY d.nombre ASC, e.nombre_completo {sentido}, e.codigo ASC"
    )

    empleados_por_dep_cargo = consultar(
        "SELECT e.codigo, e.nombre_completo, d.nombre AS dependencia, c.nombre AS cargo, e.sueldo "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        f"ORDER BY d.nombre ASC, c.nombre ASC, e.nombre_completo {sentido}, e.codigo ASC"
    )

    return dict(
        sentido=sentido,
        total_empleados=len(empleados_empresa),
        por_dependencia=por_dependencia,
        por_cargo_dep=por_cargo_dep,
        empleados_empresa=empleados_empresa,
        empleados_por_dep=empleados_por_dep,
        empleados_por_dep_cargo=empleados_por_dep_cargo,
    )


def reporte_2_informacion_personal():
    """Reporte 2: Ficha completa de información personal, seguridad social y discriminación de novedades."""
    return consultar(
        "SELECT "
        "  CONCAT(e.nombre_completo, ' (', e.codigo, ')') AS empleado_codigo, "
        "  d.nombre AS dependencia, "
        "  c.nombre AS cargo, "
        "  DATE_FORMAT(e.fecha_ingreso, '%d/%m/%Y') AS fecha_ingreso, "
        "  eps.nombre AS eps, "
        "  CONCAT(pen.nombre, ' ($', FORMAT(ROUND(e.sueldo * 0.04, 0), 0), ')') AS aporte_pension, "
        "  CONCAT('$', FORMAT(e.sueldo, 0)) AS salario, "
        "  COALESCE("
        "    ("
        "      SELECT GROUP_CONCAT("
        "        CONCAT(tn.nombre, ': ', DATE_FORMAT(n.fecha_inicio, '%d/%m/%Y'), ' al ', "
        "               DATE_FORMAT(n.fecha_fin, '%d/%m/%Y'), ' (', DATEDIFF(n.fecha_fin, n.fecha_inicio) + 1, ' d)') "
        "        ORDER BY n.fecha_inicio SEPARATOR ' | '"
        "      ) "
        "      FROM novedad n "
        "      JOIN tipo_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad "
        "      WHERE n.codigo = e.codigo"
        "    ), "
        "    'Sin novedades'"
        "  ) AS novedades "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN eps ON eps.id_eps = e.id_eps "
        "JOIN pension pen ON pen.id_pension = e.id_pension "
        "ORDER BY e.nombre_completo ASC"
    )


def reporte_3_salud_pension(orden_nombre="ASC"):
    """Reporte 3: Frecuencias por EPS/Pensión, comparativas por dependencia y listas por cargo (nombres ASC/DESC)."""
    sentido = "DESC" if str(orden_nombre).upper() == "DESC" else "ASC"

    freq_eps = consultar(
        "SELECT eps.nombre AS etiqueta, COUNT(e.codigo) AS cantidad "
        "FROM eps LEFT JOIN empleado e ON e.id_eps = eps.id_eps "
        "GROUP BY eps.id_eps, eps.nombre ORDER BY eps.nombre ASC"
    )

    freq_pension = consultar(
        "SELECT pen.nombre AS etiqueta, COUNT(e.codigo) AS cantidad "
        "FROM pension pen LEFT JOIN empleado e ON e.id_pension = pen.id_pension "
        "GROUP BY pen.id_pension, pen.nombre ORDER BY pen.nombre ASC"
    )

    eps_por_dep = consultar(
        "SELECT d.nombre AS dependencia, eps.nombre AS eps, COUNT(e.codigo) AS cantidad "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN eps ON eps.id_eps = e.id_eps "
        "GROUP BY d.id_dependencia, d.nombre, eps.id_eps, eps.nombre "
        "ORDER BY d.nombre ASC, eps.nombre ASC"
    )

    pension_por_dep = consultar(
        "SELECT d.nombre AS dependencia, pen.nombre AS pension, COUNT(e.codigo) AS cantidad "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN pension pen ON pen.id_pension = e.id_pension "
        "GROUP BY d.id_dependencia, d.nombre, pen.id_pension, pen.nombre "
        "ORDER BY d.nombre ASC, pen.nombre ASC"
    )

    conteo_cargo_eps = consultar(
        "SELECT c.nombre AS cargo, eps.nombre AS eps, COUNT(e.codigo) AS cantidad "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN eps ON eps.id_eps = e.id_eps "
        "GROUP BY c.id_cargo, c.nombre, eps.id_eps, eps.nombre "
        "ORDER BY c.nombre ASC, eps.nombre ASC"
    )

    lista_cargo_eps = consultar(
        "SELECT c.nombre AS cargo, eps.nombre AS eps, e.codigo, e.nombre_completo, d.nombre AS dependencia "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN eps ON eps.id_eps = e.id_eps "
        f"ORDER BY c.nombre ASC, eps.nombre ASC, e.nombre_completo {sentido}, e.codigo ASC"
    )

    conteo_cargo_pension = consultar(
        "SELECT c.nombre AS cargo, pen.nombre AS pension, COUNT(e.codigo) AS cantidad "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN pension pen ON pen.id_pension = e.id_pension "
        "GROUP BY c.id_cargo, c.nombre, pen.id_pension, pen.nombre "
        "ORDER BY c.nombre ASC, pen.nombre ASC"
    )

    lista_cargo_pension = consultar(
        "SELECT c.nombre AS cargo, pen.nombre AS pension, e.codigo, e.nombre_completo, d.nombre AS dependencia "
        "FROM empleado e "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN pension pen ON pen.id_pension = e.id_pension "
        f"ORDER BY c.nombre ASC, pen.nombre ASC, e.nombre_completo {sentido}, e.codigo ASC"
    )

    return dict(
        sentido=sentido,
        freq_eps=freq_eps,
        freq_pension=freq_pension,
        eps_por_dep=eps_por_dep,
        pension_por_dep=pension_por_dep,
        conteo_cargo_eps=conteo_cargo_eps,
        lista_cargo_eps=lista_cargo_eps,
        conteo_cargo_pension=conteo_cargo_pension,
        lista_cargo_pension=lista_cargo_pension,
    )


def reporte_4_novedades(f1_str=None, f2_str=None):
    """Reporte 4: Empleados con novedades en un rango F1 vs F2 (MM/AAAA) y cantidad por dependencia y cargo."""
    import re
    from datetime import date

    patron = re.compile(r"^(0[1-9]|1[0-2])/(\d{4})$")

    if not (f1_str and patron.match(f1_str) and f2_str and patron.match(f2_str)):
        rango = consultar(
            "SELECT DATE_FORMAT(MIN(fecha_inicio), '%m/%Y') AS f1, "
            "DATE_FORMAT(MAX(fecha_fin), '%m/%Y') AS f2 FROM novedad",
            uno=True,
        )
        hoy_ym = date.today().strftime("%m/%Y")
        f1_str = rango["f1"] if rango and rango["f1"] else hoy_ym
        f2_str = rango["f2"] if rango and rango["f2"] else hoy_ym

    m1, y1 = f1_str.split("/")
    m2, y2 = f2_str.split("/")

    if (int(y1), int(m1)) > (int(y2), int(m2)):
        f1_str, f2_str = f2_str, f1_str
        m1, y1, m2, y2 = m2, y2, m1, y1

    fecha_desde = f"{y1}-{m1}-01"
    fecha_hasta_base = f"{y2}-{m2}-01"

    lista_empleados = consultar(
        "SELECT e.codigo, e.nombre_completo, d.nombre AS dependencia, c.nombre AS cargo, "
        "tn.nombre AS tipo_novedad, "
        "DATE_FORMAT(n.fecha_inicio, '%d/%m/%Y') AS fecha_inicio, "
        "DATE_FORMAT(n.fecha_fin, '%d/%m/%Y') AS fecha_fin, "
        "(DATEDIFF(n.fecha_fin, n.fecha_inicio) + 1) AS dias "
        "FROM novedad n "
        "JOIN empleado e ON e.codigo = n.codigo "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "JOIN tipo_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad "
        "WHERE n.fecha_inicio <= LAST_DAY(%s) AND n.fecha_fin >= %s "
        "ORDER BY d.nombre ASC, c.nombre ASC, e.nombre_completo ASC, n.fecha_inicio ASC",
        (fecha_hasta_base, fecha_desde),
    )

    por_dep_cargo = consultar(
        "SELECT d.nombre AS dependencia, c.nombre AS cargo, "
        "COUNT(DISTINCT n.codigo) AS cantidad_empleados, "
        "COUNT(n.id_novedad) AS total_novedades "
        "FROM novedad n "
        "JOIN empleado e ON e.codigo = n.codigo "
        "JOIN cargo c ON c.id_cargo = e.id_cargo "
        "JOIN dependencia d ON d.id_dependencia = c.id_dependencia "
        "WHERE n.fecha_inicio <= LAST_DAY(%s) AND n.fecha_fin >= %s "
        "GROUP BY d.id_dependencia, d.nombre, c.id_cargo, c.nombre "
        "ORDER BY d.nombre ASC, c.nombre ASC",
        (fecha_hasta_base, fecha_desde),
    )

    empleados_unicos = len({r["codigo"] for r in lista_empleados})

    return dict(
        f1=f1_str,
        f2=f2_str,
        empleados_unicos=empleados_unicos,
        lista_empleados=lista_empleados,
        por_dep_cargo=por_dep_cargo,
    )


def reporte_5_entretenimiento(anio_f1=None, anio_f2=None, top_n=10, num_generos=2, orden_nombre="ASC"):
    """Reporte 5: Base-Entretenimiento (películas por género F1..F2, Top N libros, Top 5 mejor/peor por año,
    películas con N géneros y frecuencias de películas por género y libros por año F1..F2)."""
    sentido = "DESC" if str(orden_nombre).upper() == "DESC" else "ASC"
    top_n = max(1, min(100, int(top_n or 10)))
    num_generos = max(1, min(15, int(num_generos or 2)))

    rango_p = consultar("SELECT MIN(anio) AS min_a, MAX(anio) AS max_a FROM pelicula WHERE anio IS NOT NULL", uno=True)
    rango_l = consultar(
        "SELECT MIN(YEAR(fecha_publicacion)) AS min_a, MAX(YEAR(fecha_publicacion)) AS max_a "
        "FROM libro WHERE fecha_publicacion IS NOT NULL",
        uno=True,
    )
    anios_min = [x for x in (rango_p["min_a"] if rango_p else None, rango_l["min_a"] if rango_l else None) if x]
    anios_max = [x for x in (rango_p["max_a"] if rango_p else None, rango_l["max_a"] if rango_l else None) if x]

    min_default = min(anios_min) if anios_min else 1990
    max_default = max(anios_max) if anios_max else 2026

    try:
        f1 = int(anio_f1) if anio_f1 else min_default
    except (ValueError, TypeError):
        f1 = min_default
    try:
        f2 = int(anio_f2) if anio_f2 else max_default
    except (ValueError, TypeError):
        f2 = max_default

    if f1 > f2:
        f1, f2 = f2, f1

    # a. Listado de películas por género entre F1 y F2 (nombres ASC/DESC)
    peliculas_genero = consultar(
        "SELECT g.nombre AS genero, p.id_pelicula, p.titulo, p.anio "
        "FROM pelicula p "
        "JOIN pelicula_genero pg ON pg.id_pelicula = p.id_pelicula "
        "JOIN genero g ON g.id_genero = pg.id_genero "
        "WHERE p.anio BETWEEN %s AND %s "
        f"ORDER BY g.nombre ASC, p.titulo {sentido}, p.anio ASC",
        (f1, f2),
    )

    # b. Listado del Top N libros con mejor rating (reordenados por título ASC/DESC)
    top_n_libros = consultar(
        "SELECT * FROM ("
        "  SELECT l.id_libro, l.titulo, e.nombre AS editorial, "
        "  COALESCE(GROUP_CONCAT(DISTINCT a.nombre SEPARATOR ', '), 'Desconocido') AS autores, "
        "  YEAR(l.fecha_publicacion) AS anio, l.rating_promedio, l.num_calificaciones "
        "  FROM libro l "
        "  JOIN editorial e ON e.id_editorial = l.id_editorial "
        "  LEFT JOIN libro_autor la ON la.id_libro = l.id_libro "
        "  LEFT JOIN autor a ON a.id_autor = la.id_autor "
        "  WHERE l.rating_promedio IS NOT NULL "
        "  GROUP BY l.id_libro, l.titulo, e.nombre, l.fecha_publicacion, l.rating_promedio, l.num_calificaciones "
        "  ORDER BY l.rating_promedio DESC, l.num_calificaciones DESC "
        "  LIMIT %s"
        f") sub ORDER BY sub.titulo {sentido}",
        (top_n,),
    )

    # c. Top 5 libros mejor rating por año y Top 5 peor rating por año (nombres ASC/DESC)
    libros_con_anio = consultar(
        "SELECT l.id_libro, l.titulo, YEAR(l.fecha_publicacion) AS anio, "
        "l.rating_promedio, l.num_calificaciones, "
        "COALESCE(GROUP_CONCAT(DISTINCT a.nombre SEPARATOR ', '), 'Desconocido') AS autores "
        "FROM libro l "
        "LEFT JOIN libro_autor la ON la.id_libro = l.id_libro "
        "LEFT JOIN autor a ON a.id_autor = la.id_autor "
        "WHERE l.fecha_publicacion IS NOT NULL AND l.rating_promedio IS NOT NULL "
        "GROUP BY l.id_libro, l.titulo, l.fecha_publicacion, l.rating_promedio, l.num_calificaciones"
    )
    por_anio = {}
    for lib in libros_con_anio:
        por_anio.setdefault(lib["anio"], []).append(lib)

    reverso_titulo = sentido == "DESC"
    top5_mejor_anio = []
    top5_peor_anio = []
    for anio in sorted(por_anio.keys()):
        grupo = por_anio[anio]
        mejores = sorted(
            grupo,
            key=lambda x: (-float(x["rating_promedio"]), -(x["num_calificaciones"] or 0), x["titulo"]),
        )[:5]
        mejores.sort(key=lambda x: x["titulo"].lower(), reverse=reverso_titulo)
        top5_mejor_anio.extend(mejores)

        peores = sorted(
            grupo,
            key=lambda x: (float(x["rating_promedio"]), -(x["num_calificaciones"] or 0), x["titulo"]),
        )[:5]
        peores.sort(key=lambda x: x["titulo"].lower(), reverse=reverso_titulo)
        top5_peor_anio.extend(peores)

    # d. Listado y cantidad de películas, con sus géneros, que tienen exactamente N géneros (nombres ASC/DESC)
    peliculas_n_generos = consultar(
        "SELECT p.id_pelicula, p.titulo, p.anio, COUNT(g.id_genero) AS total_generos, "
        "GROUP_CONCAT(g.nombre ORDER BY g.nombre SEPARATOR ', ') AS generos "
        "FROM pelicula p "
        "JOIN pelicula_genero pg ON pg.id_pelicula = p.id_pelicula "
        "JOIN genero g ON g.id_genero = pg.id_genero "
        "GROUP BY p.id_pelicula, p.titulo, p.anio "
        "HAVING COUNT(g.id_genero) = %s "
        f"ORDER BY p.titulo {sentido}, p.anio ASC",
        (num_generos,),
    )

    # e. Frecuencia de películas por género
    freq_peliculas_genero = consultar(
        "SELECT g.nombre AS etiqueta, COUNT(pg.id_pelicula) AS cantidad "
        "FROM genero g "
        "LEFT JOIN pelicula_genero pg ON pg.id_genero = g.id_genero "
        "GROUP BY g.id_genero, g.nombre "
        "ORDER BY cantidad DESC, g.nombre ASC"
    )

    # f. Frecuencia de libros por año de publicación entre F1 y F2
    freq_libros_anio = consultar(
        "SELECT CAST(YEAR(fecha_publicacion) AS CHAR) AS etiqueta, COUNT(*) AS cantidad "
        "FROM libro "
        "WHERE fecha_publicacion IS NOT NULL AND YEAR(fecha_publicacion) BETWEEN %s AND %s "
        "GROUP BY YEAR(fecha_publicacion) "
        "ORDER BY YEAR(fecha_publicacion) ASC",
        (f1, f2),
    )

    return dict(
        f1=f1,
        f2=f2,
        top_n=top_n,
        num_generos=num_generos,
        sentido=sentido,
        peliculas_genero=peliculas_genero,
        top_n_libros=top_n_libros,
        top5_mejor_anio=top5_mejor_anio,
        top5_peor_anio=top5_peor_anio,
        peliculas_n_generos=peliculas_n_generos,
        cantidad_n_generos=len(peliculas_n_generos),
        freq_peliculas_genero=freq_peliculas_genero,
        freq_libros_anio=freq_libros_anio,
    ) 