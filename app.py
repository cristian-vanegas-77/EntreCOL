"""CONTROLADOR: recibe las peticiones del navegador, llama al modelo / seguridad y elige la vista.

Ejecutar:   python app.py      y abrir  http://127.0.0.1:5000
"""
import os
import secrets
from datetime import timedelta

import modelos as mod
import reportes as rep

from dotenv import load_dotenv
from flask import (Flask, Response, abort, flash, redirect, render_template, request, session, url_for)

import seguridad as seg
from db import consultar

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambiar_esto")
app.permanent_session_lifetime = timedelta(minutes=30)      # la sesión expira a los 30 min

MAX_INTENTOS_CAPTCHA = 3

# Módulos del menú. 'endpoint' se llena a medida que se construyen las pantallas.
MODULOS = [
    dict(modulo="empleados", titulo="Empleados", descr="Consultar y administrar empleados", endpoint="empleados_lista"),
    dict(modulo="nomina", titulo="Nómina", descr="Periodos, novedades y liquidación", endpoint="nomina_panel"),
    dict(modulo="entretenimiento", titulo="Entretenimiento", descr="Películas y libros", endpoint="entretenimiento"),
    dict(modulo="cargas", titulo="Cargas de archivos", descr="Excel, DAT y JSON", endpoint="cargas_panel"),
    dict(modulo="reportes", titulo="Reportes", descr="Vista previa y exportación a PDF", endpoint="reportes_panel"),
    dict(modulo="usuarios", titulo="Usuarios y roles", descr="Administrar el acceso", endpoint="usuarios_lista"),
    dict(modulo="auditoria", titulo="Auditoría", descr="Registro de acciones", endpoint="auditoria_lista"),
]

# ----------------------------------------------------------------------
#  Protección CSRF: cada formulario POST lleva un token secreto de la sesión
# ----------------------------------------------------------------------
@app.before_request
def proteger_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    if request.method == "POST" and request.form.get("csrf") != session["csrf"]:
        abort(400)


@app.context_processor
def variables_para_plantillas():
    return {"csrf_token": session.get("csrf", "")}


# ----------------------------------------------------------------------
#  Inicio de sesión en dos pasos:  1) usuario + clave   2) captcha
# ----------------------------------------------------------------------
@app.route("/")
def inicio():
    return redirect(url_for("menu" if "usuario_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("menu"))
    if request.method == "POST":
        usuario, error = seg.autenticar(request.form.get("username", "").strip(), request.form.get("clave", ""))
        if error:
            flash(error, "error")
        else:
            session.clear()
            session["pre_auth"] = usuario["id_usuario"]     # pasó el paso 1, falta el captcha
            session["intentos_captcha"] = 0
            return redirect(url_for("verificar"))
    return render_template("login.html", paso=1)


@app.route("/captcha.png")
def captcha_png():
    if "pre_auth" not in session:
        abort(404)
    texto, png = seg.generar_captcha()
    session["captcha"] = texto
    respuesta = Response(png, mimetype="image/png")
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.route("/verificar", methods=["GET", "POST"])
def verificar():
    id_usuario = session.get("pre_auth")
    if not id_usuario:
        return redirect(url_for("login"))
    if request.method == "POST":
        esperado = session.pop("captcha", None)             # cada captcha sirve una sola vez
        escrito = request.form.get("captcha", "").strip().upper()
        if esperado and escrito == esperado:
            completar_login(id_usuario)
            return redirect(url_for("menu"))
        session["intentos_captcha"] = session.get("intentos_captcha", 0) + 1
        seg.auditar("CAPTCHA_FALLIDO", "usuario", id_usuario=id_usuario)
        if session["intentos_captcha"] >= MAX_INTENTOS_CAPTCHA:
            session.clear()
            flash("Demasiados intentos con el captcha. Inicia sesión de nuevo.", "error")
            return redirect(url_for("login"))
        flash("El texto no coincide. Prueba con la nueva imagen.", "error")
    return render_template("login.html", paso=2, t=secrets.token_hex(4))


def completar_login(id_usuario):
    u = consultar(
        "SELECT u.id_usuario, u.username, u.nombre_completo, u.id_rol, r.nombre AS rol "
        "FROM usuario u JOIN rol r ON r.id_rol = u.id_rol WHERE u.id_usuario=%s", (id_usuario,), uno=True)
    permisos = seg.permisos_de_rol(u["id_rol"])
    session.clear()                                          # sesión nueva al autenticarse
    session.permanent = True
    session.update(usuario_id=u["id_usuario"], username=u["username"], nombre=u["nombre_completo"],
                   rol=u["rol"], permisos=permisos)
    seg.auditar("LOGIN", "usuario", "inicio de sesión correcto")


@app.route("/logout", methods=["POST"])
def logout():
    if "usuario_id" in session:
        seg.auditar("LOGOUT", "usuario")
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
#  Menú principal: cada rol ve solo los módulos a los que tiene permiso de lectura
# ----------------------------------------------------------------------
@app.route("/menu")
@seg.login_requerido
def menu():
    visibles = [m for m in MODULOS if f"{m['modulo']}:leer" in session["permisos"]]
    return render_template("menu.html", modulos=visibles)


@app.errorhandler(403)
def prohibido(_):
    return render_template("error.html", codigo=403, mensaje="Tu rol no tiene permiso para esta acción."), 403


@app.errorhandler(400)
def peticion_invalida(_):
    return render_template("error.html", codigo=400, mensaje="Petición inválida. Recarga la página."), 400


# ----------------------------------------------------------------------
#  Módulo: Reportes (Vista previa con gráficas y exportación a PDF)
# ----------------------------------------------------------------------
@app.route("/reportes")
@seg.requiere_permiso("reportes", "leer")
def reportes_panel():
    return render_template("reportes.html", reporte_id=None)


@app.route("/reportes/<int:num>")
@seg.requiere_permiso("reportes", "leer")
def ver_reporte(num):
    limite = max(3, min(30, request.args.get("limite", 10, type=int)))
    formato = request.args.get("formato", "html")
    orden_nombre = "DESC" if request.args.get("orden", "ASC").upper() == "DESC" else "ASC"
    f1 = request.args.get("f1", "").strip()
    f2 = request.args.get("f2", "").strip()
    top_n = max(1, min(100, request.args.get("top_n", 10, type=int)))
    num_generos = max(1, min(15, request.args.get("num_generos", 2, type=int)))

    datos_nomina = None
    datos_sp = None
    datos_nov = None
    datos_ent = None
    grafica = None
    grafica_extra = None

    if num == 1:
        titulo = f"Reporte de Nómina — Empleados por Empresa, Dependencia y Cargo (Nombre {orden_nombre})"
        datos_nomina = mod.reporte_1_nomina_listados(orden_nombre)
        filas = datos_nomina["por_dependencia"]
        columnas = ["Dependencia", "Cantidad de Empleados", "Masa Salarial ($)"]
        claves = ["etiqueta", "cantidad", "total_sueldo"]
        grafica = rep.generar_grafica_torta(
            [f["etiqueta"] for f in filas], [f["cantidad"] for f in filas],
            "Distribución de Empleados por Dependencia"
        )
        grafica_extra = rep.generar_grafica_barras_comparativas(
            datos_nomina["por_cargo_dep"], "dependencia", "cargo", "cantidad",
            "Comparativa de Empleados por Dependencia y Cargo", "Dependencia", "Cantidad"
        )
    elif num == 2:
        titulo = "Reporte de Información Personal y Discriminación de Novedades"
        filas = mod.reporte_2_informacion_personal()
        columnas = [
            "Nombre Completo + Código",
            "Dependencia",
            "Cargo",
            "Fecha Ingreso",
            "EPS",
            "Aporte Pensión",
            "Salario",
            "Discriminación de Novedades",
        ]
        claves = [
            "empleado_codigo",
            "dependencia",
            "cargo",
            "fecha_ingreso",
            "eps",
            "aporte_pension",
            "salario",
            "novedades",
        ]
    elif num == 3:
        titulo = f"Reporte de Salud y Pensión (Nombre {orden_nombre})"
        datos_sp = mod.reporte_3_salud_pension(orden_nombre)
        filas = []
        columnas = []
        claves = []
        datos_sp["graf_eps"] = rep.generar_grafica_barras(
            [f["etiqueta"] for f in datos_sp["freq_eps"]],
            [f["cantidad"] for f in datos_sp["freq_eps"]],
            "a. Frecuencia por EPS — Toda la Empresa",
            "EPS",
            "Empleados",
        )
        datos_sp["graf_pension"] = rep.generar_grafica_barras(
            [f["etiqueta"] for f in datos_sp["freq_pension"]],
            [f["cantidad"] for f in datos_sp["freq_pension"]],
            "b. Frecuencia por Pensión — Toda la Empresa",
            "Fondo de Pensión",
            "Empleados",
        )
        datos_sp["graf_eps_dep"] = rep.generar_grafica_barras_comparativas(
            datos_sp["eps_por_dep"],
            "dependencia",
            "eps",
            "cantidad",
            "c. Comparativa de Frecuencias por EPS por Dependencia",
            "Dependencia",
            "Empleados",
        )
        datos_sp["graf_pension_dep"] = rep.generar_grafica_barras_comparativas(
            datos_sp["pension_por_dep"],
            "dependencia",
            "pension",
            "cantidad",
            "d. Comparativa de Frecuencias por Pensión por Dependencia",
            "Dependencia",
            "Empleados",
        )
    elif num == 4:
        datos_nov = mod.reporte_4_novedades(f1, f2)
        f1, f2 = datos_nov["f1"], datos_nov["f2"]
        titulo = f"Reporte de Novedades ({f1} vs {f2})"
        filas = []
        columnas = []
        claves = []
    elif num == 5:
        datos_ent = mod.reporte_5_entretenimiento(
            anio_f1=f1,
            anio_f2=f2,
            top_n=top_n,
            num_generos=num_generos,
            orden_nombre=orden_nombre,
        )
        f1, f2 = str(datos_ent["f1"]), str(datos_ent["f2"])
        titulo = f"Reporte Base-Entretenimiento ({f1} – {f2} · Nombres {orden_nombre})"
        filas = []
        columnas = []
        claves = []
        datos_ent["graf_peliculas_genero"] = rep.generar_grafica_barras(
            [g["etiqueta"] for g in datos_ent["freq_peliculas_genero"]],
            [g["cantidad"] for g in datos_ent["freq_peliculas_genero"]],
            "e. Frecuencia de Películas por Género",
            "Género",
            "Cantidad de Películas",
        )
        datos_ent["graf_libros_anio"] = rep.generar_grafica_barras(
            [a["etiqueta"] for a in datos_ent["freq_libros_anio"]],
            [a["cantidad"] for a in datos_ent["freq_libros_anio"]],
            f"f. Frecuencia de Libros por Año de Publicación ({f1} – {f2})",
            "Año",
            "Cantidad de Libros",
        )
    else:
        abort(404)

    html = render_template(
        "reportes.html",
        reporte_id=num,
        titulo=titulo,
        filas=filas,
        columnas=columnas,
        claves=claves,
        grafica=grafica,
        grafica_extra=grafica_extra,
        limite=limite,
        orden_nombre=orden_nombre,
        f1=f1,
        f2=f2,
        top_n=top_n,
        num_generos=num_generos,
        datos_nomina=datos_nomina,
        datos_sp=datos_sp,
        datos_nov=datos_nov,
        datos_ent=datos_ent,
        es_pdf=(formato == "pdf"),
    )

    if formato == "pdf":
        if "reportes:exportar" not in session["permisos"]:
            abort(403)
        pdf_bytes = rep.html_a_pdf(html)
        if not pdf_bytes:
            flash("Error al generar el PDF.", "error")
            return redirect(
                url_for(
                    "ver_reporte",
                    num=num,
                    limite=limite,
                    orden=orden_nombre,
                    f1=f1,
                    f2=f2,
                    top_n=top_n,
                    num_generos=num_generos,
                )
            )
        seg.auditar("EXPORTAR_PDF", "reportes", f"Reporte {num}: {titulo}")
        resp = Response(pdf_bytes, mimetype="application/pdf")
        resp.headers["Content-Disposition"] = f"inline; filename=reporte_{num}.pdf"
        return resp

    return html


# ----------------------------------------------------------------------
#  Módulo: Entretenimiento (Consulta de películas y libros)
# ----------------------------------------------------------------------
@app.route("/entretenimiento")
@seg.requiere_permiso("entretenimiento", "leer")
def entretenimiento():
    tab = request.args.get("tab", "peliculas")
    q = request.args.get("q", "").strip()
    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = 15

    if tab == "libros":
        filas, total = mod.listar_libros(q=q, pagina=pagina, por_pagina=por_pagina)
    else:
        tab = "peliculas"
        filas, total = mod.listar_peliculas(q=q, pagina=pagina, por_pagina=por_pagina)

    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return render_template(
        "entretenimiento.html",
        tab=tab,
        q=q,
        filas=filas,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
    )


# ----------------------------------------------------------------------
#  Módulo: Auditoría
# ----------------------------------------------------------------------
@app.route("/auditoria")
@seg.requiere_permiso("auditoria", "leer")
def auditoria_lista():
    registros = mod.listar_auditoria(limite=100)
    return render_template("auditoria.html", registros=registros)


# ----------------------------------------------------------------------
#  Módulo: Nómina (Periodos, Novedades y Liquidación)
# ----------------------------------------------------------------------
@app.route("/nomina")
@seg.requiere_permiso("nomina", "leer")
def nomina_panel():
    tab = request.args.get("tab", "periodos")
    id_periodo = request.args.get("id_periodo", type=int)

    periodos = mod.listar_periodos()
    if not id_periodo and periodos:
        id_periodo = periodos[0]["id_periodo"]

    parametros = mod.listar_parametros_anuales()
    tipos_novedad = mod.listar_tipos_novedad()
    empleados_sel = consultar("SELECT codigo, nombre_completo FROM empleado ORDER BY nombre_completo ASC")
    novedades = mod.listar_novedades(id_periodo=id_periodo) if id_periodo else []
    liquidaciones = mod.listar_liquidaciones(id_periodo=id_periodo) if id_periodo else []

    liq_detalle_id = request.args.get("detalle", type=int)
    movimientos = mod.obtener_movimientos_liquidacion(liq_detalle_id) if liq_detalle_id else []

    return render_template(
        "nomina.html",
        tab=tab,
        periodos=periodos,
        id_periodo=id_periodo,
        parametros=parametros,
        tipos_novedad=tipos_novedad,
        empleados_sel=empleados_sel,
        novedades=novedades,
        liquidaciones=liquidaciones,
        liq_detalle_id=liq_detalle_id,
        movimientos=movimientos,
    )


@app.route("/nomina/periodo/crear", methods=["POST"])
@seg.requiere_permiso("nomina", "crear")
def nomina_crear_periodo():
    try:
        id_parametro = request.form.get("id_parametro", type=int)
        mes = request.form.get("mes", type=int)
        fecha_inicio = request.form.get("fecha_inicio", "").strip()
        fecha_fin = request.form.get("fecha_fin", "").strip()
        mod.crear_periodo(id_parametro, mes, fecha_inicio, fecha_fin)
        seg.auditar("CREAR", "periodo_nomina", f"Periodo mes {mes} creado")
        flash("Periodo de nómina creado correctamente.", "ok")
    except Exception as e:
        flash(f"No se pudo crear el periodo (verifica que no esté repetido): {e}", "error")
    return redirect(url_for("nomina_panel", tab="periodos"))


@app.route("/nomina/novedad/crear", methods=["POST"])
@seg.requiere_permiso("nomina", "crear")
def nomina_crear_novedad():
    id_periodo = request.form.get("id_periodo", type=int)
    try:
        codigo = request.form.get("codigo", type=int)
        id_tipo = request.form.get("id_tipo_novedad", type=int)
        fecha_inicio = request.form.get("fecha_inicio", "").strip()
        fecha_fin = request.form.get("fecha_fin", "").strip()
        if fecha_fin < fecha_inicio:
            flash("La fecha fin no puede ser menor que la fecha inicio.", "error")
        else:
            mod.crear_novedad(codigo, id_periodo, id_tipo, fecha_inicio, fecha_fin)
            seg.auditar("CREAR", "novedad", f"Novedad empleado {codigo} en periodo {id_periodo}")
            flash("Novedad registrada.", "ok")
    except Exception as e:
        flash(f"Error al registrar novedad: {e}", "error")
    return redirect(url_for("nomina_panel", tab="novedades", id_periodo=id_periodo))


@app.route("/nomina/novedad/eliminar/<int:id_novedad>", methods=["POST"])
@seg.requiere_permiso("nomina", "eliminar")
def nomina_eliminar_novedad(id_novedad):
    id_periodo = request.form.get("id_periodo", type=int)
    mod.eliminar_novedad(id_novedad)
    seg.auditar("ELIMINAR", "novedad", f"Novedad ID {id_novedad}")
    flash("Novedad eliminada.", "ok")
    return redirect(url_for("nomina_panel", tab="novedades", id_periodo=id_periodo))


@app.route("/nomina/liquidar", methods=["POST"])
@seg.requiere_permiso("nomina", "crear")
def nomina_liquidar():
    id_periodo = request.form.get("id_periodo", type=int)
    if not id_periodo:
        flash("Selecciona un periodo válido.", "error")
        return redirect(url_for("nomina_panel", tab="liquidacion"))

    cantidad = mod.liquidar_periodo(id_periodo, session["usuario_id"])
    if cantidad == 0:
        flash("No hay empleados registrados en la base de datos para liquidar.", "error")
    else:
        seg.auditar("LIQUIDAR", "liquidacion", f"Periodo {id_periodo} liquidado ({cantidad} empleados)")
        flash(f"Nómina liquidada para {cantidad} empleado(s).", "ok")
    return redirect(url_for("nomina_panel", tab="liquidacion", id_periodo=id_periodo))


# ----------------------------------------------------------------------
#  Módulo: Empleados (Listado, búsqueda, filtros y CRUD)
# ----------------------------------------------------------------------
@app.route("/empleados")
@seg.requiere_permiso("empleados", "leer")
def empleados_lista():
    q = request.args.get("q", "").strip()
    id_dependencia = request.args.get("id_dependencia", type=int)
    orden = request.args.get("orden", "nombre")
    sentido = request.args.get("sentido", "ASC")
    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = 15

    filas, total = mod.listar_empleados(
        q=q,
        id_dependencia=id_dependencia,
        orden=orden,
        sentido=sentido,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    cats = mod.catalogos()
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    return render_template(
        "empleados.html",
        filas=filas,
        total=total,
        q=q,
        id_dependencia=id_dependencia,
        orden=orden,
        sentido=sentido,
        pagina=pagina,
        total_paginas=total_paginas,
        dependencias=cats["dependencias"],
    )


def _leer_form_empleado(codigo_fijo=None):
    codigo = codigo_fijo if codigo_fijo is not None else request.form.get("codigo", type=int)
    return dict(
        codigo=codigo,
        nombre=request.form.get("nombre", "").strip(),
        fecha_ingreso=request.form.get("fecha_ingreso", "").strip(),
        sueldo=request.form.get("sueldo", type=float),
        id_cargo=request.form.get("id_cargo", type=int),
        id_eps=request.form.get("id_eps", type=int),
        id_arl=request.form.get("id_arl", type=int),
        id_pension=request.form.get("id_pension", type=int),
    )


@app.route("/empleados/nuevo", methods=["GET", "POST"])
@seg.requiere_permiso("empleados", "crear")
def empleados_nuevo():
    cats = mod.catalogos()
    if request.method == "POST":
        datos = _leer_form_empleado()
        if not datos["codigo"] or datos["codigo"] <= 0:
            flash("El código del empleado debe ser un número positivo.", "error")
        elif mod.existe_empleado(datos["codigo"]):
            flash(f"Ya existe un empleado con el código {datos['codigo']}.", "error")
        elif not datos["nombre"] or not datos["fecha_ingreso"] or datos["sueldo"] is None or datos["sueldo"] < 0:
            flash("Completa todos los campos con valores válidos.", "error")
        else:
            mod.crear_empleado(datos)
            seg.auditar("CREAR", "empleado", f"Empleado {datos['codigo']} - {datos['nombre']}")
            flash("Empleado creado correctamente.", "ok")
            return redirect(url_for("empleados_lista"))
        return render_template("empleado_form.html", modo="nuevo", emp=datos, cats=cats)

    return render_template("empleado_form.html", modo="nuevo", emp={}, cats=cats)


@app.route("/empleados/<int:codigo>/editar", methods=["GET", "POST"])
@seg.requiere_permiso("empleados", "actualizar")
def empleados_editar(codigo):
    emp = mod.obtener_empleado(codigo)
    if not emp:
        abort(404)
    cats = mod.catalogos()

    if request.method == "POST":
        datos = _leer_form_empleado(codigo_fijo=codigo)
        if not datos["nombre"] or not datos["fecha_ingreso"] or datos["sueldo"] is None or datos["sueldo"] < 0:
            flash("Completa todos los campos con valores válidos.", "error")
            return render_template("empleado_form.html", modo="editar", emp=datos, cats=cats)
        mod.actualizar_empleado(codigo, datos)
        seg.auditar("EDITAR", "empleado", f"Empleado {codigo} - {datos['nombre']}")
        flash("Datos del empleado actualizados.", "ok")
        return redirect(url_for("empleados_lista"))

    emp_form = dict(
        codigo=emp["codigo"],
        nombre=emp["nombre_completo"],
        fecha_ingreso=str(emp["fecha_ingreso"]),
        sueldo=float(emp["sueldo"]),
        id_cargo=emp["id_cargo"],
        id_eps=emp["id_eps"],
        id_arl=emp["id_arl"],
        id_pension=emp["id_pension"],
    )
    return render_template("empleado_form.html", modo="editar", emp=emp_form, cats=cats)


@app.route("/empleados/<int:codigo>/eliminar", methods=["POST"])
@seg.requiere_permiso("empleados", "eliminar")
def empleados_eliminar(codigo):
    emp = mod.obtener_empleado(codigo)
    if not emp:
        abort(404)
    deps = mod.contar_dependientes(codigo)
    if deps["novedades"] > 0 or deps["liquidaciones"] > 0:
        flash(
            f"No se puede eliminar a {emp['nombre_completo']} porque tiene "
            f"{deps['novedades']} novedad(es) y {deps['liquidaciones']} liquidación(es) asociadas.",
            "error",
        )
        return redirect(url_for("empleados_lista"))

    mod.eliminar_empleado(codigo)
    seg.auditar("ELIMINAR", "empleado", f"Empleado {codigo} - {emp['nombre_completo']}")
    flash("Empleado eliminado.", "ok")
    return redirect(url_for("empleados_lista"))


# ----------------------------------------------------------------------
#  Módulo: Usuarios y Roles (Administración de cuentas y permisos)
# ----------------------------------------------------------------------
@app.route("/usuarios")
@seg.requiere_permiso("usuarios", "leer")
def usuarios_lista():
    usuarios = mod.listar_usuarios()
    roles = mod.catalogos()["roles"]
    permisos_rol = consultar(
        "SELECT r.nombre AS rol, r.descripcion, "
        "GROUP_CONCAT(CONCAT(p.modulo, ':', p.accion) ORDER BY p.modulo, p.accion SEPARATOR ', ') AS permisos "
        "FROM rol r "
        "LEFT JOIN rol_permiso rp ON rp.id_rol = r.id_rol "
        "LEFT JOIN permiso p ON p.id_permiso = rp.id_permiso "
        "GROUP BY r.id_rol, r.nombre, r.descripcion ORDER BY r.id_rol"
    )
    return render_template("usuarios.html", usuarios=usuarios, roles=roles, permisos_rol=permisos_rol)


@app.route("/usuarios/crear", methods=["POST"])
@seg.requiere_permiso("usuarios", "crear")
def usuarios_crear():
    username = request.form.get("username", "").strip().lower()
    nombre = request.form.get("nombre_completo", "").strip()
    email = request.form.get("email", "").strip().lower()
    clave = request.form.get("clave", "")
    id_rol = request.form.get("id_rol", type=int)

    if not username or not nombre or not email or not id_rol:
        flash("Todos los campos son obligatorios.", "error")
    elif len(clave) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "error")
    else:
        try:
            mod.crear_usuario(username, seg.hashear(clave), nombre, email, id_rol)
            seg.auditar("CREAR", "usuario", f"Usuario '{username}' creado")
            flash(f"Usuario '{username}' creado correctamente.", "ok")
        except Exception as e:
            flash(f"No se pudo crear el usuario (verifica que el usuario o correo no existan): {e}", "error")
    return redirect(url_for("usuarios_lista"))


@app.route("/usuarios/<int:id_usuario>/rol", methods=["POST"])
@seg.requiere_permiso("usuarios", "actualizar")
def usuarios_cambiar_rol(id_usuario):
    id_rol = request.form.get("id_rol", type=int)
    if id_usuario == session["usuario_id"]:
        flash("No puedes cambiar tu propio rol mientras tienes la sesión abierta.", "error")
    elif id_rol:
        mod.cambiar_rol_usuario(id_usuario, id_rol)
        seg.auditar("EDITAR", "usuario", f"Cambio de rol usuario ID {id_usuario} a rol ID {id_rol}")
        flash("Rol actualizado.", "ok")
    return redirect(url_for("usuarios_lista"))


@app.route("/usuarios/<int:id_usuario>/estado", methods=["POST"])
@seg.requiere_permiso("usuarios", "actualizar")
def usuarios_cambiar_estado(id_usuario):
    if id_usuario == session["usuario_id"]:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("usuarios_lista"))

    nuevo_estado = 1 if request.form.get("activo") == "1" else 0
    mod.cambiar_estado_usuario(id_usuario, nuevo_estado)
    accion_txt = "activado/desbloqueado" if nuevo_estado == 1 else "desactivado"
    seg.auditar("EDITAR", "usuario", f"Usuario ID {id_usuario} {accion_txt}")
    flash(f"Usuario {accion_txt}.", "ok")
    return redirect(url_for("usuarios_lista"))


@app.route("/usuarios/<int:id_usuario>/clave", methods=["POST"])
@seg.requiere_permiso("usuarios", "actualizar")
def usuarios_reset_clave(id_usuario):
    nueva_clave = request.form.get("nueva_clave", "")
    if len(nueva_clave) < 8:
        flash("La nueva contraseña debe tener al menos 8 caracteres.", "error")
    else:
        mod.actualizar_password_usuario(id_usuario, seg.hashear(nueva_clave))
        seg.auditar("EDITAR", "usuario", f"Contraseña restablecida para usuario ID {id_usuario}")
        flash("Contraseña actualizada y contador de intentos reiniciado.", "ok")
    return redirect(url_for("usuarios_lista"))


# ----------------------------------------------------------------------
#  Módulo: Cargas de Archivos (Excel de Nómina, .DAT de Películas, .JSON de Libros)
# ----------------------------------------------------------------------
import tempfile
from werkzeug.utils import secure_filename
import cargadores as carg


@app.route("/cargas", methods=["GET", "POST"])
@seg.requiere_permiso("cargas", "leer")
def cargas_panel():
    resultado = None

    if request.method == "POST":
        if "cargas:crear" not in session.get("permisos", []):
            abort(403)

        tipo = request.form.get("tipo", "").strip().upper()
        archivo = request.files.get("archivo")

        if not archivo or not archivo.filename:
            flash("Selecciona un archivo válido antes de subir.", "error")
            return redirect(url_for("cargas_panel"))

        nombre_seguro = secure_filename(archivo.filename)
        ext = os.path.splitext(nombre_seguro)[1].lower()

        extensiones_validas = {
            "NOMINA": (".xlsx",),
            "PELICULAS": (".dat", ".txt"),
            "LIBROS": (".json",),
        }
        if tipo not in extensiones_validas or ext not in extensiones_validas[tipo]:
            flash(f"Formato inválido para {tipo}. Se esperaba {', '.join(extensiones_validas.get(tipo, []))}.", "error")
            return redirect(url_for("cargas_panel"))

        # Guardamos temporalmente con su nombre original para que carga_archivo registre el nombre real
        carpeta_tmp = tempfile.mkdtemp()
        ruta_tmp = os.path.join(carpeta_tmp, nombre_seguro)
        try:
            archivo.save(ruta_tmp)
            uid = session["usuario_id"]

            if tipo == "NOMINA":
                res = carg.cargar_nomina(ruta_tmp, uid)
            elif tipo == "PELICULAS":
                res = carg.cargar_peliculas(ruta_tmp, uid)
            else:
                res = carg.cargar_libros(ruta_tmp, uid)

            errores = res.pop("errores", [])
            seg.auditar("CARGA_ARCHIVO", "carga_archivo", f"{tipo}: {nombre_seguro} ({len(errores)} advertencias)")
            flash(f"Archivo '{nombre_seguro}' procesado correctamente.", "ok")
            resultado = dict(tipo=tipo, archivo=nombre_seguro, resumen=res, errores=errores)
        except Exception as e:
            flash(f"Error al procesar el archivo: {e}", "error")
        finally:
            if os.path.exists(ruta_tmp):
                os.remove(ruta_tmp)
            if os.path.exists(carpeta_tmp):
                os.rmdir(carpeta_tmp)

    historial = consultar(
        "SELECT c.id_carga, c.fecha_hora, u.username AS usuario, c.tipo_archivo, "
        "c.nombre_archivo, c.registros_cargados, c.registros_rechazados, c.estado "
        "FROM carga_archivo c JOIN usuario u ON u.id_usuario = c.id_usuario "
        "ORDER BY c.id_carga DESC LIMIT 50"
    )
    return render_template("cargas.html", historial=historial, resultado=resultado)


if __name__ == "__main__":
    app.run(debug=True)      # debug=True solo para desarrollo