"""Conexion a MySQL. Todo el proyecto accede a la base de datos solo a traves de este archivo."""
import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()  # lee las credenciales del archivo .env (que no se sube a GitHub)


def get_conn():
    """Abre una conexion nueva usando los datos del .env."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "entrecol"),
        charset="utf8mb4",
    )


def consultar(sql, params=(), uno=False):
    """SELECT. Devuelve una lista de diccionarios (o un solo diccionario si uno=True).
    Los valores SIEMPRE van en params y se marcan con %s: asi se evita la inyeccion SQL."""
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        filas = cur.fetchall()
        return (filas[0] if filas else None) if uno else filas
    finally:
        conn.close()


def ejecutar(sql, params=()):
    """INSERT / UPDATE / DELETE. Devuelve el id autogenerado (si aplica)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def ejecutar_muchos(sql, lista_params):
    """Inserta muchas filas de una vez (lo usan los cargadores). Devuelve cuantas filas afecto."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executemany(sql, lista_params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


if __name__ == "__main__":
    # Prueba rapida:  python db.py
    roles = consultar("SELECT id_rol, nombre FROM rol")
    print(f"Conexion OK. Roles encontrados: {len(roles)}")
    for r in roles:
        print(" -", r["id_rol"], r["nombre"])