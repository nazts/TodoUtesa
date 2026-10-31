#!/bin/sh
# Lanzador para Linux / VPS / Termux
cd "$(dirname "$0")" || exit 1
exec python3 servidor.py
