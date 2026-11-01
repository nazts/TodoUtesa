# Acceso desde otros dispositivos (dentro y fuera de tu red)

Hay **dos problemas distintos** y se arreglan distinto:

| Quiero entrar desde... | Que falta | Solucion |
|---|---|---|
| mi PC / tablet en **la misma wifi** | que la app escuche en toda la red | `python servidor.py --red` |
| **cualquier lugar del mundo** | un tunel (tu telefono no tiene IP publica) | Tailscale o Cloudflare |

Primero corre el diagnostico, que te dice exactamente cual es tu caso:

```bash
python diagnostico.py
```

---

## Paso 0 (obligatorio antes de abrir nada): pon una clave

En la app: menu lateral -> **Servidor** -> escribe una clave -> Guardar.

Sin clave, cualquiera en la misma wifi (un ciber, la universidad, un hotel) puede
entrar a tus tareas, tu matricula y tus notas. La app **no** te deja abrir a la
red sin clave desde la interfaz; por comando si te deja, pero te avisa.

---

## 1. Misma red wifi

```bash
cd ~/TodoUtesa
python servidor.py --red
```

La consola te muestra:

```
 TodoUtesa - servidor
 http://127.0.0.1:8630
 Red local: http://192.168.1.50:8630
```

Desde la PC abres esa direccion de **Red local**. Listo.

Para volver a solo el telefono:

```bash
python servidor.py            # o --local
```

### Si sigue sin entrar

| Revisa | Como |
|---|---|
| Estas en el mismo wifi | el telefono **no** puede estar en datos moviles |
| Wifi de invitados / AP isolation | muchos routers aíslan clientes: usa la red normal. Prueba desde otro telefono |
| La IP cambio | el router da IPs dinámicas: vuelve a mirar la consola del telefono |
| Firewall en la PC | Windows: permite Python en redes privadas |
| La app se cerro | `termux-wake-lock` y desactiva la optimizacion de bateria para Termux |

---

## 2. Desde cualquier lugar: Tailscale (recomendado)

Crea una red privada entre tus equipos. **No expone nada a internet**, es gratis
para uso personal y no necesitas dominio ni abrir puertos.

### En el telefono

1. Instala **Tailscale** desde Play Store.
2. Inicia sesion (con Google, GitHub o el que uses).
3. Activa la VPN (boton grande).
4. Anota tu IP de Tailscale: empieza con **100.** (la muestra la app arriba).

### En la PC / laptop

1. Instala Tailscale: https://tailscale.com/download
2. Inicia sesion **con la misma cuenta**.
3. Verifica que el telefono aparezca en la lista de equipos.

### Arrancar la app

```bash
python servidor.py --red
```

### Entrar

Desde la PC: `http://100.x.y.z:8630` (la IP del telefono en Tailscale).

Funciona igual desde el trabajo, la universidad o datos moviles, porque los dos
equipos estan en tu red privada. Si no estas en Tailscale, la app no existe para
el resto de internet.

---

## 3. Desde cualquier lugar: Cloudflare Tunnel (URL publica)

Si quieres abrirla **sin instalar nada** en el otro equipo (por ejemplo una PC
prestada, o el navegador de la universidad), un tunel te da una URL `https://`.

### En Termux

```bash
pkg install -y wget
cd ~
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://127.0.0.1:8630
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
- **Pon la clave en la app antes**: esa URL es publica, la unica defensa es tu
  clave.
- El telefono tiene que estar encendido y Termux vivo.

### Alternativa: ngrok

Igual de simple, tambien cambia la URL en el plan gratis:

```bash
pkg install -y wget
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz
tar xzf ngrok-v3-stable-linux-arm64.tgz
./ngrok config add-authtoken TU_TOKEN
./ngrok http 8630
```

---

## 4. Si de verdad lo quieres 24/7

Un telefono como servidor tiene tres enemigos: la bateria, el ahorro de energia
de Android y el wifi que se cae. Si quieres que este siempre arriba, un VPS
gratis (Oracle Cloud Always Free) es mas estable y no depende de tu telefono.
Instrucciones en [INSTALACION.md](INSTALACION.md), seccion 7.

Tambien puedes correrlo en el telefono **y** en el VPS con la misma base
copiada, pero no los dejes los dos escribiendo a la vez o se desincronizan.

---

## Resumen en 5 lineas

```bash
cd ~/TodoUtesa
python servidor.py --red          # abre a la red local
python diagnostico.py             # si algo no entra, esto te dice que es
# desde cualquier lugar: Tailscale (privado) o cloudflared (URL publica)
# siempre con clave de acceso puesta
```
