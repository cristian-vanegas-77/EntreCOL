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
    dict(modulo="empleados", titulo="Empleados", descr="Consultar y administrar empleados", endpoint=None),
    dict(modulo="nomina", titulo="Nómina", descr="Periodos, novedades y liquidación", endpoint=None),
    dict(modulo="entretenimiento", titulo="Entretenimiento", descr="Películas y libros", endpoint="entretenimiento"),
    dict(modulo="cargas", titulo="Cargas de archivos", descr="Excel, DAT y JSON", endpoint=None),
    dict(modulo="reportes", titulo="Reportes", descr="Vista previa y exportación a PDF", endpoint="reportes_panel"),
    dict(modulo="usuarios", titulo="Usuarios y roles", descr="Administrar el acceso", endpoint=None),
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

    if num == 1:
        titulo = "Empleados y masa salarial por dependencia"
        filas = mod.reporte_1_empleados_dependencia()
        columnas = ["Dependencia", "Empleados", "Total Sueldos ($)"]
        claves = ["etiqueta", "cantidad", "total_sueldo"]
        grafica = rep.generar_grafica_barras(
            [f["etiqueta"] for f in filas], [f["cantidad"] for f in filas], titulo, "Dependencia", "Empleados"
        )
    elif num == 2:
        titulo = f"Top {limite} géneros con más películas"
        filas = mod.reporte_2_peliculas_genero(limite)
        columnas = ["Género", "Cantidad de Películas"]
        claves = ["etiqueta", "cantidad"]
        grafica = rep.generar_grafica_barras(
            [f["etiqueta"] for f in filas], [f["cantidad"] for f in filas], titulo, "Género", "Películas"
        )
    elif num == 3:
        titulo = f"Top {limite} editoriales con más libros"
        filas = mod.reporte_3_libros_editorial(limite)
        columnas = ["Editorial", "Libros", "Rating Promedio"]
        claves = ["etiqueta", "cantidad", "rating_promedio"]
        grafica = rep.generar_grafica_barras(
            [f["etiqueta"] for f in filas], [f["cantidad"] for f in filas], titulo, "Editorial", "Libros"
        )
    elif num == 4:
        titulo = f"Top {limite} libros mejor calificados (mín. 1000 votos)"
        filas = mod.reporte_4_top_libros_rating(limite)
        columnas = ["Libro", "Rating", "Calificaciones"]
        claves = ["etiqueta", "valor", "num_calificaciones"]
        grafica = rep.generar_grafica_barras(
            [f["etiqueta"] for f in filas], [float(f["valor"]) for f in filas], titulo, "Libro", "Rating (0-5)"
        )
    elif num == 5:
        titulo = "Resumen de nómina liquidada por periodo"
        filas = mod.reporte_5_nomina_por_periodo()
        columnas = ["Periodo", "Devengado ($)", "Deducciones ($)", "Neto Pagado ($)"]
        claves = ["etiqueta", "devengado", "deducciones", "neto"]
        grafica = rep.generar_grafica_barras(
            [f["etiqueta"] for f in filas], [float(f["neto"]) for f in filas], titulo, "Periodo", "Neto ($)"
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
        limite=limite,
        es_pdf=(formato == "pdf"),
    )

    if formato == "pdf":
        if "reportes:exportar" not in session["permisos"]:
            abort(403)
        pdf_bytes = rep.html_a_pdf(html)
        if not pdf_bytes:
            flash("Error al generar el PDF.", "error")
            return redirect(url_for("ver_reporte", num=num, limite=limite))
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


if __name__ == "__main__":
    app.run(debug=True)      # debug=True solo para desarrollo