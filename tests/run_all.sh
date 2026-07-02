#!/bin/bash
# Corre todos los tests headless. Requiere DISPLAY y el venv del proyecto.
set -e
cd "$(dirname "$0")"
PY="${PY:-../.venv/bin/python}"
[ -x "$PY" ] || PY=python3
for t in test_*.py; do
    echo "══ $t ══"
    "$PY" "$t"
done
echo "✔ TODOS LOS TESTS OK"
