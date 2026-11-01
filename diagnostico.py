# -*- coding: utf-8 -*-
"""Diagnostico de acceso de TodoUtesa.

Responde una sola pregunta: por que no me entra el sitio desde otro dispositivo.

    python diagnostico.py          (o:  python3 diagnostico.py)

No cambia nada: solo lee la configuracion, mira las direcciones de red y prueba
conectarse al puerto. Sirve igual en Termux, Windows, Linux y macOS.
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys

RUTA_BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DATOS = os.path.join(RUTA_BASE, "datos")
RUTA_DB = os.path.join(RUTA_DATOS, "todoutesa.db")
RUTA_DB_VIEJA = os.path.join(RUTA_DATOS, "habitos.db")

lineas = []


def decir(texto=""):
    print(texto)
    lineas.append(texto)


def leer_ajustes(ruta):
    ajustes = {}
    try:
        con = sqlite3.connect(ruta)
        con.row_factory = sqlite3.Row
        for fila in con.execute("SELECT clave, valor FROM ajustes").fetchall():
            ajustes[fila["clave"]] = fila["valor"]
        con.close()
    except Exception as error:
        decir("  (no pude leer los ajustes: %s)" % error)
    return ajustes


def es_termux():
    return "com.termux" in os.environ.get("PREFIX", "")


def direcciones_locales():
    encontradas = []
    try:
        prueba = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        prueba.connect(("8.8.8.8", 80))
        encontradas.append(prueba.getsockname()[0])
        prueba.close()
    except Exception:
        pass

    for comando in (["ip", "-4", "-o", "addr"], ["ifconfig"]):
        try:
            salida = subprocess.run(comando, capture_output=True, text=True, timeout=5).stdout
        except Exception:
            continue
        for palabra in salida.replace("/", " ").replace(":", " ").split():
            partes = palabra.split(".")
            if len(partes) == 4 and all(p.isdigit() for p in partes):
                if palabra not in encontradas and not palabra.startswith("127."):
                    if not palabra.startswith("255."):
                        encontradas.append(palabra)

    limpias = []
    for direccion in encontradas:
        if direccion not in limpias:
            limpias.append(direccion)
    return limpias


def puertos_escuchando():
    """Lee el socket real (Linux/Termux). Devuelve [(ip, puerto)] en LISTEN."""
    encontrados = []
    try:
        with open("/proc/net/tcp", "r") as archivo:
            lineas = archivo.readlines()[1:]
    except (OSError, IndexError):
        return encontrados

    for linea in lineas:
        partes = linea.split()
        if len(partes) < 4 or partes[3] != "0A":
            continue
        try:
            direccion, puerto_hex = partes[1].split(":")
            octetos = [str(int(direccion[i:i + 2], 16)) for i in (6, 4, 2, 0)]
            encontrados.append((".".join(octetos), int(puerto_hex, 16)))
        except (ValueError, IndexError):
            continue
    return encontrados


def probar_puerto(host, puerto, segundos=2):
    prueba = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    prueba.settimeout(segundos)
    try:
        prueba.connect((host, puerto))
        prueba.close()
        return True
    except Exception:
        return False


def pedir(host, puerto, ruta="/api/resumen"):
    """GET a mano para no depender de nada."""
    try:
        conexion = socket.create_connection((host, puerto), timeout=4)
        conexion.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n"
                          % (ruta, host)).encode())
        respuesta = conexion.recv(200).decode("utf-8", "ignore")
        conexion.close()
        primera = respuesta.split("\r\n")[0]
        return primera.strip()
    except Exception as error:
        return "sin respuesta (%s)" % error


def main():
    decir("=" * 60)
    decir(" TodoUtesa - diagnostico de acceso")
    decir("=" * 60)

    decir("")
    decir("1) Entorno")
    decir("   Python: " + sys.version.split()[0])
    decir("   Sistema: " + sys.platform)
    if es_termux():
        decir("   Termux: si (estas en un telefono)")
    else:
        decir("   Termux: no")

    # ---------------------------------------------------------- configuracion
    ruta = RUTA_DB if os.path.isfile(RUTA_DB) else RUTA_DB_VIEJA
    decir("")
    decir("2) Configuracion guardada")
    if not os.path.isfile(ruta):
        decir("   No hay base de datos todavia: arranca la app una vez primero.")
        return 1
    decir("   Base: " + os.path.basename(ruta))

    ajustes = leer_ajustes(ruta)
    host = ajustes.get("host", "127.0.0.1") or "127.0.0.1"
    try:
        puerto = int(ajustes.get("puerto", "8630") or 8630)
    except ValueError:
        puerto = 8630
    tiene_clave = bool(ajustes.get("clave_hash"))

    decir("   Escucha en: " + host +
         ("  <- SOLO este dispositivo" if host == "127.0.0.1" else "  <- toda la red"))
    decir("   Puerto: " + str(puerto))
    decir("   Clave de acceso: " + ("si" if tiene_clave else "NO (cualquiera entra)"))

    # ------------------------------------------------------------- direcciones
    direcciones = direcciones_locales()
    decir("")
    decir("3) Direcciones de este dispositivo")
    if direcciones:
        for direccion in direcciones:
            decir("   " + direccion)
    else:
        decir("   No encontre ninguna IP de red.")

    # ----------------------------------------------------------------- puerto
    decir("")
    decir("4) Estado del servidor")
    escucha_local = probar_puerto("127.0.0.1", puerto)
    decir("   Puerto " + str(puerto) + " en 127.0.0.1: " +
         ("abierto" if escucha_local else "cerrado (la app no esta corriendo)"))
    if escucha_local:
        decir("   Respuesta HTTP: " + pedir("127.0.0.1", puerto))

    abierta_en_red = []
    for direccion in direcciones:
        if probar_puerto(direccion, puerto):
            abierta_en_red.append(direccion)
    if direcciones:
        if abierta_en_red:
            decir("   Alcanzable por la red en: " + ", ".join(abierta_en_red))
        else:
            decir("   NO es alcanzable por la red (esto explica el error del otro dispositivo)")

    # que dice el sistema operativo sobre el socket (Linux / Termux)
    sockets = [s for s in puertos_escuchando() if s[1] == puerto]
    if sockets:
        direcciones_socket = []
        for ip, _ in sockets:
            if ip not in direcciones_socket:
                direcciones_socket.append(ip)
        decir("   El sistema dice que escucha en: " + ", ".join(direcciones_socket))
        for ip in direcciones_socket:
            if ip == "0.0.0.0":
                decir("   -> esta aceptando conexiones de toda la red")
            elif ip.startswith("127."):
                decir("   -> esta aceptando SOLO desde este mismo dispositivo")

    # ------------------------------------------------------------------ veredicto
    decir("")
    decir("=" * 60)
    decir(" VEREDICTO")
    decir("=" * 60)

    if not escucha_local:
        decir("")
        decir(" El servidor no esta corriendo en este momento.")
        decir(" Arrancalo:   python servidor.py")
        return 1

    if abierta_en_red:
        decir("")
        decir(" Todo bien: el servidor ya acepta conexiones de la red.")
        if not tiene_clave:
            decir("")
            decir(" PERO no tiene clave de acceso: pon una en la app (menu Servidor).")
        decir("")
        decir(" Desde otro dispositivo en la misma wifi, abre:")
        for direccion in abierta_en_red:
            decir("   http://" + direccion + ":" + str(puerto))
        if direcciones:
            decir("")
            decir(" Si desde el otro equipo sigue sin entrar:")
            decir("   - ese equipo esta en la misma wifi? (no datos moviles)")
            decir("   - wifi de invitados / aislamiento de clientes del router")
            decir("   - firewall del sistema bloqueando el puerto " + str(puerto))
        decir("")
        decir(" Para acceder DESDE FUERA de tu red hace falta un tunel:")
        decir("   ver ACCESO-REMOTO.md")
        return 0

    if host == "127.0.0.1":
        decir("")
        decir(" ESTA ES LA CAUSA: la app esta configurada para escuchar solo a si misma.")
        decir(" Un servidor en 127.0.0.1 no acepta conexiones de otros equipos.")
        decir("")
        decir(" Arreglo (dos formas, elegi una):")
        decir("")
        decir("   A) Abrir SOLO la red local (misma wifi):")
        decir("      python servidor.py --red")
        decir("      y abre en tu PC:  http://IP_DEL_TELEFONO:" + str(puerto))
        if not tiene_clave:
            decir("")
            decir("      OJO: pon una clave en la app (menu Servidor) antes de dejarlo")
            decir("      abierto: ahora mismo cualquiera en tu wifi puede entrar.")
        decir("")
        decir("   B) Acceso desde cualquier lugar del mundo: mira ACCESO-REMOTO.md")
        decir("      (Tailscale o Cloudflare Tunnel).")
        return 2

    decir("")
    decir(" La configuracion dice 0.0.0.0, pero el servidor que esta corriendo")
    decir(" no acepta conexiones de la red. Pasa cuando:")
    decir("")
    decir("   - lo arrancaste con --local (o desde otra terminal vieja)")
    decir("   - el firewall del sistema bloquea el puerto " + str(puerto))
    decir("   - el router aisla los clientes (wifi de invitados)")
    decir("")
    decir(" Prueba: cierra la app y arrancala asi:")
    decir("   python servidor.py --red")
    return 3


if __name__ == "__main__":
    sys.exit(main())
