# Instalacion paso a paso

TodoUtesa corre con **Python 3.8 o superior** y no necesita instalar ninguna
libreria. `git` es opcional: si no lo tienes, hay un plan B (descargar el ZIP).

Funciona en **Windows, Linux y macOS** (tambien en un VPS Linux encendido 24/7).

Repositorio: https://github.com/nazts/TodoUtesa

---

## Indice

1. [Windows](#1-windows)
2. [Linux Debian / Ubuntu](#2-linux-debian--ubuntu)
3. [Linux Arch](#3-linux-arch)
4. [Linux Fedora](#4-linux-fedora)
5. [macOS](#5-macos)
6. [VPS encendido 24/7](#6-vps-encendido-247)
7. [Verificar que quedo bien](#7-verificar-que-quedo-bien)
8. [Errores comunes](#8-errores-comunes)
9. [Actualizar el proyecto](#9-actualizar-el-proyecto)
10. [Respaldo](#10-respaldo)

---

## 1. Windows

### 1.1 Si NO tienes git (camino corto)

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

### 1.2 Si quieres usar git

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

## 2. Linux Debian / Ubuntu

### 2.1 Instalar git y python

```bash
sudo apt update
sudo apt install -y git python3
```

### 2.2 Clonar y arrancar

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

## 3. Linux Arch

```bash
sudo pacman -S --needed git python
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
sh arrancar.sh
```

---

## 4. Linux Fedora

```bash
sudo dnf install -y git python3
cd ~
git clone https://github.com/nazts/TodoUtesa.git
cd TodoUtesa
sh arrancar.sh
```

---

## 5. macOS

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

## 6. VPS encendido 24/7

Ejemplo con Debian 12. Sirve igual en Ubuntu, Oracle Cloud, Contabo, Hetzner, etc.

### 6.1 Preparar el servidor

```bash
sudo apt update && sudo apt install -y git python3
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/nazts/TodoUtesa.git
sudo chown -R $USER:$USER /opt/TodoUtesa
cd /opt/TodoUtesa
```

### 6.2 Primera prueba manual

```bash
sh arrancar.sh
```

Entra por el navegador a `http://IP-DEL-VPS:8630`, configura la clave de acceso
en **Servidor** y marca "Permitir acceso desde otros equipos". Reinicia.

### 6.3 Dejarlo como servicio (arranca solo y se reinicia si falla)

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

### 6.4 Abrir el puerto

```bash
sudo ufw allow 8630/tcp      # si usas ufw
# y en el panel del proveedor (Security List / Firewall) abre el 8630 TCP
```

**Recomendacion**: en vez de abrir el puerto al mundo, usa **Tailscale**
(gratis) y accede por la IP privada de la tailnet. Asi no expones la app a
internet. Ver [ACCESO-REMOTO.md](ACCESO-REMOTO.md).

---

## 7. Verificar que quedo bien

Con la app corriendo, abre otra terminal:

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

Si algo no entra desde otro equipo:

```bash
python diagnostico.py
```

---

## 8. Errores comunes

| Sintoma | Causa | Solucion |
|---|---|---|
| `python: command not found` | Python no instalado o no esta en PATH | Windows: reinstala marcando *Add to PATH*. Linux: `sudo apt install python3` |
| `No encuentro Python 3` al usar `arrancar.sh` | idem | Instala python3 y vuelve a intentar |
| `git: command not found` | git no instalado | Windows `winget install Git.Git` · Debian `apt install git` · Arch `pacman -S git` |
| `Permission denied` en `arrancar.sh` | falta permiso de ejecucion | `chmod +x arrancar.sh` (o usa `sh arrancar.sh`) |
| Arranca en 8631 en vez de 8630 | ya hay otra instancia en 8630 | Cierra la otra instancia o cambia el puerto en **Servidor** |
| La pagina carga pero no hay datos | estas entrando a otra instancia | Revisa el puerto que imprime la consola |
| No entra desde otro equipo | host en 127.0.0.1 | **Servidor** -> clave -> "Permitir acceso desde otros equipos" -> reiniciar |
| `no module named ...` | estas corriendo con otro Python | Usa `python3 servidor.py` y revisa `python --version` (3.8+) |

---

## 9. Actualizar el proyecto

Si lo clonaste con git:

```bash
cd TodoUtesa
git pull
```

Tus datos **no se tocan**: viven en `datos/`, que esta en `.gitignore`.

Si bajaste el ZIP, descarga el ZIP nuevo y copia encima **sin borrar la carpeta
`datos/`**.

---

## 10. Respaldo

Todo el estado es un archivo:

```
datos/todoutesa.db
```

Copiar esa carpeta es todo:

```bash
# Linux / macOS
cp -r datos ~/respaldo-todoutesa-$(date +%F)

# Windows (PowerShell)
Copy-Item datos C:\respaldo-todoutesa -Recurse
```

Ahi dentro tambien estan `moodle.json`, `telegram.json` y `google_token.json`
con tus credenciales locales. No los subas a ningun lado.
