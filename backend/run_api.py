"""Arranca la API de Autos Colombia con un event loop compatible con Windows.

El ``ProactorEventLoop`` que usa Windows por defecto falla con
``WinError 64 ("El nombre de red especificado ya no está disponible")`` cuando
cambia la interfaz de red (Wi-Fi, VPN, etc.), lo que derriba el servidor y hace
que el frontend muestre "No fue posible completar la operación".

``SelectorEventLoop`` no tiene este problema. En Linux/macOS se conserva el
comportamiento habitual.
"""
from __future__ import annotations

import asyncio
import sys

import uvicorn


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")


if __name__ == "__main__":
    main()
