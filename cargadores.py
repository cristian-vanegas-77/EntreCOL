"""Cargadores: leen los archivos del cliente (Excel, DAT, JSON) y los insertan en MySQL.

Cada cargador tiene dos partes:
  1. leer_*()   -> solo lee y limpia el archivo (no toca la base de datos)
  2. cargar_*() -> inserta en MySQL dentro de UNA transaccion: o se carga todo o no se carga nada,
                   y deja un registro en carga_archivo.

Uso desde la terminal:
    python cargadores.py nomina    data/Nomina.xlsx
    python cargadores.py peliculas data/movies.dat
    python cargadores.py libros    data/Books.json
    python cargadores.py todo                       (usa los tres archivos de la carpeta data/)
"""
import calendar
import json
import re
import sys
import unicodedata
from datetime import date, datetime

import openpyxl

from db import consultar, ejecutar, get_conn

# Mes al que se asigna la liquidacion de los empleados SIN novedades
# (el Excel no dice a que mes pertenece). Confirmar con el grupo / profesor.
PERIODO_BASE = (2022, 3)


# ======================================================================
#  Utilidades
# ======================================================================
def _norm(texto):
    """Clave de comparacion: sin tildes, en minusculas y sin espacios sobrantes.
    MySQL (utf8mb4_unicode_ci) considera iguales 'Muller' y 'Müller', y asi evitamos
    buscar un nombre en el diccionario y no encontrarlo."""
    t = unicodedata.normalize("NFKD", str(texto).strip())
    return "".join(c for c in t if not unicodedata.combining(c)).casefold()


def _texto(valor):
    return "" if valor is None else str(valor).strip()


def _fecha_excel(valor):
    """Acepta datetime, date o numeros tipo 20210311. Devuelve date o None."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    if re.fullmatch(r"\d{8}", s):
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return None


def _entero(valor, defecto=0):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return defecto


def _chunks(lista, n=2000):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


def _abrir_carga(cur, id_usuario, tipo, ruta):
    nombre = ruta.replace("\\", "/").split("/")[-1]
    cur.execute("INSERT INTO carga_archivo (id_usuario, tipo_archivo, nombre_archivo) VALUES (%s,%s,%s)",
                (id_usuario, tipo, nombre))
    return cur.lastrowid


def _cerrar_carga(cur, id_carga, cargados, rechazados):
    estado = "CON_ERRORES" if rechazados else "PROCESADA"
    cur.execute("UPDATE carga_archivo SET registros_cargados=%s, registros_rechazados=%s, estado=%s "
                "WHERE id_carga=%s", (cargados, rechazados, estado, id_carga))


def _registrar_fallo(id_usuario, tipo, ruta):
    """Si la transaccion se deshizo, deja constancia de la carga fallida en carga_archivo."""
    nombre = ruta.replace("\\", "/").split("/")[-1]
    try:
        ejecutar("INSERT INTO carga_archivo (id_usuario, tipo_archivo, nombre_archivo, estado) "
                 "VALUES (%s,%s,%s,'FALLIDA')", (id_usuario, tipo, nombre))
    except Exception:
        pass


def _obtener_o_crear(cur, tabla, col_id, col_nombre, nombre, extra=None):
    """Busca una fila por nombre; si no existe la crea. Devuelve su id."""
    extra = extra or {}
    cond = f"{col_nombre}=%s" + "".join(f" AND {k}=%s" for k in extra)
    cur.execute(f"SELECT {col_id} FROM {tabla} WHERE {cond}", (nombre, *extra.values()))
    fila = cur.fetchone()
    if fila:
        return fila[0]
    cols = [col_nombre, *extra.keys()]
    cur.execute(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                (nombre, *extra.values()))
    return cur.lastrowid


# ======================================================================
#  1. NOMINA (Excel)
# ======================================================================
def leer_nomina(ruta):
    """Devuelve (empleados, novedades_por_codigo, errores).
    Detecta cada hoja por sus encabezados, no por su nombre."""
    wb = openpyxl.load_workbook(ruta, data_only=True)
    hoja_emp = hoja_nov = None
    for ws in wb.worksheets:
        enc = [_texto(c.value).upper() for c in ws[1]]
        if "NOMBRE DEL EMPLEADO" in enc:
            hoja_emp = ws
        elif "NOVEDAD INCAPACIDAD" in enc:
            hoja_nov = ws
    if hoja_emp is None or hoja_nov is None:
        raise ValueError("El Excel debe tener la hoja de empleados y la hoja de novedades.")

    errores, empleados, novedades = [], [], {}

    for n, f in enumerate(hoja_emp.iter_rows(min_row=2, values_only=True), start=2):
        if f[0] is None:
            continue
        ingreso = _fecha_excel(f[4])
        if ingreso is None or not _texto(f[1]):
            errores.append(f"Empleados fila {n}: datos incompletos o fecha de ingreso invalida")
            continue
        empleados.append(dict(codigo=_entero(f[0]), nombre=_texto(f[1]), dependencia=_texto(f[2]),
                              cargo=_texto(f[3]), ingreso=ingreso, eps=_texto(f[5]), arl=_texto(f[6]),
                              pension=_texto(f[7]), sueldo=f[8] or 0))

    for n, f in enumerate(hoja_nov.iter_rows(min_row=2, values_only=True), start=2):
        if f[0] is None:
            continue
        nov = dict(dias_trabajados=_entero(f[3], 30), bonificacion=f[10] or 0, transporte=f[11] or 0,
                   eventos=[])
        for tipo, marca, ini, fin in (("INCAPACIDAD", f[1], f[8], f[9]), ("VACACIONES", f[2], f[6], f[7])):
            if _texto(marca).upper() == "X":
                fi, ff = _fecha_excel(ini), _fecha_excel(fin)
                if fi and ff and ff >= fi:
                    nov["eventos"].append(dict(tipo=tipo, inicio=fi, fin=ff))
                else:
                    errores.append(f"Novedades fila {n}: {tipo} marcada pero con fechas invalidas")
        novedades[_entero(f[0])] = nov
    return empleados, novedades, errores


def _periodo(cur, anio, mes):
    """Devuelve el id del periodo (anio, mes); lo crea ABIERTO si no existe."""
    cur.execute("SELECT id_parametro FROM parametro_anual WHERE anio=%s", (anio,))
    p = cur.fetchone()
    if not p:
        raise ValueError(f"No existe parametro_anual para {anio}. Agregalo antes de cargar.")
    cur.execute("SELECT id_periodo FROM periodo_nomina WHERE id_parametro=%s AND mes=%s", (p[0], mes))
    fila = cur.fetchone()
    if fila:
        return fila[0]
    ultimo = calendar.monthrange(anio, mes)[1]
    cur.execute("INSERT INTO periodo_nomina (id_parametro, mes, fecha_inicio, fecha_fin, estado) "
                "VALUES (%s,%s,%s,%s,'ABIERTO')", (p[0], mes, date(anio, mes, 1), date(anio, mes, ultimo)))
    return cur.lastrowid


def cargar_nomina(ruta, id_usuario):
    empleados, novedades, errores = leer_nomina(ruta)
    conn = get_conn()
    cur = conn.cursor()
    try:
        id_carga = _abrir_carga(cur, id_usuario, "NOMINA", ruta)

        cur.execute("SELECT nombre, id_tipo_novedad FROM tipo_novedad")
        tipos = dict(cur.fetchall())
        cur.execute("SELECT nombre, id_concepto FROM concepto_nomina")
        conceptos = dict(cur.fetchall())

        # --- empleados y sus catalogos
        for e in empleados:
            id_dep = _obtener_o_crear(cur, "dependencia", "id_dependencia", "nombre", e["dependencia"])
            id_cargo = _obtener_o_crear(cur, "cargo", "id_cargo", "nombre", e["cargo"],
                                        {"id_dependencia": id_dep})
            id_eps = _obtener_o_crear(cur, "eps", "id_eps", "nombre", e["eps"])
            id_arl = _obtener_o_crear(cur, "arl", "id_arl", "nombre", e["arl"])
            id_pen = _obtener_o_crear(cur, "pension", "id_pension", "nombre", e["pension"])
            cur.execute("SELECT 1 FROM empleado WHERE codigo=%s", (e["codigo"],))
            if cur.fetchone():
                cur.execute("UPDATE empleado SET nombre_completo=%s, fecha_ingreso=%s, sueldo=%s, "
                            "id_cargo=%s, id_eps=%s, id_arl=%s, id_pension=%s WHERE codigo=%s",
                            (e["nombre"], e["ingreso"], e["sueldo"], id_cargo, id_eps, id_arl, id_pen,
                             e["codigo"]))
            else:
                cur.execute("INSERT INTO empleado (codigo, nombre_completo, fecha_ingreso, sueldo, id_cargo, "
                            "id_eps, id_arl, id_pension) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (e["codigo"], e["nombre"], e["ingreso"], e["sueldo"], id_cargo, id_eps, id_arl,
                             id_pen))

        # --- novedades y liquidacion en borrador (insumos del mes)
        codigos = {e["codigo"] for e in empleados}
        n_nov = 0
        for codigo, nov in novedades.items():
            if codigo not in codigos:
                errores.append(f"Novedades: el codigo {codigo} no existe en la hoja de empleados")
                continue
            id_periodo_liq = None
            for ev in nov["eventos"]:
                id_per = _periodo(cur, ev["inicio"].year, ev["inicio"].month)
                id_periodo_liq = id_periodo_liq or id_per
                cur.execute("SELECT 1 FROM novedad WHERE codigo=%s AND id_periodo=%s AND id_tipo_novedad=%s "
                            "AND fecha_inicio=%s", (codigo, id_per, tipos[ev["tipo"]], ev["inicio"]))
                if not cur.fetchone():
                    cur.execute("INSERT INTO novedad (codigo, id_periodo, id_tipo_novedad, fecha_inicio, "
                                "fecha_fin) VALUES (%s,%s,%s,%s,%s)",
                                (codigo, id_per, tipos[ev["tipo"]], ev["inicio"], ev["fin"]))
                    n_nov += 1
            if id_periodo_liq is None:
                id_periodo_liq = _periodo(cur, *PERIODO_BASE)

            cur.execute("INSERT IGNORE INTO liquidacion (codigo, id_periodo, id_usuario, dias_trabajados) "
                        "VALUES (%s,%s,%s,%s)", (codigo, id_periodo_liq, id_usuario, nov["dias_trabajados"]))
            if cur.rowcount == 1:   # liquidacion nueva: guardamos bonificacion y transporte como movimientos
                id_liq = cur.lastrowid
                for concepto, valor in (("BONIFICACION", nov["bonificacion"]),
                                        ("AUXILIO_TRANSPORTE", nov["transporte"])):
                    if valor:
                        cur.execute("INSERT INTO movimiento_nomina (id_liquidacion, id_concepto, dias, valor) "
                                    "VALUES (%s,%s,0,%s)", (id_liq, conceptos[concepto], valor))

        _cerrar_carga(cur, id_carga, len(empleados) + n_nov, len(errores))
        conn.commit()
    except Exception:
        conn.rollback()
        _registrar_fallo(id_usuario, "NOMINA", ruta)
        raise
    finally:
        conn.close()
    return dict(empleados=len(empleados), novedades=n_nov, errores=errores)


# ======================================================================
#  2. PELICULAS (.dat)  ->  id::titulo (anio)::Genero1|Genero2
# ======================================================================
def leer_peliculas(ruta):
    """Devuelve (peliculas, errores). Cada pelicula: id, titulo, anio, generos[]."""
    try:
        with open(ruta, encoding="utf-8") as f:
            lineas = f.read().splitlines()
    except UnicodeDecodeError:
        with open(ruta, encoding="latin-1") as f:
            lineas = f.read().splitlines()

    peliculas, errores, vistos = [], [], set()
    for n, linea in enumerate(lineas, start=1):
        if not linea.strip():
            continue
        partes = linea.split("::", 2)
        if len(partes) != 3 or not partes[0].strip().isdigit():
            errores.append(f"Linea {n}: formato invalido")
            continue
        id_peli = int(partes[0])
        if id_peli in vistos:
            errores.append(f"Linea {n}: id {id_peli} repetido")
            continue
        vistos.add(id_peli)
        titulo = partes[1].strip()
        m = re.search(r"\((\d{4})\)\s*$", titulo)
        anio = int(m.group(1)) if m else None
        if m:
            titulo = titulo[:m.start()].strip()
        generos = [g.strip() for g in partes[2].split("|") if g.strip() and g.strip() != "(no genres listed)"]
        peliculas.append(dict(id=id_peli, titulo=titulo, anio=anio, generos=generos))
    return peliculas, errores


def cargar_peliculas(ruta, id_usuario):
    peliculas, errores = leer_peliculas(ruta)
    conn = get_conn()
    cur = conn.cursor()
    try:
        id_carga = _abrir_carga(cur, id_usuario, "PELICULAS", ruta)

        nombres = {}
        for p in peliculas:
            for g in p["generos"]:
                nombres.setdefault(_norm(g), g)
        cur.executemany("INSERT IGNORE INTO genero (nombre) VALUES (%s)", [(g,) for g in nombres.values()])
        cur.execute("SELECT nombre, id_genero FROM genero")
        ids_genero = {_norm(n): i for n, i in cur.fetchall()}

        filas, relaciones = [], []
        for p in peliculas:
            filas.append((p["id"], p["titulo"], p["anio"], id_carga))
            for g in {_norm(x) for x in p["generos"]}:
                relaciones.append((p["id"], ids_genero[g]))

        for lote in _chunks(filas):
            cur.executemany("INSERT IGNORE INTO pelicula (id_pelicula, titulo, anio, id_carga) "
                            "VALUES (%s,%s,%s,%s)", lote)
        for lote in _chunks(relaciones):
            cur.executemany("INSERT IGNORE INTO pelicula_genero (id_pelicula, id_genero) VALUES (%s,%s)", lote)

        _cerrar_carga(cur, id_carga, len(peliculas), len(errores))
        conn.commit()
    except Exception:
        conn.rollback()
        _registrar_fallo(id_usuario, "PELICULAS", ruta)
        raise
    finally:
        conn.close()
    return dict(peliculas=len(peliculas), relaciones=len(relaciones), errores=errores)


# ======================================================================
#  3. LIBROS (JSON)
# ======================================================================
def _corregir_fila_libro(x):
    """Cuando el nombre de un autor trae una coma, el CSV original partio ese campo en dos y
    corrio todas las columnas una posicion (el sobrante cae en FIELD13).
    Aqui se vuelve a unir el autor y se reacomodan las columnas."""
    if _texto(x.get("FIELD13")) == "":
        return dict(id=x["bookID"], titulo=x["title"], autores=x["authors"], rating=x["average_rating"],
                    isbn=x["isbn"], isbn13=x["isbn13"], idioma=x["language_code"], paginas=x["num_pages"],
                    calificaciones=x["ratings_count"], resenas=x["text_reviews_count"],
                    fecha=x["publication_date"], editorial=x["publisher"])
    return dict(id=x["bookID"], titulo=x["title"], autores=f'{x["authors"]},{x["average_rating"]}',
                rating=x["isbn"], isbn=x["isbn13"], isbn13=x["language_code"], idioma=x["num_pages"],
                paginas=x["ratings_count"], calificaciones=x["text_reviews_count"],
                resenas=x["publication_date"], fecha=x["publisher"], editorial=x["FIELD13"])


def leer_libros(ruta):
    """Devuelve (libros, errores). Cada libro: id, titulo, autores[], editorial, rating, ..., fecha|None."""
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)

    libros, errores, vistos = [], [], set()
    for x in datos:
        try:
            r = _corregir_fila_libro(x)
            id_libro = int(r["id"])
            if id_libro in vistos:
                errores.append(f"Libro {id_libro}: id repetido")
                continue
            editorial = _texto(r["editorial"])
            titulo = _texto(r["titulo"])
            if not titulo or not editorial:
                errores.append(f"Libro {id_libro}: sin titulo o sin editorial")
                continue
            rating = float(r["rating"])
            if not 0 <= rating <= 5:
                raise ValueError("rating fuera de rango")
            try:
                fecha = datetime.strptime(_texto(r["fecha"]), "%m/%d/%Y").date()
            except ValueError:
                fecha = None   # fecha invalida -> se guarda NULL, el libro se conserva
            autores = []
            for a in str(r["autores"]).split("/"):
                if a.strip() and _norm(a) not in {_norm(y) for y in autores}:
                    autores.append(a.strip())
            vistos.add(id_libro)
            libros.append(dict(id=id_libro, titulo=titulo, autores=autores, editorial=editorial, rating=rating,
                               isbn=_texto(r["isbn"]) or None, isbn13=_texto(r["isbn13"]) or None,
                               idioma=_texto(r["idioma"]) or None, paginas=_entero(r["paginas"]),
                               calificaciones=_entero(r["calificaciones"]), resenas=_entero(r["resenas"]),
                               fecha=fecha))
        except (ValueError, TypeError, KeyError) as exc:
            errores.append(f"Libro {x.get('bookID')}: {exc}")
    return libros, errores


def cargar_libros(ruta, id_usuario):
    libros, errores = leer_libros(ruta)
    conn = get_conn()
    cur = conn.cursor()
    try:
        id_carga = _abrir_carga(cur, id_usuario, "LIBROS", ruta)

        editoriales, autores = {}, {}
        for l in libros:
            editoriales.setdefault(_norm(l["editorial"]), l["editorial"])
            for a in l["autores"]:
                autores.setdefault(_norm(a), a)
        for lote in _chunks([(n,) for n in editoriales.values()]):
            cur.executemany("INSERT IGNORE INTO editorial (nombre) VALUES (%s)", lote)
        for lote in _chunks([(n,) for n in autores.values()]):
            cur.executemany("INSERT IGNORE INTO autor (nombre) VALUES (%s)", lote)
        cur.execute("SELECT nombre, id_editorial FROM editorial")
        ids_edit = {_norm(n): i for n, i in cur.fetchall()}
        cur.execute("SELECT nombre, id_autor FROM autor")
        ids_aut = {_norm(n): i for n, i in cur.fetchall()}

        filas, relaciones = [], []
        for l in libros:
            filas.append((l["id"], ids_edit[_norm(l["editorial"])], id_carga, l["titulo"], l["rating"],
                          l["isbn"], l["isbn13"], l["idioma"], l["paginas"], l["calificaciones"],
                          l["resenas"], l["fecha"]))
            for a in l["autores"]:
                relaciones.append((l["id"], ids_aut[_norm(a)]))

        for lote in _chunks(filas):
            cur.executemany("INSERT IGNORE INTO libro (id_libro, id_editorial, id_carga, titulo, rating_promedio, "
                            "isbn, isbn13, idioma, num_paginas, num_calificaciones, num_resenas, "
                            "fecha_publicacion) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", lote)
        for lote in _chunks(relaciones):
            cur.executemany("INSERT IGNORE INTO libro_autor (id_libro, id_autor) VALUES (%s,%s)", lote)

        _cerrar_carga(cur, id_carga, len(libros), len(errores))
        conn.commit()
    except Exception:
        conn.rollback()
        _registrar_fallo(id_usuario, "LIBROS", ruta)
        raise
    finally:
        conn.close()
    sin_fecha = sum(1 for l in libros if l["fecha"] is None)
    return dict(libros=len(libros), autores=len(autores), editoriales=len(editoriales),
                sin_fecha=sin_fecha, errores=errores)


# ======================================================================
#  Linea de comandos
# ======================================================================
def _main(argv):
    if not argv or argv[0] not in ("nomina", "peliculas", "libros", "todo"):
        print(__doc__)
        return
    admin = consultar("SELECT id_usuario FROM usuario WHERE username=%s", ("admin",), uno=True)
    if not admin:
        print("Primero crea el usuario admin:  python seguridad.py")
        return
    uid = admin["id_usuario"]
    por_defecto = {"nomina": "data/Nomina.xlsx", "peliculas": "data/movies.dat", "libros": "data/Books.json"}
    funciones = {"nomina": cargar_nomina, "peliculas": cargar_peliculas, "libros": cargar_libros}
    tareas = list(por_defecto) if argv[0] == "todo" else [argv[0]]
    for t in tareas:
        ruta = argv[1] if len(argv) > 1 and argv[0] != "todo" else por_defecto[t]
        resumen = funciones[t](ruta, uid)
        errores = resumen.pop("errores")
        print(f"[{t}] {resumen}  |  {len(errores)} advertencias")
        for e in errores[:10]:
            print("   -", e)


if __name__ == "__main__":
    _main(sys.argv[1:]) 