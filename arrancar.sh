#!/bin/sh
# TodoUtesa - arranque portable (Linux, macOS, VPS)
cd "$(dirname "$0")" || exit 1

PY=""
for candidato in python3 python; do
    if command -v "$candidato" >/dev/null 2>&1; then
        PY="$candidato"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "No encontre Python 3."
    echo "  Debian:  sudo apt install python3"
    exit 1
fi

echo "Usando $PY ($($PY --version 2>&1))"
exec "$PY" servidor.py
