#!/usr/bin/env bash
# set -euo pipefail
# ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# if ! command -v python3 >/dev/null 2>&1; then
# 	echo "Se requiere Python 3.12 o superior." >&2
# 	exit 1
# fi
# if ! command -v node >/dev/null 2>&1; then
# 	echo "Se requiere Node.js 22.12 o superior." >&2
# 	exit 1
# fi

# if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
# 	python3 -m venv "$ROOT/backend/.venv"
# fi
# "$ROOT/backend/.venv/bin/python" -m pip install -q -r "$ROOT/backend/requirements.txt"
# if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
# 	(cd "$ROOT/frontend" && npm ci)
# fi
# (cd "$ROOT/backend" && .venv/bin/alembic upgrade head)

# (cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
# API_PID=$!
# (cd "$ROOT/frontend" && NG_CLI_ANALYTICS=false npm start -- --host 127.0.0.1) &
# FRONTEND_PID=$!
# cleanup() {
# 	kill "$API_PID" "$FRONTEND_PID" 2>/dev/null || true
# 	wait "$API_PID" "$FRONTEND_PID" 2>/dev/null || true
# }
# trap cleanup EXIT INT TERM
# wait -n "$API_PID" "$FRONTEND_PID"


#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Conexión a PostgreSQL: se lee de .env (no forma parte del repositorio).
# Copia .env.example a .env y completa usuario, clave y base de datos.
if [[ -f "$ROOT/.env" ]]; then
	set -a
	# shellcheck disable=SC1091
	source "$ROOT/.env"
	set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
	echo "DATABASE_URL no está definida." >&2
	echo "Copia .env.example a .env, completa la conexión de PostgreSQL y vuelve a ejecutar." >&2
	exit 1
fi

if [[ "$DATABASE_URL" != postgresql* ]]; then
	echo "Este proyecto usa únicamente PostgreSQL; DATABASE_URL debe empezar por postgresql+psycopg://." >&2
	exit 1
fi

# Detectar Python
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=(python3)
elif command -v py >/dev/null 2>&1; then
    PYTHON_CMD=(py -3.12)
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=(python)
else
    echo "Se requiere Python 3.12 o superior." >&2
    exit 1
fi

# Comprobar la versión mínima
"${PYTHON_CMD[@]}" -c \
'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
|| { echo "Se requiere Python 3.12 o superior."; exit 1; }

# Comprobar Node.js
if ! command -v node >/dev/null 2>&1; then
    echo "Se requiere Node.js 22.12 o superior." >&2
    exit 1
fi

# Crear el entorno virtual si no existe
VENV="$ROOT/backend/.venv"

if [[ -f "$VENV/Scripts/python.exe" ]]; then
    VENV_PY="$VENV/Scripts/python.exe"
elif [[ -x "$VENV/bin/python" ]]; then
    VENV_PY="$VENV/bin/python"
else
    "${PYTHON_CMD[@]}" -m venv "$VENV"

    if [[ -f "$VENV/Scripts/python.exe" ]]; then
        VENV_PY="$VENV/Scripts/python.exe"
    else
        VENV_PY="$VENV/bin/python"
    fi
fi

# Instalar dependencias del backend
"$VENV_PY" -m pip install -q -r "$ROOT/backend/requirements.txt"

# Instalar dependencias del frontend
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    (cd "$ROOT/frontend" && npm ci)
fi

# Aplicar migraciones de la base de datos
(cd "$ROOT/backend" && "$VENV_PY" -m alembic upgrade head)

# Iniciar backend y frontend
(cd "$ROOT/backend" && "$VENV_PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
API_PID=$!

(cd "$ROOT/frontend" && NG_CLI_ANALYTICS=false npm start -- --host 127.0.0.1) &
FRONTEND_PID=$!

cleanup() {
    kill "$API_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$API_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "$API_PID" "$FRONTEND_PID"
