"""Seguridad: contrasenas con bcrypt, creacion de usuarios.
(Mas adelante este archivo tambien tendra el captcha, el control de permisos por rol y la auditoria.)

Para crear el primer administrador:   python seguridad.py
"""
from getpass import getpass

import bcrypt

from db import consultar, ejecutar


def hashear(clave):
    """bcrypt agrega una 'sal' aleatoria: dos usuarios con la misma clave tienen hashes distintos."""
    return bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar(clave, hash_guardado):
    """No se 'descifra' el hash: se compara la clave escrita contra el hash guardado."""
    return bcrypt.checkpw(clave.encode("utf-8"), hash_guardado.encode("utf-8"))


def crear_usuario(username, clave, nombre, email, nombre_rol):
    rol = consultar("SELECT id_rol FROM rol WHERE nombre=%s", (nombre_rol,), uno=True)
    if not rol:
        raise ValueError(f"El rol {nombre_rol} no existe")
    return ejecutar(
        "INSERT INTO usuario (id_rol, username, password_hash, nombre_completo, email) "
        "VALUES (%s,%s,%s,%s,%s)",
        (rol["id_rol"], username, hashear(clave), nombre, email),
    )


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