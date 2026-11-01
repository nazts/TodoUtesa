# Instalacion paso a paso

TodoUtesa corre con **Python 3.8 o superior** y no necesita instalar ninguna
libreria. `git` es opcional: si no lo tienes, hay un plan B (descargar el ZIP).

Repositorio: https://github.com/nazts/TodoUtesa

---

## Indice

1. [Android con Termux](#1-android-con-termux)
2. [Windows](#2-windows)
3. [Linux Debian / Ubuntu](#3-linux-debian--ubuntu)
4. [Linux Arch](#4-linux-arch)
5. [Linux Fedora](#5-linux-fedora)
6. [macOS](#6-macos)
7. [VPS encendido 24/7](#7-vps-encendido-247)
8. [Verificar que quedo bien](#8-verificar-que-quedo-bien)
9. [Errores comunes](#9-errores-comunes)
10. [Actualizar el proyecto](#10-actualizar-el-proyecto)
11. [Respaldo](#11-respaldo)

---

## 1. Android con Termux

Termux convierte tu telefono en el servidor. Es la opcion mas barata para tenerlo
encendido siempre.

### 1.1 Instalar Termux

Descargalo de **F-Droid**, no de Play Store (la version de Play Store esta vieja
y rompe paquetes):

- https://f-droid.org/packages/com.termux/

Instala F-Droid, y desde ahi instala **Termux**.

### 1.2 Instalar git y python (si no los tienes)

Abre Termux y escribe:

```bash
pkg update -y && pkg upgrade -y
pkg install -y git python
```

Comprueba:

```bash
git --version
python --version
```

Si `git` dice "command not found", el `pkg install git` no termino: repitelo.

### 1.3 Clonar el repositorio

```bash
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
```

Si no quieres usar git:

```bash
pkg install -y curl unzip
cd ~
curl -L -o todoutesa.zip https://github.com/nazts/TodoUtesa/archive/refs/heads/main.zip
unzip todoutesa.zip
mv TodoUtesa-main TodoUtesa
cd TodoUtesa
```

### 1.4 Arrancar

```bash
sh arrancar.sh
```

Vas a ver algo asi:

```
 Usando python (Python 3.12.x)
========================================================
 TodoUtesa - servidor
 http://127.0.0.1:8630
 Cierra esta ventana para detener.
========================================================
```

Abre el navegador del telefono en `http://127.0.0.1:8630`.

### 1.5 Que no se detenga al bloquear el telefono

```bash
termux-wake-lock
```

Esto mantiene Termux vivo con la pantalla apagada. Para quitarlo:
`termux-unlock`.

### 1.6 Arranque automatico al encender el telefono (opcional)

1. Instala **Termux:Boot** desde F-Droid.
2. Abrela una vez (para que se registre).
3. Copia el script:

```bash
mkdir -p ~/.termux/boot
cp ~/TodoUtesa/deploy/termux-inicio.sh ~/.termux/boot/todoutesa.sh
chmod +x ~/.termux/boot/todoutesa.sh
```

Reinicia el telefono y la app arranca sola.

### 1.7 Abrirla desde la computadora

En el telefono: menu lateral -> **Servidor** -> pon una clave -> marca
"Permitir acceso desde otros equipos" -> Guardar -> **reinicia Termux**.

La misma pantalla te muestra la direccion, algo como
`http://192.168.1.50:8630`. Abrela desde la PC conectada al mismo wifi.

Forma rapida por consola, sin tocar la interfaz:

```bash
python servidor.py --red
```

Si aun asi no entra, o quieres acceder **desde fuera de tu red**, mira
[ACCESO-REMOTO.md](ACCESO-REMOTO.md) y corre `python diagnostico.py`.

---

## 2. Windows

### 2.1 Si NO tienes git (camino corto)

1. Entra a https://github.com/nazts/TodoUtesa
2. Boton verde **Code** -> **Download ZIP**
3. Clic derecho al ZIP -> **Extraer todo** -> elige una carpeta (por ejemplo
   `C:\TodoUtesa`)
4. Instala Python si no lo tienes:
   - Abre PowerShell y escribe `python --version`
   - Si no aparece, ejecuta: `winget install --id Python.Python.3.12 -e`
   - O baja el instalador de https://www.python.org/downloads/windows/
     (marca **Add python.exe to PATH**)
5. Abre la carpeta `C:\TodoUtesa` y haz doble clic en **`Iniciar.bat`**

Se abre el navegador solo en `http://127.0.0.1:8630`.

### 2.2 Si quieres usar git

Instalar git (si no lo tienes):

```powershell
winget install --id Git.Git -e --source winget
```

Cierra y vuelve a abrir PowerShell, comprueba e instala el proyecto:

```powershell
git --version
cd $HOME\Documents
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
.\Iniciar.bat
```

La primera vez que hagas `git push` (si algun dia editas algo) Windows abre una
ventana del navegador para que inicies sesion en GitHub (Git Credential Manager).

---

## 3. Linux Debian / Ubuntu

### 3.1 Instalar git y python

```bash
sudo apt update
sudo apt install -y git python3
```

### 3.2 Clonar y arrancar

```bash
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
sh arrancar.sh
```

Sin git:

```bash
sudo apt install -y curl unzip
cd ~
curl -L -o todoutesa.zip https://github.com/nazts/TodoUtesa/archive/refs/heads/main.zip
unzip todoutesa.zip && mv TodoUtesa-main TodoUtesa && cd TodoUtesa
sh arrancar.sh
```

---

## 4. Linux Arch

```bash
sudo pacman -S --needed git python
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
sh arrancar.sh
```

---

## 5. Linux Fedora

```bash
sudo dnf install -y git python3
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
sh arrancar.sh
```

---

## 6. macOS

`git` viene con las Command Line Tools y `python3` ya esta en el sistema:

```bash
xcode-select --install       # instala git (si no lo tienes)
git --version
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
sh arrancar.sh
```

Si prefieres Homebrew:

```bash
brew install git python
```

---

## 7. VPS encendido 24/7

Ejemplo con Debian 12. Sirve igual en Ubuntu, Oracle Cloud, Contabo, Hetzner, etc.

### 7.1 Preparar el servidor

```bash
sudo apt update && sudo apt install -y git python3
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/nazts/TodoUtesa.git
sudo chown -R $USER:$USER /opt/TodoUtesa
cd /opt/TodoUtesa
```

### 7.2 Primera prueba manual

```bash
sh arrancar.sh
```

Entra por el navegador a `http://IP-DEL-VPS:8630`, configura la clave de acceso
en **Servidor** y marca "Permitir acceso desde otros equipos". Reinicia.

### 7.3 Dejarlo como servicio (arranca solo y se reinicia si falla)

```bash
sudo cp deploy/todoutesa.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now todoutesa
sudo systemctl status todoutesa       # debe decir active (running)
```

Ver el log en vivo:

```bash
journalctl -u todoutesa -f
```

### 7.4 Abrir el puerto

```bash
sudo ufw allow 8630/tcp      # si usas ufw
# y en el panel del proveedor (Security List / Firewall) abre el 8630 TCP
```

**Recomendacion**: en vez de abrir el puerto al mundo, usa **Tailscale**
(gratis) y accede por la IP privada de la tailnet. Asi no expones la app a
internet.

---

## 8. Verificar que quedo bien

Con el servidor corriendo, abre otra terminal:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8630/
```

Debe responder `200`. Tambien:

```bash
curl -s http://127.0.0.1:8630/api/resumen
```

Si devuelve JSON con `"por_hacer": ...`, todo esta bien.

En el navegador deberias ver el menu con: Hoy, Tareas, Pomodoro, Calendario,
Memoria, Notas, Seguimiento, Telegram, Google y Servidor.

---

## 9. Errores comunes

| Sintoma | Causa | Solucion |
|---|---|---|
| `python: command not found` | Python no instalado o no esta en PATH | Windows: reinstala marcando *Add to PATH*. Linux/Termux: `pkg install python` / `apt install python3` |
| `No encuentre Python 3` al usar `arrancar.sh` | idem | Instala python3 y vuelve a intentar |
| `git: command not found` | git no instalado | Termux `pkg install git` · Debian `apt install git` · Windows `winget install Git.Git` |
| `Permission denied` en `arrancar.sh` | falta permiso de ejecucion | `chmod +x arrancar.sh` (o usa `sh arrancar.sh`) |
| Arranca en 8631 en vez de 8630 | ya hay otra instancia en 8630 | Cierra la otra instancia o cambia el puerto en **Servidor** |
| La pagina carga pero no hay datos | estas entrando a otra instancia | Revisa el puerto que imprime la consola |
| Se detiene al bloquear el telefono | Android suspende Termux | `termux-wake-lock` |
| `no module named ...` | estas corriendo con otro Python raro | Usa `python3 servidor.py` o revisa `python --version` (3.8+) |
| No entra desde el telefono | host en 127.0.0.1 | **Servidor** -> clave -> "Permitir acceso desde otros equipos" -> reiniciar |

---

## 10. Actualizar el proyecto

Si lo clonaste con git:

```bash
cd TodoUtesa
git pull
```

Tus datos **no se tocan**: viven en `datos/`, que esta en `.gitignore`.

Si bajaste el ZIP, descarga el ZIP nuevo y copia encima **sin borrar la carpeta
`datos/`**.

---

## 11. Respaldo

Todo el estado es un archivo:

```
datos/todoutesa.db      (o habitos.db si vienes de una version anterior)
```

Copiar esa carpeta es todo:

```bash
# Linux / Termux / macOS
cp -r datos ~/respaldo-todoutesa-$(date +%F)

# Windows
xcopy datos C:\respaldo-todoutesa /E /I
```

Ahi dentro tambien estan `moodle.json`, `telegram.json` y `google_token.json`
con tus credenciales locales. No los subas a ningun lado.
