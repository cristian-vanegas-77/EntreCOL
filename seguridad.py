"""Seguridad: contraseñas con bcrypt, bloqueo por intentos, captcha, permisos por rol y auditoría.

Para crear el primer administrador:   python seguridad.py
"""
import secrets
from functools import wraps
from getpass import getpass

import bcrypt
from flask import abort, redirect, request, session, url_for

from db import consultar, ejecutar

MAX_INTENTOS = 5                                   # al 5.º intento fallido la cuenta queda bloqueada
ALFABETO_CAPTCHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin O, I, 0, 1 para no confundir


# ----------------------------------------------------------------------
#  Contraseñas
# ----------------------------------------------------------------------
def hashear(clave):
    """bcrypt agrega una 'sal' aleatoria: dos usuarios con la misma clave tienen hashes distintos."""
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar(clave, hash_guardado):
    """No se 'descifra' el hash: se compara la clave escrita contra el hash guardado."""
    try:
        return bcrypt.checkpw(clave.encode("utf-8"), hash_guardado.encode("utf-8"))
    except ValueError:
        return False


def crear_usuario(username, clave, nombre, email, nombre_rol):
    rol = consultar("SELECT id_rol FROM rol WHERE nombre=%s", (nombre_rol,), uno=True)
    if not rol:
        raise ValueError(f"El rol {nombre_rol} no existe")
    return ejecutar(
        "INSERT INTO usuario (id_rol, username, password_hash, nombre_completo, email) "
        "VALUES (%s,%s,%s,%s,%s)",
        (rol["id_rol"], username, hashear(clave), nombre, email),
    )


# ----------------------------------------------------------------------
#  Auditoría
# ----------------------------------------------------------------------
def auditar(accion, tabla=None, detalle=None, id_usuario=None):
    """Guarda quién hizo qué, desde qué IP y cuándo. Se llama en cada acción importante."""
    if id_usuario is None:
        id_usuario = session.get("usuario_id")
    ip = request.remote_addr if request else None
    ejecutar(
        "INSERT INTO auditoria (id_usuario, accion, tabla_afectada, detalle, ip) VALUES (%s,%s,%s,%s,%s)",
        (id_usuario, accion, tabla, (detalle or "")[:500] or None, ip),
    )


# ----------------------------------------------------------------------
#  Primer factor: usuario + contraseña
# ----------------------------------------------------------------------
def autenticar(username, clave):
    """Devuelve (usuario, None) si todo es correcto, o (None, mensaje_de_error)."""
    u = consultar(
        "SELECT id_usuario, password_hash, activo, intentos_fallidos FROM usuario WHERE username=%s",
        (username,), uno=True)
    if not u:
        auditar("LOGIN_FALLIDO", "usuario", f"usuario inexistente: {username[:40]}")
        return None, "Usuario o clave incorrectos."
    if not u["activo"] or u["intentos_fallidos"] >= MAX_INTENTOS:
        auditar("LOGIN_BLOQUEADO", "usuario", "cuenta bloqueada o inactiva", u["id_usuario"])
        return None, "Cuenta bloqueada o inactiva. Contacta al administrador."
    if not verificar(clave, u["password_hash"]):
        ejecutar("UPDATE usuario SET intentos_fallidos = intentos_fallidos + 1 WHERE id_usuario=%s",
                 (u["id_usuario"],))
        auditar("LOGIN_FALLIDO", "usuario", "clave incorrecta", u["id_usuario"])
        return None, "Usuario o clave incorrectos."
    ejecutar("UPDATE usuario SET intentos_fallidos = 0 WHERE id_usuario=%s", (u["id_usuario"],))
    return u, None


# ----------------------------------------------------------------------
#  Segundo factor: captcha
# ----------------------------------------------------------------------
def generar_captcha():
    """Devuelve (texto, bytes_png). El texto se guarda en la sesión y la imagen se muestra al usuario."""
    from captcha.image import ImageCaptcha
    texto = "".join(secrets.choice(ALFABETO_CAPTCHA) for _ in range(5))
    return texto, ImageCaptcha(width=220, height=80).generate(texto).getvalue()


# ----------------------------------------------------------------------
#  Roles y permisos
# ----------------------------------------------------------------------
def permisos_de_rol(id_rol):
    """Lista de textos 'modulo:accion', por ejemplo 'nomina:crear'."""
    filas = consultar(
        "SELECT p.modulo, p.accion FROM rol_permiso rp JOIN permiso p ON p.id_permiso = rp.id_permiso "
        "WHERE rp.id_rol=%s", (id_rol,))
    return [f"{f['modulo']}:{f['accion']}" for f in filas]


def login_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return envoltura


def requiere_permiso(modulo, accion="leer"):
    """Uso:  @requiere_permiso('nomina', 'crear')  encima de una ruta de Flask."""
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if "usuario_id" not in session:
                return redirect(url_for("login"))
            if f"{modulo}:{accion}" not in session.get("permisos", []):
                auditar("ACCESO_DENEGADO", modulo, f"{accion} en {request.path}")
                abort(403)
            return f(*args, **kwargs)
        return envoltura
    return decorador


if __name__ == "__main__":
    if consultar("SELECT 1 FROM usuario WHERE username=%s", ("admin",), uno=True):
        print("El usuario admin ya existe.")
    else:
        clave = getpass("Clave para el usuario admin (no se ve al escribir): ")
        if len(clave) < 8:
            print("Usa al menos 8 caracteres.")
        else:
            crear_usuario("admin", clave, "Administrador", "admin@entrecol.com", "ADMINISTRADOR")
            print("Usuario admin creado.")