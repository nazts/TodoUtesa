# -*- coding: utf-8 -*-
"""Sincronizacion con Google Calendar y Google Tasks (solo stdlib).

Autenticacion OAuth2 con cliente de tipo "Desktop app":
  1. datos/google_cliente.json  -> el client_secret que baja de Google Cloud
  2. la app genera la URL de consentimiento (PKCE), tu apruebas
  3. Google redirige a /oauth2callback en este mismo servidor
  4. se guarda datos/google_token.json con el refresh_token

Direccion de la sincronizacion: Habitos -> Google (una sola via).
Cada tarea guarda su id de Google, asi no se duplica ni se crea dos veces.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

RUTA_BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DATOS = os.path.join(RUTA_BASE, "datos")
RUTA_CLIENTE = os.path.join(RUTA_DATOS, "google_cliente.json")
RUTA_TOKEN = os.path.join(RUTA_DATOS, "google_token.json")

URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
URL_TASKS = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"
URL_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/userinfo.email",
]

ZONA = "America/Santo_Domingo"


class ErrorGoogle(Exception):
    pass


# ------------------------------------------------------------------ archivos

def _leer_json(ruta):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, ValueError):
        return None


def _guardar_json(ruta, datos):
    if not os.path.isdir(RUTA_DATOS):
        os.makedirs(RUTA_DATOS)
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


def cargar_cliente():
    datos = _leer_json(RUTA_CLIENTE)
    if not datos:
        return None
    bloque = datos.get("installed") or datos.get("web") or datos
    if not bloque.get("client_id") or not bloque.get("client_secret"):
        return None
    return {"client_id": bloque["client_id"], "client_secret": bloque["client_secret"]}


def instalar_cliente(desde_ruta):
    """Copia el client_secret.json que bajaste de Google Cloud."""
    if not desde_ruta or not os.path.isfile(desde_ruta):
        raise ErrorGoogle("No encuentro ese archivo. Revisa la ruta.")
    datos = _leer_json(desde_ruta)
    if not datos:
        raise ErrorGoogle("Ese archivo no es un JSON valido.")
    bloque = datos.get("installed") or datos.get("web")
    if not bloque or not bloque.get("client_id") or not bloque.get("client_secret"):
        raise ErrorGoogle("Ese JSON no es un client_secret de OAuth 2.0.")
    _guardar_json(RUTA_CLIENTE, datos)
    return {"ok": True, "client_id": bloque["client_id"]}


def cargar_token():
    return _leer_json(RUTA_TOKEN)


def guardar_token(datos):
    _guardar_json(RUTA_TOKEN, datos)


def borrar_token():
    try:
        os.remove(RUTA_TOKEN)
    except OSError:
        pass


# ---------------------------------------------------------------- OAuth (PKCE)

def _base64url(datos):
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def iniciar_autorizacion(redirect_uri):
    cliente = cargar_cliente()
    if not cliente:
        raise ErrorGoogle("Primero carga el client_secret.json de Google Cloud.")

    verificador = _base64url(secrets.token_bytes(48))
    desafio = _base64url(hashlib.sha256(verificador.encode("ascii")).digest())
    estado = secrets.token_urlsafe(24)

    parametros = {
        "client_id": cliente["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": estado,
        "code_challenge": desafio,
        "code_challenge_method": "S256",
    }
    url = URL_AUTORIZACION + "?" + urllib.parse.urlencode(parametros)

    pendiente = {"verificador": verificador, "estado": estado,
                 "redirect": redirect_uri, "momento": time.time()}
    _guardar_json(RUTA_DATOS + os.sep + "google_pendiente.json", pendiente)
    return {"url": url, "estado": estado}


def cargar_pendiente():
    return _leer_json(RUTA_DATOS + os.sep + "google_pendiente.json")


def completar_autorizacion(codigo, estado):
    cliente = cargar_cliente()
    pendiente = cargar_pendiente()
    if not cliente or not pendiente:
        raise ErrorGoogle("No hay una autorizacion en curso. Empieza de nuevo.")
    if estado and estado != pendiente.get("estado"):
        raise ErrorGoogle("El codigo no corresponde a esta sesion. Empieza de nuevo.")

    datos = urllib.parse.urlencode({
        "code": codigo,
        "client_id": cliente["client_id"],
        "client_secret": cliente["client_secret"],
        "redirect_uri": pendiente["redirect"],
        "grant_type": "authorization_code",
        "code_verifier": pendiente["verificador"],
    }).encode("utf-8")

    respuesta = _post_formulario(URL_TOKEN, datos)
    if "refresh_token" not in respuesta and "access_token" not in respuesta:
        raise ErrorGoogle(respuesta.get("error_description") or "Google no devolvio el token.")

    token = {
        "access_token": respuesta.get("access_token"),
        "refresh_token": respuesta.get("refresh_token"),
        "expira": time.time() + int(respuesta.get("expires_in", 3600)) - 60,
        "scopes": respuesta.get("scope", ""),
        "momento": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    anterior = cargar_token()
    if not token["refresh_token"] and anterior:
        token["refresh_token"] = anterior.get("refresh_token")

    correo = ""
    try:
        info = _pedir("GET", URL_USERINFO, token["access_token"])
        correo = info.get("email", "")
    except ErrorGoogle:
        pass
    token["email"] = correo
    guardar_token(token)

    try:
        os.remove(RUTA_DATOS + os.sep + "google_pendiente.json")
    except OSError:
        pass
    return token


def _post_formulario(url, datos):
    peticion = urllib.request.Request(url, datos,
                                      {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        respuesta = urllib.request.urlopen(peticion, timeout=45)
        return json.loads(respuesta.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        cuerpo = error.read().decode("utf-8", "replace")
        try:
            return json.loads(cuerpo)
        except ValueError:
            raise ErrorGoogle("Google respondio %s" % error.code)
    except Exception as error:
        raise ErrorGoogle("No se pudo hablar con Google: %s" % error)


def access_token():
    token = cargar_token()
    if not token:
        raise ErrorGoogle("Google no esta conectado.")
    if token.get("access_token") and token.get("expira", 0) > time.time():
        return token["access_token"]

    cliente = cargar_cliente()
    if not cliente or not token.get("refresh_token"):
        raise ErrorGoogle("La sesion de Google expiro. Vuelve a autorizar.")

    datos = urllib.parse.urlencode({
        "client_id": cliente["client_id"],
        "client_secret": cliente["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    }).encode("utf-8")

    respuesta = _post_formulario(URL_TOKEN, datos)
    if not respuesta.get("access_token"):
        raise ErrorGoogle("No pude renovar el acceso a Google. Vuelve a autorizar.")
    token["access_token"] = respuesta["access_token"]
    token["expira"] = time.time() + int(respuesta.get("expires_in", 3600)) - 60
    guardar_token(token)
    return token["access_token"]


def _pedir(metodo, url, cuerpo=None, con_token=True):
    cuerpo_bytes = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json"}
    if con_token is True:
        cabeceras["Authorization"] = "Bearer " + access_token()
    elif con_token:
        cabeceras["Authorization"] = "Bearer " + con_token

    peticion = urllib.request.Request(url, cuerpo_bytes, cabeceras, method=metodo)
    try:
        respuesta = urllib.request.urlopen(peticion, timeout=45)
        texto = respuesta.read().decode("utf-8", "replace")
        return json.loads(texto) if texto.strip() else {}
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {"_no_encontrado": True}
        cuerpo_error = error.read().decode("utf-8", "replace")
        try:
            detalle = json.loads(cuerpo_error).get("error", {})
            mensaje = detalle.get("message") or detalle.get("status") or str(error.code)
        except ValueError:
            mensaje = str(error.code)
        raise ErrorGoogle("Google rechazo la peticion: %s" % mensaje)
    except Exception as error:
        raise ErrorGoogle("Fallo la llamada a Google: %s" % error)


# ------------------------------------------------------------------ estado

def estado():
    token = cargar_token()
    cliente = cargar_cliente()
    info = {
        "cliente": bool(cliente),
        "conectado": bool(token and token.get("refresh_token")),
        "email": (token or {}).get("email", ""),
        "momento": (token or {}).get("momento", ""),
        "calendario": True,
        "tareas": True,
    }
    return info


# ------------------------------------------------------------- calendario

def _evento_de(tarea):
    titulo = tarea["titulo"]
    if tarea["estado"] == "hecha":
        titulo = "Hecho: " + titulo

    descripcion = []
    if tarea.get("area"):
        descripcion.append("Area: " + tarea["area"])
    if tarea.get("notas"):
        descripcion.append(tarea["notas"])
    if tarea.get("url"):
        descripcion.append(tarea["url"])

    if tarea.get("hora"):
        inicio = tarea["fecha"] + "T" + tarea["hora"] + ":00"
        base = datetime.strptime(tarea["fecha"] + " " + tarea["hora"], "%Y-%m-%d %H:%M")
        fin = (base + timedelta(minutes=int(tarea.get("estimado_min") or 30))).strftime("%Y-%m-%dT%H:%M:%S")
        evento = {
            "summary": titulo,
            "description": "\n".join(descripcion),
            "start": {"dateTime": inicio, "timeZone": ZONA},
            "end": {"dateTime": fin, "timeZone": ZONA},
        }
    else:
        siguiente = (datetime.strptime(tarea["fecha"], "%Y-%m-%d") + timedelta(days=1))
        evento = {
            "summary": titulo,
            "description": "\n".join(descripcion),
            "start": {"date": tarea["fecha"]},
            "end": {"date": siguiente.strftime("%Y-%m-%d")},
        }
    return evento


def crear_evento(tarea):
    respuesta = _pedir("POST", URL_CALENDAR, _evento_de(tarea))
    return respuesta.get("id")


def actualizar_evento(identificador, tarea):
    if not identificador:
        return crear_evento(tarea)
    respuesta = _pedir("PATCH", URL_CALENDAR + "/" + urllib.parse.quote(identificador),
                       _evento_de(tarea))
    if respuesta.get("_no_encontrado"):
        return crear_evento(tarea)
    return respuesta.get("id", identificador)


def borrar_evento(identificador):
    if not identificador:
        return True
    _pedir("DELETE", URL_CALENDAR + "/" + urllib.parse.quote(identificador))
    return True


# ------------------------------------------------------------------ tareas

def _tarea_de(tarea):
    cuerpo = {
        "title": tarea["titulo"][:1000],
        "notes": (tarea.get("notas") or "")[:8000],
    }
    if tarea.get("fecha"):
        cuerpo["due"] = tarea["fecha"] + "T00:00:00.000Z"
    if tarea["estado"] == "hecha":
        cuerpo["status"] = "completed"
    return cuerpo


def crear_tarea_google(tarea):
    respuesta = _pedir("POST", URL_TASKS, _tarea_de(tarea))
    return respuesta.get("id")


def actualizar_tarea_google(identificador, tarea):
    if not identificador:
        return crear_tarea_google(tarea)
    cuerpo = _tarea_de(tarea)
    respuesta = _pedir("PATCH", URL_TASKS + "/" + urllib.parse.quote(identificador), cuerpo)
    if respuesta.get("_no_encontrado"):
        return crear_tarea_google(tarea)
    return respuesta.get("id", identificador)


def borrar_tarea_google(identificador):
    if not identificador:
        return True
    _pedir("DELETE", URL_TASKS + "/" + urllib.parse.quote(identificador))
    return True


# ------------------------------------------------------------ sincronizar

def sincronizar(con, solo_id=None):
    if not estado()["conectado"]:
        return {"ok": False, "error": "Google no esta conectado."}

    con.row_factory = None
    columnas = [fila[1] for fila in con.execute("PRAGMA table_info(tareas)").fetchall()]
    if "gcal_id" not in columnas:
        return {"ok": False, "error": "Falta preparar la base (reinicia la app)."}

    consulta = (
        "SELECT id, titulo, notas, area, fecha, hora, estado, estimado_min, url,"
        " COALESCE(perdida,0), gcal_id, gcal_hash, gtask_id"
        " FROM tareas WHERE COALESCE(perdida,0) = 0")
    valores = []
    if solo_id:
        consulta += " AND id = ?"
        valores.append(solo_id)
    filas = con.execute(consulta + " ORDER BY id", valores).fetchall()

    eventos_nuevos = 0
    eventos_actualizados = 0
    tareas_nuevas = 0
    tareas_actualizadas = 0
    errores = []

    for fila in filas:
        tarea = {
            "id": fila[0], "titulo": fila[1], "notas": fila[2] or "", "area": fila[3] or "",
            "fecha": fila[4], "hora": fila[5], "estado": fila[6],
            "estimado_min": fila[7], "url": fila[8] or "",
            "perdida": fila[9], "gcal_id": fila[10], "gcal_hash": fila[11],
            "gtask_id": fila[12],
        }
        huella = "%s|%s|%s|%s|%s" % (tarea["titulo"], tarea["fecha"], tarea["hora"],
                                     tarea["estado"], tarea["area"])

        try:
            # --- Google Calendar (solo si tiene fecha)
            if tarea["fecha"]:
                if not tarea["gcal_id"]:
                    nuevo = crear_evento(tarea)
                    if nuevo:
                        con.execute("UPDATE tareas SET gcal_id = ?, gcal_hash = ? WHERE id = ?",
                                    (nuevo, huella, tarea["id"]))
                        eventos_nuevos += 1
                elif tarea["gcal_hash"] != huella:
                    actualizado = actualizar_evento(tarea["gcal_id"], tarea)
                    con.execute("UPDATE tareas SET gcal_id = ?, gcal_hash = ? WHERE id = ?",
                                (actualizado, huella, tarea["id"]))
                    eventos_actualizados += 1

            # --- Google Tasks (todas)
            if not tarea["gtask_id"]:
                nuevo = crear_tarea_google(tarea)
                if nuevo:
                    con.execute("UPDATE tareas SET gtask_id = ? WHERE id = ?",
                                (nuevo, tarea["id"]))
                    tareas_nuevas += 1
            elif tarea["gcal_hash"] != huella:
                actualizado = actualizar_tarea_google(tarea["gtask_id"], tarea)
                con.execute("UPDATE tareas SET gtask_id = ? WHERE id = ?",
                            (actualizado, tarea["id"]))
                tareas_actualizadas += 1

            if not tarea["fecha"]:
                con.execute("UPDATE tareas SET gcal_hash = ? WHERE id = ?", (huella, tarea["id"]))
            con.commit()
            time.sleep(0.15)
        except ErrorGoogle as error:
            if str(error).startswith("Google rechazo la peticion: Not Found"):
                continue
            errores.append("%s: %s" % (tarea["titulo"][:40], error))

    resultado = {
        "ok": len(errores) == 0,
        "eventos_nuevos": eventos_nuevos,
        "eventos_actualizados": eventos_actualizados,
        "tareas_nuevas": tareas_nuevas,
        "tareas_actualizadas": tareas_actualizadas,
        "errores": errores[:5],
        "revisadas": len(filas),
        "momento": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return resultado
