# -*- coding: utf-8 -*-
"""Sincronizacion con la nube de UTSA (Moodle) para traer tareas pendientes.

Solo biblioteca estandar. Credenciales en datos/moodle.json:
    {"campus": "utsan", "usuario": "...", "clave": "..."}

Cruza cuatro fuentes por curso para no dejar nada fuera:
  1. /course/view.php?id=CID   -> lista completa de actividades + estado de
                                  finalizacion (Hecho / Pendiente)
  2. /mod/assign/index.php?id= -> tareas con fecha de entrega y estado de la
                                  entrega (Enviado para calificar / No entregado)
  3. /mod/quiz/index.php?id=   -> cuestionarios con fecha de cierre y nota
                                  (nota vacia = sin intento = pendiente)
  4. /calendar/view.php?view=month -> fechas de cierre de hvp / scorm / foros

Regla: se importa como pendiente todo lo que NO este entregado/completado,
sin importar si la fecha ya paso (las atrasadas tambien entran). Si algo ya
estaba en la app y ahora aparece entregado, se marca como hecho.
"""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import unicodedata
import http.cookiejar
from datetime import date
from difflib import SequenceMatcher

RUTA_BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_DATOS = os.path.join(RUTA_BASE, "datos")
RUTA_CONFIG = os.path.join(RUTA_DATOS, "moodle.json")
URL_BASE = "https://nube.utesa.edu"

NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

CAMPUS = {
    "utsan": "Santiago",
    "utsdg": "Santo Domingo",
    "utsdo": "Santo Domingo Oriental",
    "utdjb": "Dajabon",
    "utghd": "Gaspar Hernandez",
    "utmao": "Mao",
    "utppt": "Puerto Plata",
    "utmoc": "Moca",
    "utgrs": "Escuela Graduados Santiago",
    "utgrd": "Escuela Graduados Santo Domingo",
}

# tipos de actividad que pueden generar una tarea
TIPOS_CON_TAREA = [
    "assign", "quiz", "hvp", "scorm", "forum", "workshop", "lesson",
    "choice", "feedback", "data", "imscp", "bigbluebutton", "attendance",
    "turnitintooltwo", "geogebra", "customcert", "oublog", "wiki", "glossary",
]

# tipos que son solo material, nunca una tarea
TIPOS_MATERIAL = ["resource", "url", "page", "folder", "book", "label", "file"]

ESTIMADO_POR_TIPO = {
    "assign": 90,
    "quiz": 30,
    "hvp": 45,
    "scorm": 40,
    "forum": 25,
    "workshop": 90,
    "lesson": 40,
    "choice": 10,
    "feedback": 15,
    "wiki": 60,
}

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

PATRON_FECHA = re.compile(
    r"(\d{1,2})\s+de\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+de\s+(\d{4})(?:,?\s*(\d{1,2}):(\d{2}))?")

PRIORIDAD_EVENTO = {"close": 3, "due": 3, "graded": 2}


class ErrorMoodle(Exception):
    pass


# ---------------------------------------------------------------- utilidades

def normalizar_para_comparar(texto):
    limpio = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^a-zA-Z0-9 ]", " ", limpio).lower()
    vacias = ("del", "las", "los", "con", "para", "por", "una", "que", "the", "and")
    return [p for p in limpio.split()
            if (len(p) > 2 or p.isdigit()) and p not in vacias]


def similitud(titulo_a, titulo_b):
    """0.0 a 1.0. Mezcla comparacion de texto y solapamiento de palabras."""
    palabras_a = normalizar_para_comparar(titulo_a)
    palabras_b = normalizar_para_comparar(titulo_b)
    if not palabras_a or not palabras_b:
        return 0.0
    texto_a = " ".join(palabras_a)
    texto_b = " ".join(palabras_b)
    base = SequenceMatcher(None, texto_a, texto_b).ratio()
    conjunto_a = set(palabras_a)
    conjunto_b = set(palabras_b)
    union = conjunto_a | conjunto_b
    solape = len(conjunto_a & conjunto_b) / float(len(union)) if union else 0.0
    return base if base > solape else solape


def limpiar_texto(fragmento):
    texto = re.sub(r"<[^>]+>", " ", fragmento or "")
    texto = html.unescape(texto).replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def parsear_fecha(texto):
    """'domingo, 1 de noviembre de 2026, 23:59' -> ('2026-11-01', '23:59')"""
    encontrado = PATRON_FECHA.search(texto or "")
    if not encontrado:
        return None, None
    mes = MESES_ES.get(encontrado.group(2).lower())
    if not mes:
        return None, None
    anio = int(encontrado.group(3))
    dia = int(encontrado.group(1))
    if dia < 1 or dia > 31:
        return None, None
    fecha = "%04d-%02d-%02d" % (anio, mes, dia)
    hora = None
    if encontrado.group(4):
        hora = "%02d:%s" % (int(encontrado.group(4)), encontrado.group(5))
    return fecha, hora


def limpiar_nombre_curso(texto):
    limpio = html.unescape(texto or "").replace("\xa0", " ")
    limpio = re.sub(r"\s+", " ", limpio).strip()
    for corte in [" (Presencial", " (Virtual", " (Semipresencial", "_UTSAN", " : ", " =>"]:
        if corte in limpio:
            limpio = limpio.split(corte)[0]
            break
    return limpio.strip(" -_")[:60]


def limpiar_titulo(texto):
    """Quita las etiquetas de Moodle y los rangos de semana del nombre."""
    limpio = html.unescape(texto or "").replace("\xa0", " ")
    limpio = re.sub(r"\s+", " ", limpio).strip()

    for prefijo in ["vencimiento de ", "se cierra ", "se abre ", "entrega de ", "cierre de "]:
        if limpio.lower().startswith(prefijo):
            limpio = limpio[len(prefijo):]
            break

    for sufijo in [" deberia ser completado", " debe ser completado",
                   " debería ser completado", " esta por vencer", " está por vencer"]:
        if limpio.lower().endswith(sufijo):
            limpio = limpio[: len(limpio) - len(sufijo)]
            break

    # 'Tarea No. 1 14 de septiembre - 20 de septiembre' -> 'Tarea No. 1'
    limpio = re.sub(r"\s+\d{1,2}\s+de\s+[a-zA-Záéíóú]+\s*-\s*\d{1,2}\s+de\s+[a-zA-Záéíóú]+$",
                    "", limpio)
    limpio = limpio.strip(" -:")

    if not limpio:
        return "Actividad de la nube"
    return limpio[0].upper() + limpio[1:]


def estimado_de(tipo, titulo):
    minutos = ESTIMADO_POR_TIPO.get(tipo, 45)
    texto = (titulo or "").lower()
    if "examen" in texto or "parcial" in texto or "final" in texto:
        minutos = 120
    elif "proyecto" in texto or "investigacion" in texto or "investigación" in texto:
        minutos = 120
    elif "foro" in texto:
        minutos = 25
    return minutos


# -------------------------------------------------------------------- config

def cargar_configuracion():
    if not os.path.isfile(RUTA_CONFIG):
        return None
    try:
        with open(RUTA_CONFIG, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, ValueError):
        return None
    if not datos.get("usuario") or not datos.get("clave"):
        return None
    if not datos.get("campus"):
        datos["campus"] = "utsan"
    return datos


def guardar_configuracion(campus, usuario, clave):
    if not os.path.isdir(RUTA_DATOS):
        os.makedirs(RUTA_DATOS)
    datos = {
        "campus": (campus or "utsan").strip(),
        "usuario": (usuario or "").strip(),
        "clave": (clave or "").strip(),
    }
    with open(RUTA_CONFIG, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    try:
        os.chmod(RUTA_CONFIG, 0o600)
    except OSError:
        pass
    return datos


def estado_configuracion():
    config = cargar_configuracion()
    if not config:
        return {"configurado": False}
    return {
        "configurado": True,
        "campus": config.get("campus"),
        "campus_nombre": CAMPUS.get(config.get("campus"), config.get("campus")),
        "usuario": config.get("usuario"),
    }


# ------------------------------------------------------------------- sesion

class SesionMoodle(object):
    def __init__(self, config):
        self.config = config
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.op.addheaders = [
            ("User-Agent", NAVEGADOR),
            ("Accept-Language", "es-DO,es;q=0.9"),
            ("Accept", "text/html,application/xhtml+xml"),
        ]

    def abrir(self, ruta):
        url = ruta if ruta.startswith("http") else URL_BASE + ruta
        try:
            respuesta = self.op.open(url, timeout=60)
            return respuesta.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            raise ErrorMoodle("La nube respondio con error %s" % error.code)
        except Exception as error:
            raise ErrorMoodle("No se pudo conectar con la nube: %s" % error)

    def entrar(self):
        pagina = self.abrir("/local/entrada/")
        encontrado = re.search(r'name="logintoken"\s+value="([^"]+)"', pagina)
        if not encontrado:
            raise ErrorMoodle("No encontre el formulario de entrada. La nube cambio de pagina.")

        cuerpo = urllib.parse.urlencode({
            "campus": self.config.get("campus", "utsan"),
            "username": self.config["usuario"],
            "password": self.config["clave"],
            "logintoken": encontrado.group(1),
        }).encode("utf-8")

        try:
            respuesta = self.op.open(URL_BASE + "/local/entrada/index.php", cuerpo, timeout=60)
            pagina = respuesta.read().decode("utf-8", "replace")
        except Exception as error:
            raise ErrorMoodle("No se pudo iniciar sesion: %s" % error)

        if "/login/logout.php" not in pagina:
            raise ErrorMoodle("La nube rechazo la matricula o la contrasena.")

    # ---------------------------------------------------------- cursos

    def cursos(self):
        """courseid -> nombre del curso. (id, nombre, nombre visible en breadcrumb)"""
        mapa = {}
        pagina = self.abrir("/course/index.php?mycourses=1")
        for encontrado in re.finditer(
                r'<a[^>]+href="[^"]*?/course/view\.php\?id=(\d+)"([^>]*)>(.*?)</a>',
                pagina, re.S):
            identificador = encontrado.group(1)
            atributo = re.search(r'title="([^"]*)"', encontrado.group(2))
            if atributo:
                nombre = limpiar_nombre_curso(html.unescape(atributo.group(1)))
            else:
                nombre = limpiar_nombre_curso(html.unescape(limpiar_texto(encontrado.group(3))))
            if len(nombre) < 3:
                continue
            if identificador not in mapa or len(nombre) > len(mapa[identificador]):
                mapa[identificador] = nombre
        return mapa

    # ------------------------------------------------------ actividades

    def actividades_del_curso(self, curso_id, nombre_curso):
        """Todas las actividades del curso con su estado de finalizacion."""
        pagina = self.abrir("/course/view.php?id=" + curso_id)
        bloques = re.split(r'(?=<li[^>]*class="[^"]*\bactivity\b)', pagina)
        actividades = {}

        for bloque in bloques:
            enlace = re.search(r'/mod/([a-z]+)/view\.php\?id=(\d+)', bloque)
            if not enlace:
                continue
            tipo = enlace.group(1)
            cmid = enlace.group(2)
            if cmid in actividades:
                continue

            # quitar la etiqueta oculta de Moodle ("Tarea", "Cuestionario", "URL"...)
            nombre = ""
            bloque_limpio = re.sub(r'<span class="accesshide[^"]*">.*?</span>', " ", bloque, flags=re.S)
            instancia = re.search(r'<span class="instancename">(.*?)</span>', bloque_limpio, re.S)
            if instancia:
                nombre = limpiar_texto(instancia.group(1))
            if not nombre:
                continue

            seguimiento = 'data-region="completion-info"' in bloque
            estado = None
            if seguimiento:
                if "Pendiente" in bloque:
                    estado = "pendiente"
                elif "Hecho" in bloque:
                    estado = "hecho"

            actividades[cmid] = {
                "cmid": cmid,
                "tipo": tipo,
                "titulo": limpiar_titulo(nombre),
                "curso": nombre_curso,
                "seguimiento": seguimiento,
                "completado": estado,
                "fecha": None,
                "hora": None,
                "entregado": None,
            }
        return actividades

    def _filas_tabla(self, ruta):
        """Filas de la primera tabla como diccionarios (cabecera -> valor)."""
        pagina = self.abrir(ruta)
        tablas = re.findall(r"<table.*?</table>", pagina, re.S)
        if not tablas:
            return []

        cabecera = []
        filas = []
        for fila in re.findall(r"<tr[^>]*>.*?</tr>", tablas[0], re.S):
            celdas = re.findall(r"<t[dh]([^>]*)>(.*?)</t[dh]>", fila, re.S)
            if not celdas:
                continue

            valores = []
            for atributos, contenido in celdas:
                # Moodle 4 guarda el valor limpio en el atributo de la celda
                propio = re.search(r'data-mdl-overview-value="([^"]*)"', atributos)
                if propio:
                    valores.append(limpiar_texto(html.unescape(propio.group(1))))
                else:
                    contenido = re.sub(r'<span class="accesshide[^"]*">.*?</span>', " ",
                                      contenido, flags=re.S)
                    valores.append(limpiar_texto(contenido))

            cmid = re.search(r'data-mdl-overview-cmid="(\d+)"', fila)
            if cmid is None and not cabecera:
                cabecera = valores
                continue

            registro = {"_cmid": cmid.group(1) if cmid else "", "_href": ""}
            for posicion in range(len(valores)):
                clave = cabecera[posicion] if posicion < len(cabecera) else ("col%d" % posicion)
                registro[clave] = valores[posicion]

            enlace = re.search(r'href="([^"]*?view\.php\?id=\d+[^"]*)"', fila)
            if enlace:
                registro["_href"] = enlace.group(1)
            filas.append(registro)
        return filas

    def _cmid_de(self, fila):
        identificador = fila.get("_cmid") or ""
        if identificador:
            return identificador
        enlace = re.search(r"[?&]id=(\d+)", fila.get("_href", ""))
        if enlace:
            return enlace.group(1)
        return ""

    def tareas_del_curso(self, curso_id):
        """Tareas (mod_assign) con fecha y estado de entrega."""
        resultado = []
        for fila in self._filas_tabla("/mod/assign/index.php?id=" + curso_id):
            cmid = self._cmid_de(fila)
            if not cmid:
                continue
            nombre = ""
            fecha_texto = ""
            estado = ""
            for clave in fila:
                if clave.lower().startswith("nombre"):
                    nombre = fila[clave]
                elif "fecha de entrega" in clave.lower():
                    fecha_texto = fila[clave]
                elif "estado de la entrega" in clave.lower():
                    estado = fila[clave]
            if not nombre:
                continue
            fecha, hora = parsear_fecha(fecha_texto)
            minusculas = estado.lower()
            entregado = False
            if ("enviado" in minusculas or "entregado" in minusculas) and not minusculas.startswith("no "):
                entregado = True
            resultado.append({
                "cmid": cmid,
                "titulo": limpiar_titulo(nombre),
                "fecha": fecha,
                "hora": hora,
                "entregado": entregado,
                "detalle_entrega": estado,
            })
        return resultado

    def cuestionarios_del_curso(self, curso_id):
        """Cuestionarios con fecha de cierre y nota (vacia = sin intento)."""
        resultado = []
        for fila in self._filas_tabla("/mod/quiz/index.php?id=" + curso_id):
            cmid = self._cmid_de(fila)
            if not cmid:
                continue
            nombre = ""
            fecha_texto = ""
            nota = ""
            for clave in fila:
                minusculas = clave.lower()
                if minusculas.startswith("nombre"):
                    nombre = fila[clave]
                elif "cerrar" in minusculas or "cierra" in minusculas:
                    fecha_texto = fila[clave]
                elif "calificaci" in minusculas:
                    nota = fila[clave]
            if not nombre:
                continue
            fecha, hora = parsear_fecha(fecha_texto)
            intentado = re.search(r"\d\s*/\s*\d", nota) is not None
            resultado.append({
                "cmid": cmid,
                "titulo": limpiar_titulo(nombre),
                "fecha": fecha,
                "hora": hora,
                "entregado": intentado,
                "detalle_entrega": ("nota " + nota) if intentado else "sin intento",
            })
        return resultado

    def puede_entregar(self, url):
        """True si la actividad muestra el boton para subir/editar la entrega."""
        try:
            pagina = self.abrir(url)
        except ErrorMoodle:
            return True
        if "editsubmission" in pagina:
            return True
        texto = limpiar_texto(pagina).lower()
        if re.search(r"agregar entrega|editar entrega|enviar entrega|add submission", texto):
            return True
        return False

    def fechas_del_calendario(self, meses=4):
        """cmid -> (fecha, hora) de los eventos de vencimiento/cierre."""
        hoy = date.today()
        anio, mes = hoy.year, hoy.month
        mapa = {}

        for _ in range(meses):
            marca = time.mktime(date(anio, mes, 1).timetuple())
            try:
                pagina = self.abrir("/calendar/view.php?view=month&time=%d" % int(marca))
            except ErrorMoodle:
                pagina = ""

            for celda in re.finditer(r'<td[^>]*data-day="(\d+)"[^>]*>(.*?)</td>', pagina, re.S):
                contenido = celda.group(2)
                referencia = re.search(
                    r'data-year="(\d{4})"\s+data-month="(\d+)"\s+data-day="(\d+)"', contenido)
                if not referencia:
                    continue
                fecha = "%04d-%02d-%02d" % (int(referencia.group(1)),
                                            int(referencia.group(2)),
                                            int(referencia.group(3)))

                for elemento in re.finditer(
                        r'<li[^>]*data-region="event-item"[^>]*data-event-component="([^"]*)"'
                        r'[^>]*data-event-eventtype="([^"]*)"(.*?)</li>', contenido, re.S):
                    tipo_evento = elemento.group(2).strip()
                    if tipo_evento == "open":
                        continue
                    enlace = re.search(r'href="([^"]+)"', elemento.group(3))
                    if not enlace:
                        continue
                    cmid = re.search(r"[?&]id=(\d+)", enlace.group(1))
                    if not cmid:
                        continue
                    clave = cmid.group(1)
                    prioridad = PRIORIDAD_EVENTO.get(tipo_evento, 1)
                    anterior = mapa.get(clave)
                    if anterior is None or prioridad > anterior[2] or (
                            prioridad == anterior[2] and fecha > anterior[0]):
                        mapa[clave] = (fecha, None, prioridad)

            mes += 1
            if mes > 12:
                mes = 1
                anio += 1
            time.sleep(0.3)

        return mapa


# ------------------------------------------------------------------ recoger

def recolectar(sesion):
    """Cruza las cuatro fuentes y devuelve la lista de actividades evaluadas."""
    cursos = sesion.cursos()
    if not cursos:
        raise ErrorMoodle("No encontre tus cursos en la nube.")

    actividades = {}
    orden = []
    for curso_id in sorted(cursos):
        nombre_curso = cursos[curso_id]
        del_curso = sesion.actividades_del_curso(curso_id, nombre_curso)
        for cmid in del_curso:
            if cmid not in actividades:
                actividades[cmid] = del_curso[cmid]
                orden.append(cmid)

        for tarea in sesion.tareas_del_curso(curso_id):
            cmid = tarea["cmid"]
            if cmid not in actividades:
                actividades[cmid] = {
                    "cmid": cmid, "tipo": "assign", "titulo": tarea["titulo"],
                    "curso": nombre_curso, "seguimiento": True, "completado": None,
                    "fecha": None, "hora": None, "entregado": None,
                }
                orden.append(cmid)
            registro = actividades[cmid]
            registro["titulo"] = tarea["titulo"] or registro["titulo"]
            if tarea["fecha"]:
                registro["fecha"] = tarea["fecha"]
                registro["hora"] = tarea["hora"]
            registro["entregado"] = tarea["entregado"]
            registro["detalle_entrega"] = tarea["detalle_entrega"]

        for cuestionario in sesion.cuestionarios_del_curso(curso_id):
            cmid = cuestionario["cmid"]
            if cmid not in actividades:
                actividades[cmid] = {
                    "cmid": cmid, "tipo": "quiz", "titulo": cuestionario["titulo"],
                    "curso": nombre_curso, "seguimiento": True, "completado": None,
                    "fecha": None, "hora": None, "entregado": None,
                }
                orden.append(cmid)
            registro = actividades[cmid]
            registro["titulo"] = cuestionario["titulo"] or registro["titulo"]
            if cuestionario["fecha"]:
                registro["fecha"] = cuestionario["fecha"]
                registro["hora"] = cuestionario["hora"]
            registro["entregado"] = cuestionario["entregado"]
            registro["detalle_entrega"] = cuestionario["detalle_entrega"]

    fechas = sesion.fechas_del_calendario()
    for cmid in actividades:
        registro = actividades[cmid]
        if registro["fecha"] is None and cmid in fechas:
            registro["fecha"] = fechas[cmid][0]

    # decidir cuales son pendientes
    pendientes = []
    consultas_entrega = 0
    for cmid in orden:
        registro = actividades[cmid]
        tipo = registro["tipo"]

        if tipo in TIPOS_MATERIAL:
            continue

        if registro["entregado"] is True:
            registro["pendiente"] = False
        elif registro["entregado"] is False:
            registro["pendiente"] = True
        elif registro["completado"] == "hecho":
            registro["pendiente"] = False
        elif registro["completado"] == "pendiente":
            registro["pendiente"] = True
        elif registro["fecha"]:
            registro["pendiente"] = True
        else:
            registro["pendiente"] = False

        if tipo not in TIPOS_CON_TAREA and registro["fecha"] is None:
            continue

        # tareas donde Moodle ya no permite subir nada -> tarea perdida
        registro["perdida"] = False
        if registro["pendiente"] and tipo == "assign" and consultas_entrega < 25:
            url = URL_BASE + "/mod/assign/view.php?id=" + cmid
            if not sesion.puede_entregar(url):
                registro["perdida"] = True
            consultas_entrega += 1
            time.sleep(0.2)

        registro["clave"] = "moodle:%s:%s" % (tipo, cmid)
        pendientes.append(registro)

    return {"cursos": cursos, "actividades": pendientes, "total_actividades": len(actividades)}


# -------------------------------------------------------------- sincronizar

def enlazar_parecida(con, registro):
    """Si ya tienes una tarea escrita a mano casi igual, se enlaza a la nube."""
    filas = con.execute(
        "SELECT id, titulo FROM tareas WHERE estado = 'pendiente'"
        " AND (externa_id IS NULL OR externa_id = '')").fetchall()
    mejor = None
    mejor_puntaje = 0.0
    for fila in filas:
        puntaje = similitud(registro["titulo"], fila["titulo"])
        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor = fila["id"]
    if mejor is None or mejor_puntaje < 0.72:
        return False

    con.execute(
        "UPDATE tareas SET externa_id = ?, url = ?, origen = 'moodle',"
        " fecha = COALESCE(fecha, ?), notas = ? WHERE id = ?",
        (registro["clave"],
         URL_BASE + "/mod/%s/view.php?id=%s" % (registro["tipo"], registro["cmid"]),
         registro["fecha"], texto_notas(registro), mejor))
    return True


def sincronizar(con, meses=3, incluir_vencidas=True):
    config = cargar_configuracion()
    if not config:
        return {"ok": False, "error": "Faltan las credenciales de la nube."}

    sesion = SesionMoodle(config)
    try:
        sesion.entrar()
        datos = recolectar(sesion)
    except ErrorMoodle as error:
        return {"ok": False, "error": str(error)}

    nuevas = 0
    actualizadas = 0
    cerradas = 0
    sin_cambios = 0
    enlazadas = 0
    creadas = []

    for registro in datos["actividades"]:
        fila = con.execute(
            "SELECT id, fecha, titulo, estado, COALESCE(perdida,0) AS perdida"
            " FROM tareas WHERE externa_id = ?",
            (registro["clave"],)).fetchone()

        # ya entregado / completado y no estaba en la app -> no se crea
        if fila is None:
            if not registro["pendiente"]:
                continue
            # si ya existe una tarea tuya parecida, se enlaza en vez de duplicar
            if enlazar_parecida(con, registro):
                enlazadas += 1
                continue
            con.execute(
                "INSERT INTO tareas (titulo, notas, area, prioridad, fecha, hora,"
                " estimado_min, estado, creada, origen, externa_id, url, perdida)"
                " VALUES (?,?,?,?,?,?,?,'pendiente',?,'moodle',?,?,?)",
                (registro["titulo"],
                 texto_notas(registro),
                 (registro["curso"] or "Universidad")[:38],
                 2,
                 registro["fecha"],
                 registro["hora"],
                 estimado_de(registro["tipo"], registro["titulo"]),
                 time.strftime("%Y-%m-%d %H:%M:%S"),
                 registro["clave"],
                 URL_BASE + "/mod/%s/view.php?id=%s" % (registro["tipo"], registro["cmid"]),
                 1 if registro.get("perdida") else 0))
            nuevas += 1
            creadas.append(registro["titulo"])
            continue

        if fila["estado"] == "hecha":
            sin_cambios += 1
            continue

        # entrego o completo en la nube y aqui seguia pendiente -> se cierra
        if not registro["pendiente"]:
            con.execute(
                "UPDATE tareas SET estado = 'hecha', completada = ?, notas = ? WHERE id = ?",
                (time.strftime("%Y-%m-%d %H:%M:%S"),
                 texto_notas(registro) + "\n[cumplido en la nube]",
                 fila["id"]))
            cerradas += 1
            continue

        perdida_ahora = 1 if registro.get("perdida") else 0
        if (fila["fecha"] != registro["fecha"] or fila["titulo"] != registro["titulo"]
                or fila["perdida"] != perdida_ahora):
            con.execute(
                "UPDATE tareas SET titulo = ?, fecha = ?, hora = ?, notas = ?,"
                " estimado_min = ?, perdida = ? WHERE id = ?",
                (registro["titulo"], registro["fecha"], registro["hora"],
                 texto_notas(registro), estimado_de(registro["tipo"], registro["titulo"]),
                 perdida_ahora, fila["id"]))
            actualizadas += 1
        else:
            sin_cambios += 1

    con.commit()

    resultado = {
        "ok": True,
        "nuevas": nuevas,
        "nuevas_titulos": creadas[:8],
        "actualizadas": actualizadas,
        "cerradas": cerradas,
        "enlazadas": enlazadas,
        "sin_cambios": sin_cambios,
        "revisadas": len(datos["actividades"]),
        "cursos": len(datos["cursos"]),
        "actividades_totales": datos["total_actividades"],
        "pendientes_nube": sum(1 for a in datos["actividades"]
                               if a["pendiente"] and not a.get("perdida")),
        "perdidas_nube": sum(1 for a in datos["actividades"] if a.get("perdida")),
        "momento": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    guardar_estado(con, resultado)
    return resultado


def texto_notas(registro):
    partes = ["Nube UTSA - " + (registro["curso"] or "Universidad")]
    if registro.get("detalle_entrega"):
        partes.append("Estado: " + registro["detalle_entrega"])
    if registro.get("fecha"):
        partes.append("Vence: " + registro["fecha"] + (" " + registro["hora"] if registro.get("hora") else ""))
    partes.append(URL_BASE + "/mod/%s/view.php?id=%s" % (registro["tipo"], registro["cmid"]))
    return "\n".join(partes)


def guardar_estado(con, resultado):
    ajustes = {
        "moodle_ultima_sync": resultado.get("momento", ""),
        "moodle_ultimo_resultado": json.dumps(resultado, ensure_ascii=False),
    }
    for clave in ajustes:
        con.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
            " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, ajustes[clave]))
    con.commit()


def ultimo_estado(con):
    estado = {"configurado": bool(cargar_configuracion())}
    try:
        filas = con.execute(
            "SELECT clave, valor FROM ajustes WHERE clave LIKE 'moodle%'").fetchall()
    except Exception:
        return estado
    for fila in filas:
        if fila["clave"] == "moodle_ultima_sync":
            estado["ultima"] = fila["valor"]
        elif fila["clave"] == "moodle_ultimo_resultado":
            try:
                estado["ultimo"] = json.loads(fila["valor"])
            except ValueError:
                pass
    return estado
