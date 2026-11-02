# -*- coding: utf-8 -*-
"""TodoUtesa - app web local de tareas + pomodoro + seguimiento.
Backend solo con la biblioteca estandar de Python (http.server + sqlite3).
Sin dependencias, portable a Windows, Linux, macOS y VPS.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import moodle
import google_sync
import telegram

RUTA_BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_WEB = os.path.join(RUTA_BASE, "web")
RUTA_DATOS = os.path.join(RUTA_BASE, "datos")
RUTA_DB = os.path.join(RUTA_DATOS, "todoutesa.db")
RUTA_DB_ANTERIOR = os.path.join(RUTA_DATOS, "habitos.db")
PUERTO_INICIAL = 8630
HORAS_ENTRE_SINCRONIAS = 6

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS tareas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo       TEXT NOT NULL,
    notas        TEXT NOT NULL DEFAULT '',
    area         TEXT NOT NULL DEFAULT 'General',
    prioridad    INTEGER NOT NULL DEFAULT 2,
    fecha        TEXT,
    hora         TEXT,
    estimado_min INTEGER NOT NULL DEFAULT 30,
    estado       TEXT NOT NULL DEFAULT 'pendiente',
    creada       TEXT NOT NULL,
    completada   TEXT,
    origen       TEXT NOT NULL DEFAULT 'web'
);
CREATE TABLE IF NOT EXISTS sesiones (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tarea_id INTEGER,
    inicio   TEXT NOT NULL,
    minutos  INTEGER NOT NULL DEFAULT 0,
    tipo     TEXT NOT NULL DEFAULT 'foco',
    completa INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
CREATE TABLE IF NOT EXISTS apuntes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo      TEXT NOT NULL DEFAULT '',
    cuerpo      TEXT NOT NULL DEFAULT '',
    tarea_id    INTEGER,
    creada      TEXT NOT NULL,
    actualizada TEXT
);
CREATE INDEX IF NOT EXISTS ix_tareas_fecha ON tareas(fecha);
CREATE INDEX IF NOT EXISTS ix_sesiones_inicio ON sesiones(inicio);
"""

COLUMNAS_NUEVAS = [
    ("externa_id", "TEXT"),
    ("url", "TEXT"),
    ("perdida", "INTEGER NOT NULL DEFAULT 0"),
    ("gcal_id", "TEXT"),
    ("gcal_hash", "TEXT"),
    ("gtask_id", "TEXT"),
]


# ---------------------------------------------------------------- utilidades

def ahora_texto():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hoy_texto():
    return date.today().isoformat()


def conectar():
    con = sqlite3.connect(RUTA_DB, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def iniciar_db():
    if not os.path.isdir(RUTA_DATOS):
        os.makedirs(RUTA_DATOS)

    # migracion: versiones anteriores guardaban en habitos.db
    if not os.path.isfile(RUTA_DB) and os.path.isfile(RUTA_DB_ANTERIOR):
        try:
            os.rename(RUTA_DB_ANTERIOR, RUTA_DB)
            print("[datos] base migrada de habitos.db a todoutesa.db", flush=True)
        except OSError as error:
            print("[datos] no pude renombrar la base:", error, flush=True)

    con = conectar()
    con.executescript(ESQUEMA)

    existentes = []
    for fila in con.execute("PRAGMA table_info(tareas)").fetchall():
        existentes.append(fila["name"])
    for nombre, tipo in COLUMNAS_NUEVAS:
        if nombre not in existentes:
            con.execute("ALTER TABLE tareas ADD COLUMN " + nombre + " " + tipo)

    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tareas_externa"
                " ON tareas(externa_id) WHERE externa_id IS NOT NULL")
    con.commit()
    con.close()


# ------------------------------------------------------- sincronizacion nube

def sincronizar_moodle(incluir_vencidas=False):
    con = conectar()
    try:
        resultado = moodle.sincronizar(con, incluir_vencidas=incluir_vencidas)
    except Exception as error:
        resultado = {"ok": False, "error": "Fallo la sincronizacion: %s" % error}
        try:
            moodle.guardar_estado(con, resultado)
        except Exception:
            pass
    finally:
        con.close()

    if resultado.get("ok") and resultado.get("nuevas"):
        titulos = resultado.get("nuevas_titulos") or []
        texto = "Tareas nuevas en Moodle: %d" % resultado["nuevas"]
        if titulos:
            texto += "\n" + "\n".join("- " + t for t in titulos)
        avisar_telegram(texto)
    return resultado


def bucle_moodle():
    time.sleep(12)
    while True:
        try:
            if moodle.cargar_configuracion() is not None:
                resultado = sincronizar_moodle()
                if resultado.get("ok"):
                    print("[nube] sync: %d nuevas, %d actualizadas de %d revisadas"
                          % (resultado["nuevas"], resultado["actualizadas"],
                             resultado["revisadas"]), flush=True)
                else:
                    print("[nube] sync fallo: %s" % resultado.get("error"), flush=True)
        except Exception as error:
            print("[nube] error en el bucle:", error, flush=True)
        time.sleep(HORAS_ENTRE_SINCRONIAS * 3600)


def rango_periodo(periodo):
    referencia = date.today()
    if periodo == "mes":
        inicio = referencia.replace(day=1)
        if referencia.month == 12:
            siguiente = date(referencia.year + 1, 1, 1)
        else:
            siguiente = date(referencia.year, referencia.month + 1, 1)
        fin = siguiente - timedelta(days=1)
    else:
        inicio = referencia - timedelta(days=referencia.weekday())
        fin = inicio + timedelta(days=6)
    return inicio.isoformat(), fin.isoformat()


def a_entero(valor, por_defecto=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return por_defecto


def limpiar_fecha(texto):
    # acepta '' , 'YYYY-MM-DD' ; cualquier otra cosa se descarta
    if not texto:
        return None
    texto = str(texto).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", texto):
        return texto
    return None


def limpiar_hora(texto):
    if not texto:
        return None
    texto = str(texto).strip()
    if re.match(r"^\d{2}:\d{2}$", texto):
        return texto
    return None


# ---------------------------------------------------------------- tareas

ORDEN_PENDIENTES = (
    " ORDER BY (fecha IS NULL), fecha, prioridad, id DESC"
)


def listar_tareas(argumentos):
    filtro = (argumentos.get("filtro") or ["todas"])[0]
    buscar = (argumentos.get("q") or [""])[0].strip()
    desde = (argumentos.get("desde") or [""])[0].strip()
    hasta = (argumentos.get("hasta") or [""])[0].strip()

    sql = "SELECT * FROM tareas WHERE 1=1"
    valores = []

    if filtro == "pendientes":
        sql += " AND estado = 'pendiente' AND COALESCE(perdida,0) = 0"
    elif filtro == "por_hacer":
        sql += " AND estado = 'pendiente' AND COALESCE(perdida,0) = 0"
        sql += " AND (fecha IS NULL OR fecha >= ?)"
        valores.append(hoy_texto())
    elif filtro == "perdidas":
        sql += " AND estado = 'pendiente' AND COALESCE(perdida,0) = 1"
    elif filtro == "hechas":
        sql += " AND estado = 'hecha'"
    elif filtro == "hoy":
        sql += " AND estado = 'pendiente' AND COALESCE(perdida,0) = 0 AND fecha = ?"
        valores.append(hoy_texto())
    elif filtro == "atrasadas":
        sql += " AND estado = 'pendiente' AND COALESCE(perdida,0) = 0"
        sql += " AND fecha IS NOT NULL AND fecha < ?"
        valores.append(hoy_texto())
    elif filtro == "semana":
        inicio, fin = rango_periodo("semana")
        sql += " AND fecha BETWEEN ? AND ? AND COALESCE(perdida,0) = 0"
        valores.append(inicio)
        valores.append(fin)

    if desde:
        sql += " AND fecha >= ?"
        valores.append(desde)
    if hasta:
        sql += " AND fecha <= ?"
        valores.append(hasta)
    if buscar:
        sql += " AND (titulo LIKE ? OR notas LIKE ? OR area LIKE ?)"
        comodin = "%" + buscar + "%"
        valores.append(comodin)
        valores.append(comodin)
        valores.append(comodin)

    if filtro == "hechas":
        sql += " ORDER BY completada DESC, id DESC"
    else:
        sql += ORDEN_PENDIENTES

    con = conectar()
    filas = con.execute(sql, valores).fetchall()
    con.close()
    return [dict(f) for f in filas]


def obtener_tarea(identificador):
    con = conectar()
    fila = con.execute("SELECT * FROM tareas WHERE id = ?", (identificador,)).fetchone()
    con.close()
    if fila is None:
        return None
    return dict(fila)


def crear_tarea(datos):
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        return None
    con = conectar()
    cur = con.execute(
        "INSERT INTO tareas (titulo, notas, area, prioridad, fecha, hora, estimado_min,"
        " estado, creada, origen) VALUES (?,?,?,?,?,?,?,'pendiente',?,?)",
        (
            titulo,
            (datos.get("notas") or "").strip(),
            (datos.get("area") or "General").strip(),
            a_entero(datos.get("prioridad"), 2),
            limpiar_fecha(datos.get("fecha")),
            limpiar_hora(datos.get("hora")),
            a_entero(datos.get("estimado_min"), 30),
            ahora_texto(),
            (datos.get("origen") or "web").strip(),
        ),
    )
    con.commit()
    nuevo = cur.lastrowid
    con.close()
    return obtener_tarea(nuevo)


def actualizar_tarea(identificador, datos):
    actual = obtener_tarea(identificador)
    if actual is None:
        return None

    titulo = datos.get("titulo")
    if titulo is not None:
        titulo = titulo.strip()
    notas = datos.get("notas")
    area = datos.get("area")
    prioridad = datos.get("prioridad")
    fecha = datos.get("fecha")
    hora = datos.get("hora")
    estimado = datos.get("estimado_min")
    estado = datos.get("estado")

    completada = actual["completada"]
    if estado is not None:
        if estado == "hecha":
            if actual["estado"] != "hecha":
                completada = ahora_texto()
        else:
            completada = None
    elif actual["estado"] == "hecha":
        completada = actual["completada"]

    campos = []
    valores = []
    if titulo is not None:
        campos.append("titulo = ?")
        valores.append(titulo)
    if notas is not None:
        campos.append("notas = ?")
        valores.append(notas.strip())
    if area is not None:
        campos.append("area = ?")
        valores.append(area.strip() or "General")
    if prioridad is not None:
        campos.append("prioridad = ?")
        valores.append(a_entero(prioridad, 2))
    if fecha is not None:
        campos.append("fecha = ?")
        valores.append(limpiar_fecha(fecha))
    if hora is not None:
        campos.append("hora = ?")
        valores.append(limpiar_hora(hora))
    if estimado is not None:
        campos.append("estimado_min = ?")
        valores.append(a_entero(estimado, 30))
    if estado is not None:
        campos.append("estado = ?")
        valores.append("hecha" if estado == "hecha" else "pendiente")
        campos.append("completada = ?")
        valores.append(completada)

    if not campos:
        return actual

    valores.append(identificador)
    con = conectar()
    con.execute("UPDATE tareas SET " + ", ".join(campos) + " WHERE id = ?", valores)
    con.commit()
    con.close()
    return obtener_tarea(identificador)


def borrar_tarea(identificador):
    con = conectar()
    cur = con.execute("DELETE FROM tareas WHERE id = ?", (identificador,))
    con.commit()
    borradas = cur.rowcount
    con.close()
    return borradas > 0


# ---------------------------------------------------------------- sesiones

def registrar_sesion(datos):
    minutos = a_entero(datos.get("minutos"), 0)
    if minutos <= 0:
        return None
    tipo = (datos.get("tipo") or "foco").strip()
    tarea_id = datos.get("tarea_id")
    if tarea_id in ("", None, 0, "0"):
        tarea_id = None
    else:
        tarea_id = a_entero(tarea_id, 0) or None
    completa = 1 if datos.get("completa", True) else 0

    con = conectar()
    cur = con.execute(
        "INSERT INTO sesiones (tarea_id, inicio, minutos, tipo, completa)"
        " VALUES (?,?,?,?,?)",
        (tarea_id, ahora_texto(), minutos, tipo, completa),
    )
    con.commit()
    nuevo = cur.lastrowid
    con.close()
    return {"id": nuevo, "minutos": minutos, "tarea_id": tarea_id, "tipo": tipo}


def listar_sesiones(argumentos):
    desde = (argumentos.get("desde") or [""])[0]
    hasta = (argumentos.get("hasta") or [""])[0]
    sql = (
        "SELECT s.*, t.titulo AS tarea_titulo, t.area AS tarea_area"
        " FROM sesiones s LEFT JOIN tareas t ON t.id = s.tarea_id WHERE 1=1"
    )
    valores = []
    if desde:
        sql += " AND date(s.inicio) >= ?"
        valores.append(desde)
    if hasta:
        sql += " AND date(s.inicio) <= ?"
        valores.append(hasta)
    sql += " ORDER BY s.inicio DESC LIMIT 500"
    con = conectar()
    filas = con.execute(sql, valores).fetchall()
    con.close()
    return [dict(f) for f in filas]


# ---------------------------------------------------------------- metricas

def metricas(periodo):
    inicio, fin = rango_periodo(periodo)
    con = conectar()

    foco = con.execute(
        "SELECT COALESCE(SUM(minutos),0) AS m, COUNT(*) AS n FROM sesiones"
        " WHERE tipo = 'foco' AND date(inicio) BETWEEN ? AND ?",
        (inicio, fin),
    ).fetchone()

    por_dia = con.execute(
        "SELECT date(inicio) AS dia, SUM(minutos) AS minutos FROM sesiones"
        " WHERE tipo = 'foco' AND date(inicio) BETWEEN ? AND ?"
        " GROUP BY dia ORDER BY dia",
        (inicio, fin),
    ).fetchall()

    por_area = con.execute(
        "SELECT COALESCE(t.area,'Sin tarea') AS area, SUM(s.minutos) AS minutos,"
        " COUNT(*) AS sesiones FROM sesiones s LEFT JOIN tareas t ON t.id = s.tarea_id"
        " WHERE s.tipo = 'foco' AND date(s.inicio) BETWEEN ? AND ?"
        " GROUP BY area ORDER BY minutos DESC",
        (inicio, fin),
    ).fetchall()

    destacadas = con.execute(
        "SELECT COALESCE(t.titulo,'(sin tarea)') AS titulo, SUM(s.minutos) AS minutos,"
        " COUNT(*) AS sesiones FROM sesiones s LEFT JOIN tareas t ON t.id = s.tarea_id"
        " WHERE s.tipo = 'foco' AND date(s.inicio) BETWEEN ? AND ?"
        " GROUP BY titulo ORDER BY minutos DESC LIMIT 8",
        (inicio, fin),
    ).fetchall()

    completadas = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE completada IS NOT NULL"
        " AND date(completada) BETWEEN ? AND ?",
        (inicio, fin),
    ).fetchone()["n"]

    programadas = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE fecha BETWEEN ? AND ?",
        (inicio, fin),
    ).fetchone()["n"]

    vencidas = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'pendiente'"
        " AND COALESCE(perdida,0) = 0 AND fecha IS NOT NULL AND fecha < ?",
        (hoy_texto(),),
    ).fetchone()["n"]

    con.close()

    if programadas > 0:
        cumplimiento = int(round(completadas * 100.0 / programadas))
    else:
        cumplimiento = 0

    # racha: dias consecutivos con al menos un bloque de foco (hacia atras)
    racha = calcular_racha()

    return {
        "periodo": periodo,
        "desde": inicio,
        "hasta": fin,
        "minutos_foco": foco["m"],
        "horas_foco": round(foco["m"] / 60.0, 1),
        "bloques": foco["n"],
        "promedio_bloque": int(round(foco["m"] / foco["n"])) if foco["n"] else 0,
        "completadas": completadas,
        "programadas": programadas,
        "cumplimiento": cumplimiento,
        "vencidas": vencidas,
        "racha": racha,
        "por_dia": [dict(f) for f in por_dia],
        "por_area": [dict(f) for f in por_area],
        "destacadas": [dict(f) for f in destacadas],
    }


def racha_detallada():
    """Racha de dias activos: vale un bloque de foco o marcar una tarea hecha."""
    con = conectar()
    filas = con.execute(
        "SELECT dia, SUM(minutos) AS minutos, SUM(hechas) AS hechas FROM ("
        " SELECT date(inicio) AS dia, minutos AS minutos, 0 AS hechas"
        " FROM sesiones WHERE tipo = 'foco'"
        " UNION ALL"
        " SELECT date(completada) AS dia, 0 AS minutos, 1 AS hechas"
        " FROM tareas WHERE completada IS NOT NULL"
        ") WHERE dia IS NOT NULL GROUP BY dia ORDER BY dia DESC LIMIT 400"
    ).fetchall()
    con.close()

    minutos_por_dia = {}
    hechas_por_dia = {}
    for fila in filas:
        minutos_por_dia[fila["dia"]] = fila["minutos"] or 0
        hechas_por_dia[fila["dia"]] = fila["hechas"] or 0

    activos = set()
    for dia in minutos_por_dia:
        if dia:
            activos.add(dia)

    hoy = date.today()
    cursor = hoy
    if cursor.isoformat() not in activos:
        cursor = cursor - timedelta(days=1)
    actual = 0
    while cursor.isoformat() in activos:
        actual += 1
        cursor = cursor - timedelta(days=1)

    mejor = 0
    anterior = None
    seguidas = 0
    for texto in sorted(activos):
        partes = texto.split("-")
        este = date(int(partes[0]), int(partes[1]), int(partes[2]))
        if anterior is not None and (este - anterior).days == 1:
            seguidas += 1
        else:
            seguidas = 1
        if seguidas > mejor:
            mejor = seguidas
        anterior = este

    ultimos = []
    for posicion in range(6, -1, -1):
        dia = hoy - timedelta(days=posicion)
        iso = dia.isoformat()
        ultimos.append({
            "fecha": iso,
            "activo": iso in activos,
            "minutos": minutos_por_dia.get(iso, 0),
            "hechas": hechas_por_dia.get(iso, 0),
        })

    hoy_activo = hoy.isoformat() in activos
    insignia = "Empezando"
    if actual >= 30:
        insignia = "Imparable"
    elif actual >= 14:
        insignia = "Constante"
    elif actual >= 7:
        insignia = "Semana completa"
    elif actual >= 3:
        insignia = "Arrancando"

    if hoy_activo:
        mensaje = "Hoy ya cuenta. Llevas %d dias seguidos." % actual
    elif actual > 0:
        mensaje = ("Todavia no registras nada hoy. Un bloque de 25 minutos "
                   "o marcar una tarea mantiene la racha de %d." % actual)
    else:
        mensaje = "Arranca hoy: un bloque de 25 minutos o marcar una tarea hecha."

    return {
        "actual": actual,
        "mejor": mejor,
        "hoy_activo": hoy_activo,
        "insignia": insignia,
        "dias": ultimos,
        "activos_semana": sum(1 for dia in ultimos if dia["activo"]),
        "meta_semana": 5,
        "minutos_semana": sum(dia["minutos"] for dia in ultimos),
        "hechas_semana": sum(dia["hechas"] for dia in ultimos),
        "mensaje": mensaje,
    }


def calcular_racha():
    con = conectar()
    filas = con.execute(
        "SELECT DISTINCT date(inicio) AS dia FROM sesiones"
        " WHERE tipo = 'foco' ORDER BY dia DESC LIMIT 60"
    ).fetchall()
    con.close()
    dias = set()
    for fila in filas:
        dias.add(fila["dia"])
    if not dias:
        return 0
    cursor = date.today()
    if cursor.isoformat() not in dias:
        cursor = cursor - timedelta(days=1)
    racha = 0
    while cursor.isoformat() in dias:
        racha += 1
        cursor = cursor - timedelta(days=1)
    return racha


def resumen():
    con = conectar()
    pendientes = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'pendiente'"
        " AND COALESCE(perdida,0) = 0"
    ).fetchone()["n"]
    perdidas = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'pendiente'"
        " AND COALESCE(perdida,0) = 1"
    ).fetchone()["n"]
    por_hacer = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'pendiente'"
        " AND COALESCE(perdida,0) = 0 AND (fecha IS NULL OR fecha >= ?)",
        (hoy_texto(),),
    ).fetchone()["n"]
    de_hoy = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'pendiente'"
        " AND COALESCE(perdida,0) = 0 AND fecha = ?",
        (hoy_texto(),),
    ).fetchone()["n"]
    hechas_hoy = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE completada IS NOT NULL"
        " AND date(completada) = ?",
        (hoy_texto(),),
    ).fetchone()["n"]
    minutos_hoy = con.execute(
        "SELECT COALESCE(SUM(minutos),0) AS m FROM sesiones"
        " WHERE tipo = 'foco' AND date(inicio) = ?",
        (hoy_texto(),),
    ).fetchone()["m"]
    sin_fecha = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'pendiente'"
        " AND COALESCE(perdida,0) = 0 AND fecha IS NULL"
    ).fetchone()["n"]
    total_hechas = con.execute(
        "SELECT COUNT(*) AS n FROM tareas WHERE estado = 'hecha'"
    ).fetchone()["n"]
    minutos_totales = con.execute(
        "SELECT COALESCE(SUM(minutos),0) AS m FROM sesiones WHERE tipo = 'foco'"
    ).fetchone()["m"]
    con.close()

    semana = metricas("semana")
    racha = racha_detallada()
    return {
        "hoy": hoy_texto(),
        "pendientes": pendientes,
        "por_hacer": por_hacer,
        "perdidas": perdidas,
        "de_hoy": de_hoy,
        "hechas_hoy": hechas_hoy,
        "minutos_hoy": minutos_hoy,
        "sin_fecha": sin_fecha,
        "total_hechas": total_hechas,
        "horas_totales": round(minutos_totales / 60.0, 1),
        "semana_minutos": semana["minutos_foco"],
        "semana_cumplimiento": semana["cumplimiento"],
        "racha": racha["actual"],
        "racha_mejor": racha["mejor"],
        "racha_insignia": racha["insignia"],
        "vencidas": semana["vencidas"],
    }


# ---------------------------------------------------------------- estimacion

REGLAS_ESTIMACION = [
    (["leer", "estudiar", "repasar", "investigar", "leer capitulo"], 45),
    (["escribir", "redactar", "documento", "informe", "ensayo", "tesis"], 60),
    (["programar", "codigo", "implementar", "bug", "depurar", "modulo"], 60),
    (["disenar", "maqueta", "prototipo", "diagrama"], 50),
    (["reunion", "llamada", "entrevista", "clase", "examen"], 40),
    (["limpiar", "ordenar", "lavar", "organizar"], 25),
    (["comprar", "pagar", "factura", "banco", "transferir"], 15),
    (["ejercicio", "gym", "entrenar", "correr", "caminar"], 45),
    (["correo", "email", "responder", "mensaje"], 10),
    (["revisar", "verificar", "probar", "test"], 30),
]


def estimar_tarea(datos):
    titulo = (datos.get("titulo") or "").strip()
    notas = (datos.get("notas") or "").strip()
    area = (datos.get("area") or "General").strip()
    texto = (titulo + " " + notas + " " + area).lower()

    minutos = 30
    razon = "Tarea general: parto de bloques de 30 minutos."
    for palabras, valor in REGLAS_ESTIMACION:
        for palabra in palabras:
            if palabra in texto:
                minutos = valor
                razon = "Detecte la actividad '" + palabra + "': base de " + str(valor) + " min."
                break
        if razon != "Tarea general: parto de bloques de 30 minutos.":
            break

    # el detalle en las notas aumenta el trabajo real
    if len(notas) > 120:
        minutos += 15
        razon += " Las notas son detalladas, sumo 15 min."
    elif len(notas) > 40:
        minutos += 5

    # varias ideas sueltas en el titulo = varias subtareas
    partes = [p for p in re.split(r"[,;y+]| y ", titulo) if len(p.strip()) > 3]
    if len(partes) > 1:
        minutos += 15 * (len(partes) - 1)
        razon += " El titulo tiene " + str(len(partes)) + " partes, sumo tiempo por cada una."

    if minutos < 10:
        minutos = 10
    if minutos > 240:
        minutos = 240
    minutos = int(round(minutos / 5.0) * 5)

    bloques = int((minutos + 24) // 25)
    if bloques < 1:
        bloques = 1

    subtareas = []
    if minutos >= 45:
        tramos = 2 if minutos < 90 else 3
        base = minutos // tramos
        nombres = ["Preparar y arrancar", "Trabajo principal", "Cerrar y revisar"]
        for i in range(tramos):
            texto_sub = nombres[i] if i < 3 else "Parte " + str(i + 1)
            subtareas.append({"titulo": texto_sub, "minutos": base})

    return {
        "minutos": minutos,
        "bloques": bloques,
        "subtareas": subtareas,
        "razon": razon,
        "motor": "heuristica-local",
    }


# ---------------------------------------------------------------- servidor

# ---------------------------------------------------------------- apuntes

def listar_apuntes(argumentos):
    buscar = (argumentos.get("q") or [""])[0].strip()
    sql = "SELECT * FROM apuntes WHERE 1=1"
    valores = []
    if buscar:
        sql += " AND (titulo LIKE ? OR cuerpo LIKE ?)"
        comodin = "%" + buscar + "%"
        valores.append(comodin)
        valores.append(comodin)
    sql += " ORDER BY id DESC LIMIT 300"
    con = conectar()
    filas = con.execute(sql, valores).fetchall()
    con.close()
    return [dict(f) for f in filas]


def obtener_apunte(identificador):
    con = conectar()
    fila = con.execute("SELECT * FROM apuntes WHERE id = ?", (identificador,)).fetchone()
    con.close()
    return dict(fila) if fila else None


def crear_apunte(datos):
    cuerpo = (datos.get("cuerpo") or "").strip()
    titulo = (datos.get("titulo") or "").strip()
    if not cuerpo and not titulo:
        return None
    if not titulo:
        titulo = cuerpo.split("\n")[0][:60]
    tarea_id = a_entero(datos.get("tarea_id"), 0) or None
    con = conectar()
    cur = con.execute(
        "INSERT INTO apuntes (titulo, cuerpo, tarea_id, creada) VALUES (?,?,?,?)",
        (titulo, cuerpo, tarea_id, ahora_texto()))
    con.commit()
    nuevo = cur.lastrowid
    con.close()
    return obtener_apunte(nuevo)


def actualizar_apunte(identificador, datos):
    actual = obtener_apunte(identificador)
    if actual is None:
        return None
    titulo = datos.get("titulo")
    if titulo is None:
        titulo = actual["titulo"]
    cuerpo = datos.get("cuerpo")
    if cuerpo is None:
        cuerpo = actual["cuerpo"]
    con = conectar()
    con.execute("UPDATE apuntes SET titulo = ?, cuerpo = ?, actualizada = ? WHERE id = ?",
                (titulo.strip(), cuerpo, ahora_texto(), identificador))
    con.commit()
    con.close()
    return obtener_apunte(identificador)


def borrar_apunte(identificador):
    con = conectar()
    cur = con.execute("DELETE FROM apuntes WHERE id = ?", (identificador,))
    con.commit()
    borradas = cur.rowcount
    con.close()
    return borradas > 0


# ------------------------------------------------- tareas parecidas

def buscar_parecida(titulo):
    """Tarea pendiente ya existente casi igual (para no duplicar)."""
    if not titulo:
        return None
    con = conectar()
    filas = con.execute(
        "SELECT * FROM tareas WHERE estado = 'pendiente' ORDER BY id DESC LIMIT 200").fetchall()
    con.close()
    mejor = None
    mejor_puntaje = 0.0
    for fila in filas:
        puntaje = moodle.similitud(titulo, fila["titulo"])
        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor = dict(fila)
    if mejor is not None and mejor_puntaje >= 0.72:
        mejor["similitud"] = round(mejor_puntaje, 2)
        return mejor
    return None


# ------------------------------------------------------------- telegram

RUTA_TELEGRAM = os.path.join(RUTA_DATOS, "telegram.json")

AYUDA = (
    "Comandos:\n"
    "/add <texto> | <fecha o 'hoy'/'manana'> - crear tarea\n"
    "/hoy - lo de hoy y lo atrasado\n"
    "/pendientes - lo que te falta por hacer\n"
    "/atrasadas - lo que se vencio y sigue sin hacer\n"
    "/racha - como va tu racha de dias activos\n"
    "/perdidas - lo que ya no acepta entrega\n"
    "/recordatorio on|off - avisos automaticos\n"
    "/intervalo 90 - cada cuanto te aviso\n"
    "/hecho <numero> - marcar hecha\n"
    "/agendar <numero> <2026-11-05 18:00> - cambiar fecha\n"
    "/pomo <numero> [minutos] - registrar bloque de foco\n"
    "/sync - traer novedades de Moodle\n"
    "/nota <texto> - guardar apunte\n"
    "/notas - ultimos apuntes\n"
    "/buscar <texto>\n\n"
    "Si me mandas texto suelto, lo guardo como tarea nueva."
)


def cargar_telegram():
    try:
        with open(RUTA_TELEGRAM, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, ValueError):
        return {}


def guardar_telegram(datos):
    if not os.path.isdir(RUTA_DATOS):
        os.makedirs(RUTA_DATOS)
    with open(RUTA_TELEGRAM, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    try:
        os.chmod(RUTA_TELEGRAM, 0o600)
    except OSError:
        pass


def estado_telegram():
    config = cargar_telegram()
    token = config.get("token") or ""
    return {
        "configurado": bool(token),
        "chat_id": config.get("chat_id"),
        "bot": config.get("bot"),
        "token_visible": (token[:8] + "..." + token[-4:]) if len(token) > 14 else "",
    }


def avisar_telegram(texto):
    config = cargar_telegram()
    token = config.get("token")
    chat = config.get("chat_id")
    if not token or not chat:
        return False
    respuesta = telegram.enviar(token, chat, texto)
    return bool(respuesta.get("ok"))


def bucle_telegram():
    time.sleep(6)
    while True:
        config = cargar_telegram()
        token = config.get("token")
        if not token:
            time.sleep(30)
            continue
        try:
            telegram.bucle(token, atender_mensaje,
                           lambda t=token: (cargar_telegram().get("token") or "") == t,
                           atender_boton)
        except Exception as error:
            print("[telegram] el bot se detuvo:", error, flush=True)
        time.sleep(10)


def fecha_corta(iso):
    partes = (iso or "").split("-")
    if len(partes) < 3:
        return iso or ""
    return partes[2] + "/" + partes[1]


def interpretar_cuando(texto):
    texto = (texto or "").strip().lower()
    hora = None
    encontrada_hora = re.search(r"(\d{1,2}):(\d{2})", texto)
    if encontrada_hora:
        hora = "%02d:%s" % (int(encontrada_hora.group(1)), encontrada_hora.group(2))
    if not texto or texto.startswith("sin"):
        return None, None

    hoy = date.today()
    if "hoy" in texto:
        return hoy.isoformat(), hora
    if "manana" in texto or "mañana" in texto:
        return (hoy + timedelta(days=1)).isoformat(), hora

    completa = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if completa:
        return completa.group(0), hora
    corta = re.search(r"(\d{1,2})/(\d{1,2})", texto)
    if corta:
        return "%04d-%02d-%02d" % (hoy.year, int(corta.group(2)), int(corta.group(1))), hora
    return (hoy.isoformat() if hora else None), hora


def formatear_tareas(tareas, vacio):
    if not tareas:
        return vacio
    lineas = []
    for tarea in tareas[:25]:
        extra = ""
        if tarea["fecha"]:
            extra = " - " + fecha_corta(tarea["fecha"])
            if tarea["fecha"] < hoy_texto():
                extra += " (atrasada)"
        elif tarea.get("perdida"):
            extra = " - sin entrega"
        lineas.append("#%d %s%s" % (tarea["id"], tarea["titulo"][:70], extra))
    if len(tareas) > 25:
        lineas.append("... y %d mas" % (len(tareas) - 25))
    return "\n".join(lineas)


def atender_mensaje(texto, chat_id):
    config = cargar_telegram()
    autorizado = config.get("chat_id")
    limpio = (texto or "").strip()
    if not limpio:
        return None

    partes = limpio.split(" ", 1)
    comando = partes[0].lower().split("@")[0]
    resto = partes[1].strip() if len(partes) > 1 else ""

    if comando == "/start":
        if not autorizado:
            config["chat_id"] = chat_id
            guardar_telegram(config)
            return "Listo, jefe. Este chat queda vinculado a Habitos.\n\n" + AYUDA
        if str(autorizado) == str(chat_id):
            return "Ya estas vinculado.\n\n" + AYUDA
        return None

    if not autorizado:
        return "Manda /start para vincular este chat."
    if str(autorizado) != str(chat_id):
        return None

    if comando in ("/ayuda", "/help", "/comandos", "/start"):
        return AYUDA

    if comando == "/hoy":
        de_hoy = listar_tareas({"filtro": ["hoy"]})
        atrasadas = listar_tareas({"filtro": ["atrasadas"]})
        respuesta = "Hoy:\n" + formatear_tareas(de_hoy, "  nada para hoy.")
        if atrasadas:
            respuesta += "\n\nAtrasadas:\n" + formatear_tareas(atrasadas, "")
        return respuesta

    if comando in ("/pendientes", "/todo", "/lista"):
        return "Por hacer:\n" + formatear_tareas(
            listar_tareas({"filtro": ["por_hacer"]}), "  nada por hacer.")

    if comando == "/atrasadas":
        return "Atrasadas:\n" + formatear_tareas(
            listar_tareas({"filtro": ["atrasadas"]}), "  ninguna.")

    if comando == "/racha":
        datos = racha_detallada()
        respuesta = "Racha: %d dias seguidos (%s)\nMejor racha: %d\nSemana: %d/%d dias activos" % (
            datos["actual"], datos["insignia"], datos["mejor"],
            datos["activos_semana"], datos["meta_semana"])
        respuesta += "\n\n" + datos["mensaje"]
        return respuesta

    if comando == "/perdidas":
        return "Tareas perdidas (ya no aceptan entrega):\n" + formatear_tareas(
            listar_tareas({"filtro": ["perdidas"]}), "  ninguna.")

    if comando in ("/recordatorio", "/recordatorios"):
        orden = resto.lower()
        if orden in ("off", "no", "apagar", "0"):
            guardar_recordatorios({"activo": False})
            return "Recordatorios apagados."
        if orden in ("on", "si", "sí", "encender", "1"):
            guardar_recordatorios({"activo": True})
            return "Recordatorios encendidos."
        config = cargar_recordatorios()
        return ("Recordatorios %s: cada %d min, de %02d:00 a %02d:00.\n"
                "Para cambiar el ritmo: /intervalo 90"
                % ("ACTIVOS" if config["activo"] else "apagados",
                   config["minutos"], config["desde"], config["hasta"]))

    if comando == "/intervalo":
        minutos = a_entero(resto, 0)
        if not minutos:
            config = cargar_recordatorios()
            return "Ahora mismo: cada %d minutos. Uso: /intervalo 90" % config["minutos"]
        config = guardar_recordatorios({"minutos": minutos})
        return "Listo: te aviso cada %d minutos mientras tengas pendientes." % config["minutos"]

    if comando in ("/hecho", "/listo", "/done"):
        identificador = a_entero(resto.split(" ")[0] if resto else "", 0)
        if not identificador:
            return "Uso: /hecho 12"
        tarea = actualizar_tarea(identificador, {"estado": "hecha"})
        if tarea is None:
            return "No encontre la tarea #%d" % identificador
        return "Hecha: %s" % tarea["titulo"]

    if comando == "/agendar":
        trozos = resto.split(" ", 1)
        identificador = a_entero(trozos[0] if trozos else "", 0)
        if not identificador:
            return "Uso: /agendar 12 2026-11-05 18:00"
        fecha, hora = interpretar_cuando(trozos[1] if len(trozos) > 1 else "")
        if not fecha:
            return "No entendi la fecha. Usa 2026-11-05, 05/11, hoy o manana."
        tarea = actualizar_tarea(identificador, {"fecha": fecha, "hora": hora or ""})
        if tarea is None:
            return "No encontre la tarea #%d" % identificador
        return "Agendada #%d para %s %s" % (identificador, fecha, hora or "")

    if comando == "/pomo":
        trozos = resto.split(" ")
        identificador = a_entero(trozos[0] if trozos else "", 0)
        minutos = a_entero(trozos[1], 25) if len(trozos) > 1 else 25
        sesion = registrar_sesion({"tarea_id": identificador, "minutos": minutos, "tipo": "foco"})
        if sesion is None:
            return "Uso: /pomo 12 25"
        return "Guardados %d min de foco." % minutos

    if comando == "/sync":
        resultado = sincronizar_moodle()
        if not resultado.get("ok"):
            return "No pude sincronizar: %s" % resultado.get("error")
        return ("Nube: %d nuevas, %d actualizadas, %d cerradas, %d enlazadas."
                % (resultado["nuevas"], resultado["actualizadas"],
                   resultado["cerradas"], resultado["enlazadas"]))

    if comando == "/nota":
        if not resto:
            return "Uso: /nota texto de la nota"
        apunte = crear_apunte({"cuerpo": resto})
        if apunte is None:
            return "No pude guardar la nota."
        return "Nota #%d guardada." % apunte["id"]

    if comando == "/notas":
        apuntes = listar_apuntes({})
        if not apuntes:
            return "No hay notas todavia."
        lineas = []
        for apunte in apuntes[:8]:
            lineas.append("#%d %s" % (apunte["id"], apunte["titulo"][:80]))
        return "Notas:\n" + "\n".join(lineas)

    if comando == "/buscar":
        if not resto:
            return "Uso: /buscar texto"
        encontradas = listar_tareas({"filtro": ["todas"], "q": [resto]})
        return "Busqueda '" + resto + "':\n" + formatear_tareas(encontradas, "  sin resultados.")

    # texto suelto -> tarea nueva
    titulo = limpio
    fecha = None
    hora = None
    if "|" in limpio:
        trozos = limpio.split("|", 1)
        titulo = trozos[0].strip()
        fecha, hora = interpretar_cuando(trozos[1])

    if comando == "/add":
        titulo = resto
        if "|" in resto:
            trozos = resto.split("|", 1)
            titulo = trozos[0].strip()
            fecha, hora = interpretar_cuando(trozos[1])

    if not titulo:
        return AYUDA

    parecida = buscar_parecida(titulo)
    if parecida:
        return "Ya tienes algo parecido: #%d %s\nSi es otra cosa, cambia el titulo." % (
            parecida["id"], parecida["titulo"])

    tarea = crear_tarea({"titulo": titulo, "fecha": fecha, "hora": hora,
                         "origen": "telegram"})
    if tarea is None:
        return "No pude crear la tarea."
    extra = ""
    if fecha:
        extra = " para el " + fecha + (" " + hora if hora else "")
    return "Anotada #%d: %s%s" % (tarea["id"], tarea["titulo"], extra)


# ------------------------------------------------------- recordatorios

def cargar_recordatorios():
    con = conectar()
    valores = {}
    try:
        filas = con.execute(
            "SELECT clave, valor FROM ajustes WHERE clave LIKE 'rec_%'").fetchall()
        for fila in filas:
            valores[fila["clave"]] = fila["valor"]
    except Exception:
        pass
    con.close()

    return {
        "activo": valores.get("rec_activo", "1") == "1",
        "minutos": a_entero(valores.get("rec_minutos"), 90),
        "desde": a_entero(valores.get("rec_desde"), 7),
        "hasta": a_entero(valores.get("rec_hasta"), 23),
        "ultimo": valores.get("rec_ultimo", ""),
    }


def guardar_recordatorios(datos):
    actual = cargar_recordatorios()

    activo = datos.get("activo")
    if activo is None:
        activo = actual["activo"]
    minutos = a_entero(datos.get("minutos"), actual["minutos"])
    desde = a_entero(datos.get("desde"), actual["desde"])
    hasta = a_entero(datos.get("hasta"), actual["hasta"])

    if minutos < 5:
        minutos = 5
    if minutos > 720:
        minutos = 720
    if desde < 0:
        desde = 0
    if hasta > 24:
        hasta = 24
    if hasta <= desde:
        hasta = min(24, desde + 1)

    pares = [
        ("rec_activo", "1" if activo else "0"),
        ("rec_minutos", str(minutos)),
        ("rec_desde", str(desde)),
        ("rec_hasta", str(hasta)),
    ]
    con = conectar()
    for clave, valor in pares:
        con.execute("INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
                    " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                    (clave, valor))
    con.commit()
    con.close()
    return cargar_recordatorios()


def tareas_urgentes():
    """Primero las atrasadas, despues lo que falta por hacer."""
    lista = []
    for tarea in listar_tareas({"filtro": ["atrasadas"]}):
        lista.append(tarea)
    for tarea in listar_tareas({"filtro": ["por_hacer"]}):
        lista.append(tarea)
    return lista


def guardar_ajuste(clave, valor):
    con = conectar()
    con.execute("INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
                " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor))
    con.commit()
    con.close()


def enviar_recordatorio():
    telegrama = cargar_telegram()
    if not telegrama.get("token") or not telegrama.get("chat_id"):
        return {"enviado": False, "motivo": "Telegram sin vincular"}

    pendientes = tareas_urgentes()
    if not pendientes:
        return {"enviado": False, "motivo": "no hay pendientes"}

    atrasadas = 0
    para_hoy = 0
    for tarea in pendientes:
        if tarea["fecha"] and tarea["fecha"] < hoy_texto():
            atrasadas += 1
        elif tarea["fecha"] == hoy_texto():
            para_hoy += 1

    resumen = []
    if atrasadas:
        resumen.append("%d atrasada(s)" % atrasadas)
    if para_hoy:
        resumen.append("%d para hoy" % para_hoy)
    resumen.append("%d por hacer en total" % len(pendientes))

    texto = "Recordatorio: " + ", ".join(resumen) + "\n\n"
    primeras = pendientes[:6]
    for tarea in primeras:
        extra = ""
        if tarea["fecha"]:
            extra = " - " + fecha_corta(tarea["fecha"])
            if tarea["fecha"] < hoy_texto():
                extra += " atrasada"
        texto += "#%d %s%s\n" % (tarea["id"], tarea["titulo"][:60], extra)
    if len(pendientes) > 6:
        texto += "... y %d mas (manda /pendientes)\n" % (len(pendientes) - 6)

    racha = racha_detallada()
    if racha["actual"] > 0:
        texto += "\nRacha de %d dias. No la rompas hoy." % racha["actual"]

    teclado = {"inline_keyboard": []}
    for tarea in primeras[:5]:
        teclado["inline_keyboard"].append([{
            "text": "Listo  #%d %s" % (tarea["id"], tarea["titulo"][:24]),
            "callback_data": "h:%d" % tarea["id"]}])

    respuesta = telegram.enviar(telegrama["token"], telegrama["chat_id"], texto, teclado)
    if respuesta.get("ok"):
        guardar_ajuste("rec_ultimo", ahora_texto())
        return {"enviado": True, "tareas": len(pendientes)}
    return {"enviado": False,
            "motivo": respuesta.get("description") or respuesta.get("error") or "fallo el envio"}


def atender_boton(datos, chat_id):
    telegrama = cargar_telegram()
    if telegrama.get("chat_id") and str(telegrama["chat_id"]) != str(chat_id):
        return {"aviso": "No autorizado"}

    if not datos.startswith("h:"):
        return {"aviso": "Boton no reconocido"}

    identificador = a_entero(datos[2:], 0)
    tarea = actualizar_tarea(identificador, {"estado": "hecha"})
    if tarea is None:
        return {"aviso": "Esa tarea ya no existe"}

    empujar_google_hilo(identificador)
    pendientes = tareas_urgentes()
    racha = racha_detallada()

    mensaje = "Hecha: %s" % tarea["titulo"][:60]
    if pendientes:
        mensaje += "\nTe quedan %d por hacer." % len(pendientes)
    else:
        mensaje += "\nNo te queda nada pendiente. Bien ahi."
    if racha["actual"] > 0:
        mensaje += "\nRacha: %d dias." % racha["actual"]

    teclado = None
    if pendientes:
        teclado = {"inline_keyboard": []}
        for pendiente in pendientes[:5]:
            teclado["inline_keyboard"].append([{
                "text": "Listo  #%d %s" % (pendiente["id"], pendiente["titulo"][:24]),
                "callback_data": "h:%d" % pendiente["id"]}])

    return {"aviso": "Hecha", "mensaje": mensaje, "teclado": teclado}


def bucle_recordatorios():
    time.sleep(25)
    while True:
        try:
            config = cargar_recordatorios()
            telegrama = cargar_telegram()
            if config["activo"] and telegrama.get("token") and telegrama.get("chat_id"):
                ahora = datetime.now()
                if config["desde"] <= ahora.hour < config["hasta"]:
                    toca = True
                    if config["ultimo"]:
                        try:
                            previo = datetime.strptime(config["ultimo"], "%Y-%m-%d %H:%M:%S")
                            toca = (ahora - previo).total_seconds() >= config["minutos"] * 60
                        except ValueError:
                            toca = True
                    if toca:
                        resultado = enviar_recordatorio()
                        print("[recordatorios] %s" % resultado, flush=True)
        except Exception as error:
            print("[recordatorios] error:", error, flush=True)
        time.sleep(60)


# ------------------------------------------------------------------ google

def estado_google():
    info = google_sync.estado()
    con = conectar()
    try:
        fila = con.execute(
            "SELECT valor FROM ajustes WHERE clave = 'google_ultimo'").fetchone()
        if fila:
            try:
                info["ultimo"] = json.loads(fila["valor"])
            except ValueError:
                pass
    except Exception:
        pass
    con.close()
    return info


def sincronizar_google():
    con = conectar()
    try:
        resultado = google_sync.sincronizar(con)
    except Exception as error:
        resultado = {"ok": False, "error": "Fallo Google: %s" % error}
    finally:
        con.close()

    if resultado.get("ok") or resultado.get("revisadas"):
        con = conectar()
        con.execute(
            "INSERT INTO ajustes (clave, valor) VALUES ('google_ultimo', ?)"
            " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (json.dumps(resultado, ensure_ascii=False),))
        con.commit()
        con.close()
    return resultado


def empujar_google(tarea_id):
    """Manda una sola tarea a Google, sin bloquear la interfaz."""
    try:
        if not google_sync.estado()["conectado"]:
            return
        con = conectar()
        google_sync.sincronizar(con, solo_id=tarea_id)
        con.close()
    except Exception:
        pass


def empujar_google_hilo(tarea_id):
    hilo = threading.Thread(target=empujar_google, args=(tarea_id,))
    hilo.daemon = True
    hilo.start()


def borrar_tarea_de_google(tarea):
    if not tarea or not google_sync.estado()["conectado"]:
        return
    try:
        if tarea.get("gcal_id"):
            google_sync.borrar_evento(tarea["gcal_id"])
        if tarea.get("gtask_id"):
            google_sync.borrar_tarea_google(tarea["gtask_id"])
    except Exception:
        pass


def pagina_google(titulo, detalle, bien=True):
    color = "#34d399" if bien else "#f87171"
    simbolo = "&#10003;" if bien else "&#10007;"
    return ("<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Habitos - Google</title></head>"
            "<body style='background:#0b0e14;color:#e6ebf5;font-family:Segoe UI,sans-serif;"
            "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0'>"
            "<div style='text-align:center;max-width:430px;padding:32px;background:#131822;"
            "border:1px solid #242c3a;border-radius:16px'>"
            "<div style='font-size:40px;color:" + color + "'>" + simbolo + "</div>"
            "<h2 style='margin:10px 0 8px;font-size:20px'>" + titulo + "</h2>"
            "<p style='color:#8b97ad;font-size:13.5px;line-height:1.55'>" + detalle + "</p>"
            "<p style='color:#5c6880;font-size:12px;margin-top:16px'>"
            "Ya puedes cerrar esta pestaña y volver a Habitos.</p>"
            "</div></body></html>")


class ServidorLocal(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *argumentos):
        print("[%s] %s" % (self.address_string(), formato % argumentos), flush=True)

    # -- respuestas

    def _json(self, codigo, objeto):
        cuerpo = json.dumps(objeto, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cookie_sesion(self):
        cabecera = self.headers.get("Cookie") or ""
        encontrado = re.search(r"sesion=([A-Za-z0-9_\-]+)", cabecera)
        return encontrado.group(1) if encontrado else ""

    def _autorizado(self):
        if not hay_clave():
            return True
        token = self._cookie_sesion()
        return bool(token) and sesion_valida(token)

    def _html(self, codigo, texto):
        cuerpo = texto.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _archivo(self, ruta):
        try:
            with open(ruta, "rb") as archivo:
                cuerpo = archivo.read()
        except OSError:
            self._json(404, {"error": "No encontrado"})
            return
        extension = os.path.splitext(ruta)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(extension, "application/octet-stream"))
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cuerpo(self):
        largo = a_entero(self.headers.get("Content-Length"), 0)
        if not largo:
            return {}
        try:
            return json.loads(self.rfile.read(largo).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # -- rutas

    def do_GET(self):
        partes = urlparse(self.path)
        ruta = partes.path
        argumentos = parse_qs(partes.query)

        if ruta in ("/", "/index.html"):
            if not self._autorizado():
                self._archivo(os.path.join(RUTA_WEB, "login.html"))
                return
            self._archivo(os.path.join(RUTA_WEB, "index.html"))
            return

        if ruta == "/login":
            self._archivo(os.path.join(RUTA_WEB, "login.html"))
            return

        if ruta.startswith("/api/") and not self._autorizado():
            self._json(401, {"error": "Necesitas la clave de acceso"})
            return

        if ruta == "/oauth2callback":
            codigo = (argumentos.get("code") or [""])[0]
            estado_o = (argumentos.get("state") or [""])[0]
            fallo = (argumentos.get("error") or [""])[0]
            if fallo:
                self._html(200, pagina_google(
                    "No se autorizo",
                    "Google respondio: " + fallo +
                    ". Si fue un rechazo tuyo, vuelve a intentarlo desde la app.", False))
            elif not codigo:
                self._html(200, pagina_google(
                    "Falto el codigo", "Google no mando el codigo de autorizacion.", False))
            else:
                try:
                    token = google_sync.completar_autorizacion(codigo, estado_o)
                    self._html(200, pagina_google(
                        "Google conectado",
                        "Cuenta: " + (token.get("email") or "tu cuenta") +
                        ". Ya puedes sincronizar desde la app."))
                except Exception as error:
                    self._html(200, pagina_google("No se pudo conectar", str(error), False))
            return

        if ruta == "/api/google":
            self._json(200, estado_google())
            return

        if ruta == "/api/ajustes":
            self._json(200, estado_servidor())
            return
        if ruta in ("/app.js", "/app.css", "/favicon.ico"):
            self._archivo(os.path.join(RUTA_WEB, ruta.lstrip("/")))
            return
        if ruta.startswith("/assets/"):
            limpia = os.path.normpath(ruta.lstrip("/"))
            self._archivo(os.path.join(RUTA_BASE, limpia))
            return

        if ruta == "/api/resumen":
            self._json(200, resumen())
            return
        if ruta == "/api/tareas":
            self._json(200, {"tareas": listar_tareas(argumentos)})
            return
        if ruta == "/api/sesiones":
            self._json(200, {"sesiones": listar_sesiones(argumentos)})
            return
        if ruta == "/api/metricas":
            periodo = (argumentos.get("periodo") or ["semana"])[0]
            if periodo not in ("semana", "mes"):
                periodo = "semana"
            self._json(200, metricas(periodo))
            return

        if ruta == "/api/moodle":
            con = conectar()
            estado_nube = moodle.ultimo_estado(con)
            con.close()
            estado_nube.update(moodle.estado_configuracion())
            self._json(200, estado_nube)
            return

        if ruta == "/api/apuntes":
            self._json(200, {"apuntes": listar_apuntes(argumentos)})
            return

        if ruta == "/api/racha":
            self._json(200, racha_detallada())
            return

        if ruta == "/api/telegram":
            self._json(200, estado_telegram())
            return

        if ruta == "/api/recordatorios":
            info = cargar_recordatorios()
            info["telegram"] = bool(cargar_telegram().get("chat_id"))
            self._json(200, info)
            return

        coincidencia = re.match(r"^/api/tareas/(\d+)$", ruta)
        if coincidencia:
            tarea = obtener_tarea(int(coincidencia.group(1)))
            if tarea is None:
                self._json(404, {"error": "Esa tarea no existe"})
            else:
                self._json(200, tarea)
            return

        self._json(404, {"error": "Ruta no encontrada"})

    def do_POST(self):
        ruta = urlparse(self.path).path
        datos = self._cuerpo()

        if ruta == "/api/login":
            if not hay_clave():
                self._json(200, {"ok": True, "sin_clave": True})
                return
            if verificar_clave((datos.get("clave") or "").strip()):
                token = crear_sesion()
                cuerpo = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Set-Cookie",
                                 "sesion=" + token + "; Path=/; HttpOnly; SameSite=Lax; Max-Age="
                                 + str(DIAS_SESION * 86400))
                self.end_headers()
                self.wfile.write(cuerpo)
            else:
                time.sleep(0.7)
                self._json(401, {"error": "Clave incorrecta"})
            return

        if not self._autorizado():
            self._json(401, {"error": "Necesitas la clave de acceso"})
            return

        if ruta == "/api/logout":
            token = self._cookie_sesion()
            if token:
                cerrar_sesion(token)
            cuerpo = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Set-Cookie", "sesion=; Path=/; HttpOnly; Max-Age=0")
            self.end_headers()
            self.wfile.write(cuerpo)
            return

        if ruta == "/api/ajustes":
            if "clave" in datos:
                nueva = (datos.get("clave") or "").strip()
                if nueva == "":
                    borrar_ajuste("clave_hash")
                else:
                    if len(nueva) < 4:
                        self._json(400, {"error": "La clave necesita al menos 4 caracteres"})
                        return
                    escribir_ajuste("clave_hash", calcular_hash(nueva))
            host = datos.get("host")
            if host is not None:
                if host not in ("127.0.0.1", "0.0.0.0"):
                    self._json(400, {"error": "Host invalido"})
                    return
                if host == "0.0.0.0" and not hay_clave():
                    self._json(400, {"error": "Pon primero una clave de acceso: abrir "
                                              "a la red sin clave deja tus tareas a la vista"})
                    return
                escribir_ajuste("host", host)
            puerto = datos.get("puerto")
            if puerto is not None:
                numero = a_entero(puerto, 0)
                if numero < 1024 or numero > 65535:
                    self._json(400, {"error": "El puerto va entre 1024 y 65535"})
                    return
                escribir_ajuste("puerto", str(numero))
            info = estado_servidor()
            info["reiniciar"] = True
            self._json(200, info)
            return

        if ruta == "/api/tareas":
            parecida = buscar_parecida((datos.get("titulo") or "").strip())
            if parecida is not None and not datos.get("forzar"):
                self._json(200, {"duplicado": True, "tarea": parecida})
                return
            tarea = crear_tarea(datos)
            if tarea is None:
                self._json(400, {"error": "La tarea necesita un titulo"})
            else:
                empujar_google_hilo(tarea["id"])
                self._json(201, tarea)
            return

        if ruta == "/api/apuntes":
            apunte = crear_apunte(datos)
            if apunte is None:
                self._json(400, {"error": "La nota esta vacia"})
            else:
                self._json(201, apunte)
            return

        if ruta == "/api/telegram/config":
            token = (datos.get("token") or "").strip()
            if not token:
                self._json(400, {"error": "Falta el token del bot"})
                return
            prueba = telegram.probar(token)
            if not prueba.get("ok"):
                self._json(400, {"error": "Telegram rechazo el token: %s"
                                          % prueba.get("error")})
                return
            config = cargar_telegram()
            config["token"] = token
            config["bot"] = prueba.get("bot")
            guardar_telegram(config)
            self._json(200, estado_telegram())
            return

        if ruta == "/api/telegram/desvincular":
            config = cargar_telegram()
            config.pop("chat_id", None)
            guardar_telegram(config)
            self._json(200, estado_telegram())
            return

        if ruta == "/api/google/cliente":
            try:
                resultado = google_sync.instalar_cliente((datos.get("ruta") or "").strip())
            except Exception as error:
                self._json(400, {"error": str(error)})
                return
            self._json(200, {"ok": True, "client_id": resultado["client_id"]})
            return

        if ruta == "/api/google/autorizar":
            puerto = self.server.server_address[1]
            try:
                respuesta = google_sync.iniciar_autorizacion(
                    "http://127.0.0.1:%d/oauth2callback" % puerto)
            except Exception as error:
                self._json(400, {"error": str(error)})
                return
            self._json(200, respuesta)
            return

        if ruta == "/api/google/sync":
            self._json(200, sincronizar_google())
            return

        if ruta == "/api/google/desconectar":
            google_sync.borrar_token()
            self._json(200, estado_google())
            return

        if ruta == "/api/recordatorios":
            self._json(200, guardar_recordatorios(datos))
            return

        if ruta == "/api/recordatorios/probar":
            self._json(200, enviar_recordatorio())
            return
        if ruta == "/api/sesiones":
            sesion = registrar_sesion(datos)
            if sesion is None:
                self._json(400, {"error": "Los minutos deben ser mayores que cero"})
            else:
                self._json(201, sesion)
            return
        if ruta == "/api/estimar":
            self._json(200, estimar_tarea(datos))
            return

        if ruta == "/api/moodle/config":
            base = (datos.get("base") or "").strip()
            ruta_login = (datos.get("ruta_login") or "").strip()
            usuario = (datos.get("usuario") or "").strip()
            clave = (datos.get("clave") or "").strip()
            campus = (datos.get("campus") or "").strip()
            if not base:
                self._json(400, {"error": "Falta la direccion de tu Moodle "
                                          "(por ejemplo https://moodle.tuinstitucion.edu)"})
                return
            if not usuario or not clave:
                self._json(400, {"error": "Faltan el usuario y la contrasena"})
                return
            try:
                moodle.guardar_configuracion(base, usuario, clave, ruta_login, campus)
            except Exception as error:
                self._json(400, {"error": str(error)})
                return
            self._json(200, sincronizar_moodle())
            return

        if ruta == "/api/moodle/sync":
            self._json(200, sincronizar_moodle(bool(datos.get("incluir_vencidas"))))
            return

        coincidencia = re.match(r"^/api/tareas/(\d+)/estado$", ruta)
        if coincidencia:
            tarea = actualizar_tarea(int(coincidencia.group(1)), datos)
            if tarea is None:
                self._json(404, {"error": "Esa tarea no existe"})
            else:
                empujar_google_hilo(tarea["id"])
                self._json(200, tarea)
            return

        self._json(404, {"error": "Ruta no encontrada"})

    def do_PUT(self):
        ruta = urlparse(self.path).path
        datos = self._cuerpo()
        if not self._autorizado():
            self._json(401, {"error": "Necesitas la clave de acceso"})
            return
        apunte = re.match(r"^/api/apuntes/(\d+)$", ruta)
        if apunte:
            actualizado = actualizar_apunte(int(apunte.group(1)), datos)
            if actualizado is None:
                self._json(404, {"error": "Esa nota no existe"})
            else:
                self._json(200, actualizado)
            return
        coincidencia = re.match(r"^/api/tareas/(\d+)$", ruta)
        if coincidencia:
            tarea = actualizar_tarea(int(coincidencia.group(1)), datos)
            if tarea is None:
                self._json(404, {"error": "Esa tarea no existe"})
            else:
                empujar_google_hilo(tarea["id"])
                self._json(200, tarea)
            return
        self._json(404, {"error": "Ruta no encontrada"})

    def do_DELETE(self):
        ruta = urlparse(self.path).path
        if not self._autorizado():
            self._json(401, {"error": "Necesitas la clave de acceso"})
            return
        apunte = re.match(r"^/api/apuntes/(\d+)$", ruta)
        if apunte:
            if borrar_apunte(int(apunte.group(1))):
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "Esa nota no existe"})
            return
        coincidencia = re.match(r"^/api/tareas/(\d+)$", ruta)
        if coincidencia:
            identificador = int(coincidencia.group(1))
            borrar_tarea_de_google(obtener_tarea(identificador))
            if borrar_tarea(identificador):
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "Esa tarea no existe"})
            return
        self._json(404, {"error": "Ruta no encontrada"})


def main():
    iniciar_db()

    hilo_nube = threading.Thread(target=bucle_moodle)
    hilo_nube.daemon = True
    hilo_nube.start()

    hilo_bot = threading.Thread(target=bucle_telegram)
    hilo_bot.daemon = True
    hilo_bot.start()

    hilo_recordatorios = threading.Thread(target=bucle_recordatorios)
    hilo_recordatorios.daemon = True
    hilo_recordatorios.start()

    servidor = None
    host_argumento, puerto_argumento = leer_argumentos()
    host = host_argumento or host_servidor()
    puerto_base = puerto_argumento or puerto_servidor()
    for puerto in range(puerto_base, puerto_base + 6):
        try:
            servidor = ServidorLocal((host, puerto), Handler)
            break
        except OSError:
            continue
    if servidor is None:
        print("No hay puerto libre entre %d y %d." % (puerto_base, puerto_base + 5))
        input("Enter para salir...")
        return

    url = "http://127.0.0.1:%d" % puerto
    print("=" * 56)
    print(" TodoUtesa - servidor")
    print(" " + url)
    if host != "127.0.0.1":
        direccion = ip_local()
        if direccion:
            print(" Red local: http://" + direccion + ":" + str(puerto))
        if not hay_clave():
            print(" AVISO: abierto a la red SIN clave de acceso.")
            print("        pon una en el menu Servidor de la app.")
    print(" Cierra esta ventana para detener.")
    print("=" * 56, flush=True)
    if not os.environ.get("NO_BROWSER") and host == "127.0.0.1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()


# ------------------------------------------------------- acceso y ajustes

def leer_ajuste(clave, por_defecto=""):
    try:
        con = conectar()
        fila = con.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
        con.close()
    except Exception:
        return por_defecto
    if fila is None or fila["valor"] is None:
        return por_defecto
    return fila["valor"]


def escribir_ajuste(clave, valor):
    con = conectar()
    con.execute("INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
                " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor))
    con.commit()
    con.close()


def borrar_ajuste(clave):
    con = conectar()
    con.execute("DELETE FROM ajustes WHERE clave = ?", (clave,))
    con.commit()
    con.close()


def hay_clave():
    return bool(leer_ajuste("clave_hash", ""))


def calcular_hash(clave):
    sal = os.urandom(16).hex()
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"),
                                   bytes.fromhex(sal), 200000).hex()
    return sal + ":" + derivada


def verificar_clave(clave):
    guardado = leer_ajuste("clave_hash", "")
    if not guardado:
        return True
    partes = guardado.split(":", 1)
    if len(partes) != 2:
        return False
    try:
        calculada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"),
                                        bytes.fromhex(partes[0]), 200000).hex()
    except ValueError:
        return False
    return hmac.compare_digest(calculada, partes[1])


RUTA_SESIONES = os.path.join(RUTA_DATOS, "sesiones.json")
DIAS_SESION = 30


def cargar_sesiones():
    try:
        with open(RUTA_SESIONES, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, ValueError):
        return {}


def guardar_sesiones(datos):
    if not os.path.isdir(RUTA_DATOS):
        os.makedirs(RUTA_DATOS)
    with open(RUTA_SESIONES, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo)


def crear_sesion():
    ahora = time.time()
    vigentes = {}
    for token, expira in cargar_sesiones().items():
        if expira > ahora:
            vigentes[token] = expira
    nuevo = secrets.token_urlsafe(32)
    vigentes[nuevo] = ahora + DIAS_SESION * 86400
    guardar_sesiones(vigentes)
    return nuevo


def sesion_valida(token):
    return cargar_sesiones().get(token, 0) > time.time()


def cerrar_sesion(token):
    sesiones = cargar_sesiones()
    if token in sesiones:
        del sesiones[token]
        guardar_sesiones(sesiones)


def host_servidor():
    host = leer_ajuste("host", "127.0.0.1")
    if host not in ("127.0.0.1", "0.0.0.0"):
        host = "127.0.0.1"
    return host


def puerto_servidor():
    return a_entero(leer_ajuste("puerto", ""), PUERTO_INICIAL)


def ip_local():
    try:
        prueba = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        prueba.connect(("8.8.8.8", 80))
        direccion = prueba.getsockname()[0]
        prueba.close()
        return direccion
    except Exception:
        return ""


def imprimir_ayuda():
    print("TodoUtesa")
    print("")
    print("  python servidor.py                 solo este equipo (127.0.0.1)")
    print("  python servidor.py --red           toda la red local (0.0.0.0)")
    print("  python servidor.py --local         volver a solo este equipo")
    print("  python servidor.py --host 0.0.0.0  host explicito")
    print("  python servidor.py --puerto 9000   cambiar el puerto")
    print("  python diagnostico.py              por que no me entra el sitio")
    print("  python servidor.py --ayuda         esta ayuda")


def leer_argumentos():
    host = ""
    puerto = 0
    lista = sys.argv[1:]
    i = 0
    while i < len(lista):
        argumento = lista[i]
        if argumento in ("--red", "--lan"):
            host = "0.0.0.0"
        elif argumento in ("--local", "--solo-local"):
            host = "127.0.0.1"
        elif argumento == "--host" and i + 1 < len(lista):
            i = i + 1
            host = lista[i]
        elif argumento == "--puerto" and i + 1 < len(lista):
            i = i + 1
            puerto = a_entero(lista[i], 0)
        elif argumento in ("-h", "--ayuda", "--help"):
            imprimir_ayuda()
            sys.exit(0)
        i = i + 1

    if host and host not in ("127.0.0.1", "0.0.0.0"):
        print("Host invalido, uso 127.0.0.1")
        host = "127.0.0.1"
    return host, puerto


def estado_servidor():
    host = host_servidor()
    puerto = puerto_servidor()
    direccion = ip_local()
    return {
        "clave": hay_clave(),
        "host": host,
        "puerto": puerto,
        "ip": direccion,
        "red_abierta": host != "127.0.0.1",
        "url_red": ("http://" + direccion + ":" + str(puerto)) if direccion else "",
    }


# ---------------------------------------------------------------- tareas


if __name__ == "__main__":
    main()
