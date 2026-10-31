#!/data/data/com.termux/files/usr/bin/sh
# Arranque automatico en Termux.
# Copiar a ~/.termux/boot/ y dar permiso: chmod +x ~/.termux/boot/todoutesa.sh
# Requiere la app Termux:Boot instalada una vez desde F-Droid.

termux-wake-lock
cd "$HOME/TodoUtesa" || exit 1

while true; do
    python servidor.py
    sleep 10
done
