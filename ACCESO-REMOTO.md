# Acceso desde otros equipos (dentro y fuera de tu red)

Hay **dos problemas distintos** y se arreglan distinto:

| Quiero entrar desde... | Que falta | Solucion |
|---|---|---|
| otra PC o laptop en **la misma wifi** | que la app escuche en toda la red | `python servidor.py --red` |
| **cualquier lugar del mundo** | un tunel (tu casa no tiene IP publica) | Tailscale o Cloudflare |

Primero corre el diagnostico, que te dice exactamente cual es tu caso:

```bash
python diagnostico.py
```

---

## Paso 0 (obligatorio antes de abrir nada): pon una clave

En la app: menu lateral -> **Servidor** -> escribe una clave -> Guardar.

Sin clave, cualquiera en la misma wifi (un ciber, la universidad, un hotel) puede
entrar a tus tareas, tus notas y tus credenciales. La app **no** te deja abrir a
la red sin clave desde la interfaz; por comando si te deja, pero te avisa.

---

## 1. Misma red wifi

```bash
cd TodoUtesa
python servidor.py --red
```

La consola te muestra:

```
 TodoUtesa - servidor
 http://127.0.0.1:8630
 Red local: http://192.168.1.50:8630
```

Desde el otro equipo abres esa direccion de **Red local**.

Para volver a solo el equipo donde corre:

```bash
python servidor.py            # o --local
```

### Si sigue sin entrar

| Revisa | Como |
|---|---|
| Estas en la misma red | el otro equipo no puede estar en otra wifi ni en datos moviles |
| Wifi de invitados | muchos routers aislan clientes entre si: usa la red normal |
| La IP cambio | el router da IPs dinamicas: vuelve a mirar la consola |
| Firewall | Windows: permite Python en redes privadas. Linux: `sudo ufw allow 8630/tcp` |
| La app se cerro | mira la consola: si hay un error, ahi esta |

---

## 2. Desde cualquier lugar: Tailscale (recomendado)

Crea una red privada entre tus equipos. **No expone nada a internet**, es gratis
para uso personal y no necesitas dominio ni abrir puertos.

1. Instala Tailscale en el equipo que corre la app: https://tailscale.com/download
2. Inicia sesion (Google, GitHub o el que uses).
3. Anota su IP de Tailscale: empieza con **100.**
4. Instala Tailscale en el otro equipo y entra **con la misma cuenta**.
5. Arranca la app:

```bash
python servidor.py --red
```

6. Entra desde el otro equipo: `http://100.x.y.z:8630`

Funciona igual desde el trabajo, la universidad o datos moviles, porque los dos
equipos estan en tu red privada. Si no estas en Tailscale, la app no existe para
el resto de internet.

---

## 3. Desde cualquier lugar: Cloudflare Tunnel (URL publica)

Si quieres abrirla **sin instalar nada** en el otro equipo (una PC prestada, el
navegador de la universidad), un tunel te da una URL `https://`.

```bash
# Linux
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://127.0.0.1:8630

# Windows (PowerShell)
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://127.0.0.1:8630

# macOS
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8630
```

Te imprime algo asi:

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at:                                          |
|  https://palabra-random-otra-palabra.trycloudflare.com                                     |
+--------------------------------------------------------------------------------------------+
```

Esa URL funciona desde cualquier parte del mundo, con HTTPS.

**Ojo:**
- La URL **cambia cada vez** que reinicias el tunel. Para una fija hace falta un
  dominio propio y un tunel con nombre (documentado en Cloudflare).
- **Pon la clave en la app antes**: esa URL es publica, la unica defensa es tu clave.
- La app y el tunel tienen que estar corriendo en el mismo equipo.

---

## 4. Si quieres que este siempre arriba

Una PC de escritorio se apaga, se suspende o se queda sin luz. Si quieres el
sitio disponible 24/7, lo natural es un VPS (Oracle Cloud tiene una capa gratis
permanente). Instrucciones en [INSTALACION.md](INSTALACION.md), seccion 6.

Puedes correrlo en la PC **y** en el VPS con la misma base copiada, pero no los
dejes los dos escribiendo a la vez o se desincronizan.

---

## Resumen en 4 lineas

```bash
python servidor.py --red          # abre a la red local
python diagnostico.py             # si algo no entra, esto te dice que es
# desde cualquier lugar: Tailscale (privado) o cloudflared (URL publica)
# siempre con clave de acceso puesta
```
