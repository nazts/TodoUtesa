# -*- coding: utf-8 -*-
"""Cliente minimo de Telegram (solo stdlib) para el bot de Habitos.

Sin dependencias: usa getUpdates con long polling y sendMessage.
El bot no sabe nada de la app: recibe una funcion `atender(texto, chat_id)`
que devuelve la respuesta a enviar.
"""
import json
import time
import urllib.parse
import urllib.request

URL = "https://api.telegram.org/bot%s/%s"


def llamar(token, metodo, **parametros):
    datos = urllib.parse.urlencode(parametros).encode("utf-8")
    try:
        respuesta = urllib.request.urlopen(URL % (token, metodo), datos, timeout=45)
        return json.loads(respuesta.read().decode("utf-8", "replace"))
    except Exception as error:
        return {"ok": False, "error": str(error)}


def enviar(token, chat_id, texto, teclado=None):
    if not texto:
        return
    if len(texto) > 4000:
        texto = texto[:3990] + "..."
    parametros = {"chat_id": chat_id, "text": texto,
                  "disable_web_page_preview": "true"}
    if teclado:
        parametros["reply_markup"] = json.dumps(teclado, ensure_ascii=False)
    return llamar(token, "sendMessage", **parametros)


def probar(token):
    """Comprueba el token y devuelve el nombre del bot."""
    respuesta = llamar(token, "getMe")
    if respuesta.get("ok"):
        return {"ok": True, "bot": respuesta["result"].get("username")}
    return {"ok": False, "error": respuesta.get("description") or respuesta.get("error") or "token invalido"}


def bucle(token, atender, seguir, atender_boton=None):
    """Long polling. `seguir()` devuelve False cuando hay que reiniciar."""
    offset = 0
    fallos = 0

    while True:
        if not seguir():
            return
        respuesta = llamar(token, "getUpdates", offset=offset, timeout=25,
                           allowed_updates=json.dumps(["message", "callback_query"]))

        if not respuesta.get("ok"):
            fallos += 1
            print("[telegram] getUpdates fallo (%s): %s"
                  % (fallos, respuesta.get("description") or respuesta.get("error")), flush=True)
            time.sleep(min(60, 5 * fallos))
            continue

        fallos = 0
        for actualizacion in respuesta.get("result", []):
            offset = actualizacion.get("update_id", 0) + 1

            llamada = actualizacion.get("callback_query")
            if llamada:
                if atender_boton is None:
                    continue
                chat = ((llamada.get("message") or {}).get("chat") or {}).get("id")
                if chat is None:
                    continue
                try:
                    resultado = atender_boton(llamada.get("data") or "", chat)
                except Exception as error:
                    resultado = {"aviso": "Fallo: %s" % error}
                llamar(token, "answerCallbackQuery",
                       callback_query_id=llamada.get("id"),
                       text=(resultado.get("aviso") or "")[:190])
                if resultado.get("mensaje"):
                    enviar(token, chat, resultado["mensaje"], resultado.get("teclado"))
                continue

            mensaje = actualizacion.get("message") or {}
            texto = (mensaje.get("text") or "").strip()
            chat = (mensaje.get("chat") or {}).get("id")
            if chat is None or not texto:
                continue
            try:
                respuesta_texto = atender(texto, chat)
            except Exception as error:
                respuesta_texto = "Ups, fallo algo: %s" % error
            if respuesta_texto:
                enviar(token, chat, respuesta_texto)

        time.sleep(1)
