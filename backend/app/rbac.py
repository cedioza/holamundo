"""Catálogo único de roles y permisos de Autos Colombia.

Solo existen dos roles. Los códigos son canónicos en toda la aplicación:
`ADMINISTRADOR` y `EMPLEADO`. No se crean roles adicionales.

Los permisos se comprueban en FastAPI (ver ``app.auth.permit``) y se reutilizan
en Angular para construir el menú y proteger las vistas.
"""

from __future__ import annotations

from typing import Any

ROLE_ADMIN = "ADMINISTRADOR"
ROLE_EMPLOYEE = "EMPLEADO"

P_OPERATE = "OPERATE"
P_VIEW_AVAILABILITY = "VIEW_AVAILABILITY"
P_MANAGE_ACCOUNTS = "MANAGE_ACCOUNTS"
P_MANAGE_STRUCTURE = "MANAGE_STRUCTURE"
P_MANAGE_CELLS = "MANAGE_CELLS"
P_VIEW_ACTIVITY = "VIEW_ACTIVITY"
P_VIEW_HISTORY = "VIEW_HISTORY"

ROLE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "code": ROLE_ADMIN,
        "name": "Administrador",
        "description": (
            "Operación completa, gestión de cuentas, parqueaderos, sedes, zonas, "
            "celdas, historial de movimientos y bitácora administrativa."
        ),
        "sort": 1,
    },
    {
        "code": ROLE_EMPLOYEE,
        "name": "Empleado",
        "description": (
            "Registrar ingresos, salidas, pagos y novedades; consultar clientes, "
            "vehículos y ocupación; crear y configurar celdas. Sin acceso administrativo."
        ),
        "sort": 2,
    },
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: (
        P_OPERATE,
        P_VIEW_AVAILABILITY,
        P_MANAGE_ACCOUNTS,
        P_MANAGE_STRUCTURE,
        P_MANAGE_CELLS,
        P_VIEW_ACTIVITY,
        P_VIEW_HISTORY,
    ),
    ROLE_EMPLOYEE: (P_OPERATE, P_VIEW_AVAILABILITY, P_MANAGE_CELLS),
}

PERMISSION_FUNCTIONS: tuple[tuple[str, str], ...] = (
    (P_OPERATE, "Registrar ingresos, salidas, pagos y novedades"),
    (P_VIEW_AVAILABILITY, "Consultar disponibilidad, ocupación y celdas"),
    (P_MANAGE_CELLS, "Crear, configurar y modificar celdas"),
    (P_MANAGE_ACCOUNTS, "Crear, editar, activar o desactivar cuentas y roles"),
    (P_MANAGE_STRUCTURE, "Gestionar parqueaderos, sedes, zonas y tarifas"),
    (P_VIEW_HISTORY, "Consultar el historial administrativo de movimientos"),
    (P_VIEW_ACTIVITY, "Consultar bitácora administrativa"),
)

ACTIVITY_LABELS: dict[str, str] = {
    "USER_CREATED": "Creación de cuenta",
    "USER_UPDATED": "Edición de cuenta",
    "ROLES_UPDATED": "Actualización de rol",
    "USER_ACTIVATED": "Activación de cuenta",
    "USER_DEACTIVATED": "Desactivación de cuenta",
    "PASSWORD_CHANGED": "Actualización de contraseña",
    "LOGIN": "Inicio de sesión",
    "LOGOUT": "Cierre de sesión",
    "PARKING_LOT_CREATED": "Creación de parqueadero",
    "PARKING_LOT_UPDATED": "Edición de parqueadero",
    "SITE_CREATED": "Creación de sede",
    "ZONE_CREATED": "Creación de zona",
    "CELL_CREATED": "Creación de celda",
    "CELL_UPDATED": "Edición de celda",
    "CELL_STATUS_CHANGED": "Cambio de estado de celda",
    "EMPLOYEE_CREATED": "Creación de empleado",
    "EMPLOYEE_UPDATED": "Edición de empleado",
    "MOVEMENT_ENTRY": "Entrada registrada",
    "MOVEMENT_EXIT": "Salida registrada",
    "PAYMENT_RECORDED": "Pago registrado",
    "NOVELTY_RECORDED": "Novedad registrada",
    "INVENTORY_CONFIGURED": "Inventario de celdas configurado",
}

PAGE_PERMISSIONS: dict[str, str] = {
    "dashboard": P_OPERATE,
    "cells": P_VIEW_AVAILABILITY,
    "entry": P_OPERATE,
    "exit": P_OPERATE,
    "customers": P_OPERATE,
    "vehicles": P_VIEW_AVAILABILITY,
    "payments": P_OPERATE,
    "payments-register": P_OPERATE,
    "novelties": P_OPERATE,
    "history": P_VIEW_HISTORY,
    "parking-lots": P_MANAGE_STRUCTURE,
    "employees": P_MANAGE_STRUCTURE,
    "users": P_MANAGE_ACCOUNTS,
    "users-form": P_MANAGE_ACCOUNTS,
    "reports": P_VIEW_ACTIVITY,
    "settings": P_MANAGE_STRUCTURE,
    "tariffs": P_MANAGE_STRUCTURE,
}


def permissions_for_roles(codes: set[str] | list[str] | tuple[str, ...]) -> frozenset[str]:
    """Une los permisos de todos los roles asignados a una cuenta."""
    result: set[str] = set()
    for code in codes:
        result.update(ROLE_PERMISSIONS.get(code, ()))
    return frozenset(result)
