from calendar import monthrange
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta, time
from decimal import Decimal
import os
import re
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .auth import (
    Principal, authenticate, build_principal, current_principal, decode_token,
    permit, router as auth_router,
)
from .database import Base, SessionLocal, engine, get_db
from .models import (
    Cell, CellStatusEvent, Customer, Employee, MonthlyContract, MonthlyTariff,
    Movement, Novelty, ParkingLot, Payment, Role, Shift, Site, UserAccount,
    UserActivity, UserRole, Vehicle, VehicleType, Zone, v_user_roles,
)
from .schemas import (
    CellCreate, CellStatusUpdate, CellUpdate, CustomerCreate, EmployeeCreate,
    EmployeeUpdate, EntryCreate, NoveltyCreate, ParkingLotCreate, ParkingLotUpdate,
    PaymentCreate, RoleOut, ShiftCreate, ShiftUpdate, SiteCreate, TariffCreate,
    UserAccessCheck, UserCreate, UserStatusUpdate, UserUpdate, VehicleCreate,
    ZoneCreate,
)
from .rbac import (
    ACTIVITY_LABELS, PERMISSION_FUNCTIONS, ROLE_ADMIN, ROLE_CATALOG,
    ROLE_EMPLOYEE, ROLE_PERMISSIONS,
)
from .security import hash_password, verify_password
from .views import ensure_reporting_views

#: Zona horaria de negocio. Las columnas `DateTime` son naive, así que se guarda
#: la hora local de Bogotá sin offset y se serializa con `-05:00` para que el
#: navegador no la reinterprete como UTC.
BOGOTA_TZ = ZoneInfo("America/Bogota")


def local_today() -> date:
    """Fecha civil de Bogotá, incluso si el servidor corre en UTC."""
    return datetime.now(BOGOTA_TZ).date()


def local_now_naive() -> datetime:
    """Hora de Bogotá lista para columnas `DateTime` sin zona."""
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def iso_local(value: datetime | None) -> str | None:
    """Serializa una hora naive guardada como Bogotá con su offset real."""
    if value is None:
        return None
    aware = value.replace(tzinfo=BOGOTA_TZ) if value.tzinfo is None else value.astimezone(BOGOTA_TZ)
    return aware.isoformat()


#: Cabecera heredada. Se acepta pero NUNCA se usa para autorizar: la identidad
#: sale del token firmado (ver `app.auth.authenticate`).
ACTOR_HEADER = "X-Actor-Username"


#: La creación de esquema y los datos de demostración solo se permiten de forma
#: explícita en entornos aislados (por ejemplo, autos_colombia_test). Con la BD
#: principal el arranque es de solo lectura: no crea tablas, vistas ni registros.
AUTO_INIT_ENV = "AUTO_INIT_DB"


def auto_init_enabled() -> bool:
    return os.getenv(AUTO_INIT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if auto_init_enabled():
        Base.metadata.create_all(bind=engine)
        # Las vistas no viven en el metadata: se crean aparte (idempotente).
        with engine.begin() as connection:
            ensure_reporting_views(connection)
        with Session(bind=engine) as db:
            seed_database(db)
    yield


app = FastAPI(title="Autos Colombia API", version="0.1.0", description="Gestión configurable de parqueaderos mensuales", lifespan=lifespan)
@app.middleware("http")
async def attach_session_context(request: Request, call_next):
    """Fija la sesión en el contexto de la request antes de dependencias/vistas.

    FastAPI resuelve las dependencias y el endpoint en contextos distintos; un
    ContextVar fijado solo en la dependencia no llega al cuerpo del endpoint.
    Este middleware garantiza que `resolve_parking_lot`, la bitácora y las
    comprobaciones heredadas vean al mismo usuario autenticado.
    """
    # El principal validado se guarda en la request para que `authenticate`
    # reutilice el trabajo de este middleware (roles + empleado) en lugar de
    # repetir dos consultas por petición. Las validaciones siguen en ambas capas.
    request.state.principal = None
    request.state.auth_token = None
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        payload = decode_token(token.strip())
        if payload:
            with SessionLocal() as session:
                user = session.get(UserAccount, payload.get("uid"))
                if user and user.active and user.username == payload.get("sub") \
                        and user.parking_lot_id == payload.get("lot"):
                    principal = build_principal(session, user)
                    current_principal.set(principal)
                    request.state.principal = principal
                    request.state.auth_token = token.strip()
    return await call_next(request)


# Rutas públicas de login y de sesión (perfil, cambio de contraseña, logout).
app.include_router(auth_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://autos-colombia-web.onrender.com",
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def money_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def parse_clock(value: str) -> time:
    """Convierte 'HH:MM' en un objeto time para los turnos."""
    hour, minute = value.strip().split(":")
    return time(int(hour), int(minute))


def tariff_state(tariff: MonthlyTariff, today: date) -> str:
    if tariff.effective_from > today:
        return "PROGRAMADA"
    if tariff.effective_until and tariff.effective_until < today:
        return "CERRADA"
    return "VIGENTE"


def tariff_payload(db: Session, tariff: MonthlyTariff, vehicle_type: VehicleType | None = None) -> dict[str, Any]:
    today = local_today()
    vtype = vehicle_type or db.get(VehicleType, tariff.vehicle_type_id)
    return {
        "id": tariff.id,
        "parking_lot_id": tariff.parking_lot_id,
        "vehicle_type_id": tariff.vehicle_type_id,
        "type_name": vtype.name if vtype else "",
        "type_code": vtype.code if vtype else "",
        "amount": money_float(tariff.amount),
        "effective_from": tariff.effective_from.isoformat(),
        "effective_until": tariff.effective_until.isoformat() if tariff.effective_until else None,
        "note": tariff.note,
        "state": tariff_state(tariff, today),
    }


def employee_payload(employee: Employee) -> dict[str, Any]:
    shift = employee.shift
    return {
        "id": employee.id,
        "parking_lot_id": employee.parking_lot_id,
        "full_name": employee.full_name,
        "document_number": employee.document_number,
        "username": employee.username,
        "role": employee.role,
        "active": employee.active,
        "shift_id": employee.shift_id,
        "shift": shift_payload(shift) if shift else None,
    }


def shift_payload(shift: Shift) -> dict[str, Any]:
    return {
        "id": shift.id,
        "parking_lot_id": shift.parking_lot_id,
        "name": shift.name,
        "starts_at": shift.starts_at.strftime("%H:%M"),
        "ends_at": shift.ends_at.strftime("%H:%M"),
        "active": shift.active,
        "notes": shift.notes,
        "employees": [
            {"id": employee.id, "full_name": employee.full_name, "role": employee.role}
            for employee in sorted(shift.employees, key=lambda item: item.full_name)
        ],
    }


#: El catálogo canónico (ADMINISTRADOR / EMPLEADO) y sus permisos viven en
#: `app.rbac`. Se importan arriba para que el frontend y la API usen la misma
#: nomenclatura. `seed_roles` también normaliza códigos heredados.
def seed_roles(db: Session) -> None:
    """Asegura exactamente dos roles; renombra los códigos heredados sin borrar filas."""
    changed = False
    for old_code, new_code in (("ADMIN", ROLE_ADMIN), ("OPERATOR", ROLE_EMPLOYEE)):
        old = db.scalar(select(Role).where(Role.code == old_code))
        new = db.scalar(select(Role.id).where(Role.code == new_code))
        if old and not new:
            old.code = new_code
            changed = True
    for entry in ROLE_CATALOG:
        exists = db.scalar(select(Role.id).where(Role.code == entry["code"]))
        if exists:
            continue
        db.add(Role(**entry))
        changed = True
    if changed:
        db.commit()


def seed_database(db: Session) -> None:
    seed_roles(db)
    if db.scalar(select(ParkingLot.id).limit(1)):
        return
    lot = ParkingLot(name="Autos Colombia · demostración", tax_id=None)
    db.add(lot)
    db.flush()
    car_type = VehicleType(code="CAR", name="Carro")
    truck_type = VehicleType(code="TRUCK", name="Camioneta")
    moto_type = VehicleType(code="MOTO", name="Moto")
    db.add_all([car_type, truck_type, moto_type])
    db.flush()
    site = Site(parking_lot_id=lot.id, name="Sede principal", address="Dirección de ejemplo")
    db.add(site)
    db.flush()
    car_zone = Zone(site_id=site.id, name="Zona carros y camionetas · demo", code="A")
    moto_zone = Zone(site_id=site.id, name="Zona motos · demo", code="M")
    db.add_all([car_zone, moto_zone])
    db.flush()
    for number in range(1, 9):
        cell = Cell(zone_id=car_zone.id, code=f"C-{number:02d}")
        cell.compatible_types.extend([car_type, truck_type])
        db.add(cell)
    for number in range(1, 5):
        cell = Cell(zone_id=moto_zone.id, code=f"M-{number:02d}")
        cell.compatible_types.append(moto_type)
        db.add(cell)
    today = local_today()
    db.add_all([
        MonthlyTariff(parking_lot_id=lot.id, vehicle_type_id=car_type.id, amount=Decimal("250000"), effective_from=today),
        MonthlyTariff(parking_lot_id=lot.id, vehicle_type_id=truck_type.id, amount=Decimal("250000"), effective_from=today),
        MonthlyTariff(parking_lot_id=lot.id, vehicle_type_id=moto_type.id, amount=Decimal("100000"), effective_from=today),
    ])
    db.commit()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database": "connected"}


def parking_lot_summary(db: Session, lot: ParkingLot) -> dict[str, Any]:
    """Resumen operativo de un parqueadero: estructura, inventario y cartera."""
    sites = db.scalars(select(Site).where(Site.parking_lot_id == lot.id).order_by(Site.id)).all()
    site_ids = [site.id for site in sites]
    zones = db.scalars(select(Zone).where(Zone.site_id.in_(site_ids)).order_by(Zone.id)).all() if site_ids else []
    zone_ids = [zone.id for zone in zones]
    cells = db.scalars(select(Cell).where(Cell.zone_id.in_(zone_ids))).all() if zone_ids else []
    active_cells = [cell for cell in cells if cell.operational_status == "ACTIVE"]
    maintenance_cells = [cell for cell in cells if cell.operational_status == "MAINTENANCE"]
    occupied = db.scalar(
        select(func.count(Movement.id)).join(Cell).where(Cell.zone_id.in_(zone_ids), Movement.exited_at.is_(None))
    ) if zone_ids else 0
    vehicles_inside = db.scalar(
        select(func.count(Movement.id)).join(Vehicle).where(Vehicle.parking_lot_id == lot.id, Movement.exited_at.is_(None))
    ) or 0
    customers = db.scalar(select(func.count(Customer.id)).where(Customer.parking_lot_id == lot.id, Customer.active.is_(True))) or 0
    vehicles = db.scalar(select(func.count(Vehicle.id)).where(Vehicle.parking_lot_id == lot.id, Vehicle.active.is_(True))) or 0
    return {
        "id": lot.id,
        "name": lot.name,
        "tax_id": lot.tax_id,
        "city": lot.city,
        "address": lot.address,
        "active": lot.active,
        "sites_count": len(sites),
        "sites": [{"id": site.id, "name": site.name, "address": site.address} for site in sites],
        "zones_count": len(zones),
        "zones": [{"id": zone.id, "name": zone.name, "code": zone.code, "site_id": zone.site_id} for zone in zones],
        "cells_total": len(cells),
        "cells_active": len(active_cells),
        "cells_maintenance": len(maintenance_cells),
        "cells_occupied": occupied,
        "cells_available": max(len(active_cells) - (occupied or 0), 0),
        "customers": customers,
        "vehicles": vehicles,
        "vehicles_inside": vehicles_inside,
    }


@app.get("/api/parking-lots", dependencies=[Depends(permit("VIEW_AVAILABILITY"))])
def list_parking_lots(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lots = db.scalars(select(ParkingLot).order_by(ParkingLot.active.desc(), ParkingLot.name)).all()
    return [parking_lot_summary(db, lot) for lot in lots]


@app.post("/api/parking-lots", status_code=201, dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def create_parking_lot(payload: ParkingLotCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Crea un parqueadero vacío: sin sedes, zonas, celdas ni tarifas."""
    lot = ParkingLot(
        name=payload.name.strip(),
        tax_id=(payload.tax_id or None),
        city=payload.city.strip(),
        address=payload.address.strip(),
    )
    db.add(lot)
    db.flush()
    audit_admin(db, "PARKING_LOT_CREATED", lot.name)
    db.commit()
    db.refresh(lot)
    return parking_lot_summary(db, lot)


@app.patch("/api/parking-lots/{lot_id}", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def update_parking_lot(lot_id: int, payload: ParkingLotUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot = db.get(ParkingLot, lot_id)
    if not lot:
        raise HTTPException(404, "Parqueadero no encontrado")
    resolve_parking_lot(db, lot_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        lot.name = data["name"].strip()
    if "tax_id" in data:
        lot.tax_id = (data["tax_id"] or None)
    if "city" in data and data["city"] is not None:
        lot.city = data["city"].strip()
    if "address" in data and data["address"] is not None:
        lot.address = data["address"].strip()
    if "active" in data and data["active"] is not None:
        lot.active = data["active"]
    audit_admin(db, "PARKING_LOT_UPDATED", lot.name)
    db.commit()
    db.refresh(lot)
    return parking_lot_summary(db, lot)


@app.get("/api/bootstrap", dependencies=[Depends(permit("VIEW_AVAILABILITY"))])
def bootstrap(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    allowed_lot_id = resolve_parking_lot(db, parking_lot_id)
    lots = db.scalars(select(ParkingLot).where(ParkingLot.active.is_(True)).order_by(ParkingLot.id)).all()
    lot = next((item for item in lots if item.id == allowed_lot_id), None)
    if not lot:
        raise HTTPException(404, "No hay parqueaderos activos configurados")
    sites = db.scalars(select(Site).where(Site.parking_lot_id == lot.id, Site.active.is_(True))).all()
    types = db.scalars(select(VehicleType).order_by(VehicleType.id)).all()
    return {
        "parking_lot": {"id": lot.id, "name": lot.name, "tax_id": lot.tax_id},
        "parking_lots": [{"id": item.id, "name": item.name, "tax_id": item.tax_id} for item in lots],
        "sites": [{"id": site.id, "name": site.name, "address": site.address} for site in sites],
        "vehicle_types": [{"id": item.id, "code": item.code, "name": item.name} for item in types],
    }


@app.patch("/api/parking-lot", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def update_parking_lot(payload: ParkingLotUpdate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    lot = db.get(ParkingLot, lot_id) if lot_id else None
    if not lot:
        raise HTTPException(404, "Parqueadero no encontrado")
    lot.name = payload.name.strip()
    lot.tax_id = payload.tax_id
    db.commit()
    return {"id": lot.id, "name": lot.name, "tax_id": lot.tax_id}


@app.get("/api/vehicle-types", dependencies=[Depends(permit("OPERATE"))])
def list_vehicle_types(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [{"id": item.id, "code": item.code, "name": item.name} for item in db.scalars(select(VehicleType).order_by(VehicleType.id)).all()]


@app.get("/api/dashboard", dependencies=[Depends(permit("OPERATE"))])
def dashboard(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    if not lot_id:
        raise HTTPException(404, "Parqueadero no encontrado")
    cells = db.scalars(select(Cell).join(Zone).join(Site).where(Site.parking_lot_id == lot_id, Cell.operational_status == "ACTIVE")).all()
    active_movements = db.scalars(
        select(Movement).join(Vehicle).where(Vehicle.parking_lot_id == lot_id, Movement.exited_at.is_(None))
        .options(joinedload(Movement.vehicle).joinedload(Vehicle.vehicle_type))
    ).all()
    customers_count = db.scalar(select(func.count(Customer.id)).where(Customer.parking_lot_id == lot_id)) or 0
    vehicles_count = db.scalar(select(func.count(Vehicle.id)).where(Vehicle.parking_lot_id == lot_id, Vehicle.active.is_(True))) or 0
    occupied_ids = {movement.cell_id for movement in active_movements}
    occupancy: dict[str, dict[str, int]] = {}
    for cell in cells:
        for vehicle_type in cell.compatible_types:
            item = occupancy.setdefault(vehicle_type.code, {"total": 0, "occupied": 0, "available": 0})
            item["total"] += 1
            if cell.id in occupied_ids:
                item["occupied"] += 1
            else:
                item["available"] += 1
    today = local_today()
    active_contracts = db.scalars(
        select(MonthlyContract).join(Vehicle).where(
            Vehicle.parking_lot_id == lot_id,
            MonthlyContract.status == "ACTIVE",
            MonthlyContract.starts_on <= today,
            MonthlyContract.expires_on > today,
        )
    ).all()
    valid_contract_vehicle_ids = {contract.vehicle_id for contract in active_contracts}
    expired_count = max(vehicles_count - len(valid_contract_vehicle_ids), 0)
    coverage_end_by_vehicle = dict(db.execute(
        select(MonthlyContract.vehicle_id, func.max(MonthlyContract.expires_on))
        .join(Vehicle)
        .where(Vehicle.parking_lot_id == lot_id, MonthlyContract.status == "ACTIVE")
        .group_by(MonthlyContract.vehicle_id)
    ).all())
    expiring_soon = len({
        vehicle_id for vehicle_id, coverage_end in coverage_end_by_vehicle.items()
        if vehicle_id in valid_contract_vehicle_ids and (coverage_end - today).days <= 7
    })
    # Inventario completo por grupo de compatibilidad. Una celda apta para varios
    # grupos se cuenta una sola vez: las exclusivas de motos van a "motos" y el
    # resto a "vehiculos" (carros y camionetas).
    all_cells = db.scalars(select(Cell).join(Zone).join(Site).where(Site.parking_lot_id == lot_id)).all()
    groups: dict[str, dict[str, int]] = {
        "vehiculos": {"total": 0, "occupied": 0, "maintenance": 0},
        "motos": {"total": 0, "occupied": 0, "maintenance": 0},
    }
    for cell in all_cells:
        codes = {item.code for item in cell.compatible_types}
        key = "motos" if ("MOTO" in codes and not (codes & {"CAR", "TRUCK"})) else "vehiculos"
        bucket = groups[key]
        bucket["total"] += 1
        if cell.id in occupied_ids:
            bucket["occupied"] += 1
        elif cell.operational_status != "ACTIVE":
            bucket["maintenance"] += 1
    for bucket in groups.values():
        bucket["available"] = bucket["total"] - bucket["occupied"] - bucket["maintenance"]
    today_payments = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0), func.count(Payment.id))
        .join(MonthlyContract).join(Vehicle)
        .where(Vehicle.parking_lot_id == lot_id, func.date(Payment.paid_at) == today)
    ).one()
    return {
        "parking_lot_id": lot_id,
        "customers_registered": customers_count,
        "vehicles_registered": vehicles_count,
        "vehicles_inside": len(active_movements),
        "cells_total": len(cells),
        "cells_occupied": len(occupied_ids),
        "cells_available": max(len(cells) - len(occupied_ids), 0),
        "cells_maintenance": groups["vehiculos"]["maintenance"] + groups["motos"]["maintenance"],
        "occupancy_by_type": occupancy,
        "occupancy_by_group": groups,
        "monthly_active": vehicles_count - expired_count,
        "monthly_expired": expired_count,
        "monthly_expiring_soon": expiring_soon,
        "payments_this_month": money_float(db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).join(MonthlyContract).join(Vehicle).where(Vehicle.parking_lot_id == lot_id, func.extract("month", Payment.paid_at) == today.month, func.extract("year", Payment.paid_at) == today.year)) or 0),
        "payments_today": money_float(today_payments[0] or 0),
        "payments_today_count": int(today_payments[1] or 0),
    }


@app.get("/api/customers", dependencies=[Depends(permit("OPERATE"))])
def list_customers(parking_lot_id: int | None = None, search: str = "", db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    stmt = select(Customer).where(Customer.parking_lot_id == lot_id, Customer.active.is_(True)).options(joinedload(Customer.vehicles))
    if search:
        needle = f"%{search.strip()}%"
        stmt = stmt.where((Customer.full_name.ilike(needle)) | (Customer.document_number.ilike(needle)))
    return [{"id": customer.id, "document_type": customer.document_type, "document_number": customer.document_number,
             "full_name": customer.full_name, "phone": customer.phone, "email": customer.email,
             "vehicles_count": len(customer.vehicles)} for customer in db.scalars(stmt.order_by(Customer.full_name)).unique().all()]


@app.post("/api/customers", status_code=201, dependencies=[Depends(permit("OPERATE"))])
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, payload.parking_lot_id)
    customer_data = payload.model_dump()
    customer_data["parking_lot_id"] = lot_id
    customer_data["document_number"] = payload.document_number.strip()
    customer = Customer(**customer_data)
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un cliente con ese documento en este parqueadero")
    db.refresh(customer)
    return {"id": customer.id, "full_name": customer.full_name, "document_number": customer.document_number,
            "phone": customer.phone, "email": customer.email, "vehicles_count": 0}


@app.put("/api/customers/{customer_id}", dependencies=[Depends(permit("OPERATE"))])
def update_customer(customer_id: int, payload: CustomerCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Actualiza los datos de un cliente del parqueadero; los vehículos no cambian."""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.parking_lot_id == payload.parking_lot_id))
    if customer is None:
        raise HTTPException(404, "Cliente no encontrado en este parqueadero")
    customer_data = payload.model_dump(exclude={"parking_lot_id"})
    customer_data["document_number"] = customer_data["document_number"].strip()
    for field, value in customer_data.items():
        setattr(customer, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un cliente con ese documento en este parqueadero")
    db.refresh(customer)
    return {"id": customer.id, "document_type": customer.document_type, "full_name": customer.full_name,
            "document_number": customer.document_number, "phone": customer.phone, "email": customer.email,
            "vehicles_count": len(customer.vehicles)}


def current_contract(db: Session, vehicle_id: int) -> MonthlyContract | None:
    today = local_today()
    return db.scalar(select(MonthlyContract).where(
        MonthlyContract.vehicle_id == vehicle_id,
        MonthlyContract.status == "ACTIVE",
        MonthlyContract.starts_on <= today,
        MonthlyContract.expires_on > today,
    ).order_by(MonthlyContract.expires_on.desc()).limit(1))


def latest_contract(db: Session, vehicle_id: int) -> MonthlyContract | None:
    return db.scalar(select(MonthlyContract).where(MonthlyContract.vehicle_id == vehicle_id, MonthlyContract.status == "ACTIVE")
                     .order_by(MonthlyContract.expires_on.desc()).limit(1))


#: Centinela para distinguir "no se pasó el dato" de "se pasó None" (sin contrato
#: o sin movimiento) en los payloads con datos precargados.
_UNSET = object()


def contract_maps(db: Session, vehicle_ids: list[int]) -> tuple[dict[int, MonthlyContract], dict[int, MonthlyContract]]:
    """Contratos vigentes y de referencia por vehículo en una sola consulta."""
    if not vehicle_ids:
        return {}, {}
    today = local_today()
    contracts = db.scalars(
        select(MonthlyContract)
        .where(MonthlyContract.vehicle_id.in_(vehicle_ids), MonthlyContract.status == "ACTIVE")
        .order_by(MonthlyContract.expires_on)
    ).unique().all()
    current: dict[int, MonthlyContract] = {}
    latest: dict[int, MonthlyContract] = {}
    for contract in contracts:
        vehicle_id = contract.vehicle_id
        latest[vehicle_id] = contract
        if contract.starts_on <= today < contract.expires_on:
            current[vehicle_id] = contract
    return current, latest


def active_movement_map(db: Session, vehicle_ids: list[int]) -> dict[int, Movement]:
    """Movimiento activo por vehículo, con su celda, en una sola consulta."""
    if not vehicle_ids:
        return {}
    movements = db.scalars(
        select(Movement)
        .where(Movement.vehicle_id.in_(vehicle_ids), Movement.exited_at.is_(None))
        .options(joinedload(Movement.cell))
    ).unique().all()
    return {movement.vehicle_id: movement for movement in movements}


def vehicle_payload(
    db: Session,
    vehicle: Vehicle,
    contract: MonthlyContract | None | object = _UNSET,
    fallback_contract: MonthlyContract | None = None,
    active_movement: Movement | None | object = _UNSET,
) -> dict[str, Any]:
    today = local_today()
    if contract is _UNSET:
        contract = current_contract(db, vehicle.id)
        fallback_contract = latest_contract(db, vehicle.id)
    displayed_contract = contract or fallback_contract
    expiry_contract = fallback_contract or contract
    upcoming = displayed_contract is not None and displayed_contract.starts_on > today
    monthly_status = "VIGENTE" if contract else "ANTICIPADA" if upcoming else "VENCIDA"
    if active_movement is _UNSET:
        active_movement = db.scalar(
            select(Movement).where(Movement.vehicle_id == vehicle.id, Movement.exited_at.is_(None))
            .options(joinedload(Movement.cell))
        )
    return {
        "id": vehicle.id, "parking_lot_id": vehicle.parking_lot_id, "customer_id": vehicle.customer_id,
        "customer_name": vehicle.customer.full_name, "vehicle_type_id": vehicle.vehicle_type_id,
        "type_code": vehicle.vehicle_type.code, "type_name": vehicle.vehicle_type.name,
        "plate": vehicle.plate, "brand": vehicle.brand, "color": vehicle.color,
        "monthly_status": monthly_status,
        "expires_on": expiry_contract.expires_on.isoformat() if expiry_contract else None,
        "inside": active_movement is not None, "movement_id": active_movement.id if active_movement else None,
        "cell_code": active_movement.cell.code if active_movement else None,
    }


@app.get("/api/vehicles", dependencies=[Depends(permit("OPERATE"))])
def list_vehicles(parking_lot_id: int | None = None, search: str = "", inside: bool | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    stmt = select(Vehicle).where(Vehicle.parking_lot_id == lot_id, Vehicle.active.is_(True)).options(joinedload(Vehicle.customer), joinedload(Vehicle.vehicle_type))
    if search:
        stmt = stmt.where(Vehicle.plate.ilike(f"%{search.strip()}%"))
    vehicles = db.scalars(stmt.order_by(Vehicle.plate)).unique().all()
    vehicle_ids = [vehicle.id for vehicle in vehicles]
    current_map, latest_map = contract_maps(db, vehicle_ids)
    movements_map = active_movement_map(db, vehicle_ids)
    result = [
        vehicle_payload(db, vehicle, current_map.get(vehicle.id), latest_map.get(vehicle.id), movements_map.get(vehicle.id))
        for vehicle in vehicles
    ]
    return [item for item in result if inside is None or item["inside"] is inside]


@app.post("/api/vehicles", status_code=201, dependencies=[Depends(permit("OPERATE"))])
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, payload.parking_lot_id)
    customer = db.get(Customer, payload.customer_id)
    if not customer or customer.parking_lot_id != lot_id:
        raise HTTPException(422, "El cliente no pertenece a este parqueadero")
    vehicle_type = db.get(VehicleType, payload.vehicle_type_id)
    if not vehicle_type:
        raise HTTPException(422, "Tipo de vehículo no válido")
    vehicle_data = payload.model_dump()
    vehicle_data["parking_lot_id"] = lot_id
    vehicle_data["plate"] = payload.plate.strip().upper()
    vehicle = Vehicle(**vehicle_data)
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un vehículo con esa placa en este parqueadero")
    db.refresh(vehicle)
    return vehicle_payload(db, vehicle)


@app.get("/api/contracts", dependencies=[Depends(permit("OPERATE"))])
def list_contracts(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Cobertura contractual por vehículo para la pantalla de mensualidades.

    Cada fila resume el contrato vigente, el periodo pagado, la tarifa vigente
    y el último cobro registrado. Las fechas se toman de los datos reales: la
    cobertura une todos los periodos pagados del vehículo.
    """
    lot_id = resolve_parking_lot(db, parking_lot_id)
    today = local_today()
    vehicles = db.scalars(
        select(Vehicle)
        .where(Vehicle.parking_lot_id == lot_id, Vehicle.active.is_(True))
        .options(joinedload(Vehicle.customer), joinedload(Vehicle.vehicle_type))
        .order_by(Vehicle.plate)
    ).unique().all()
    vehicle_ids = [vehicle.id for vehicle in vehicles]
    contracts_by_vehicle: dict[int, list[MonthlyContract]] = {vehicle_id: [] for vehicle_id in vehicle_ids}
    if vehicle_ids:
        for contract in db.scalars(
            select(MonthlyContract)
            .where(MonthlyContract.vehicle_id.in_(vehicle_ids))
            .order_by(MonthlyContract.starts_on.desc(), MonthlyContract.expires_on.desc())
        ).unique().all():
            contracts_by_vehicle[contract.vehicle_id].append(contract)
        payment_rows = db.execute(
            select(Payment, MonthlyContract.vehicle_id)
            .join(MonthlyContract, Payment.contract_id == MonthlyContract.id)
            .where(MonthlyContract.vehicle_id.in_(vehicle_ids))
            .order_by(Payment.paid_at.desc())
        ).all()
    else:
        payment_rows = []
    payments_by_vehicle: dict[int, list[Payment]] = {vehicle_id: [] for vehicle_id in vehicle_ids}
    for payment, vehicle_id in payment_rows:
        payments_by_vehicle[vehicle_id].append(payment)
    type_ids = {vehicle.vehicle_type_id for vehicle in vehicles}
    tariffs: dict[int, MonthlyTariff] = {}
    if type_ids:
        for tariff in db.scalars(
            select(MonthlyTariff)
            .where(
                MonthlyTariff.parking_lot_id == lot_id,
                MonthlyTariff.vehicle_type_id.in_(type_ids),
                MonthlyTariff.effective_from <= today,
                (MonthlyTariff.effective_until.is_(None)) | (MonthlyTariff.effective_until >= today),
            )
            .order_by(MonthlyTariff.effective_from.desc())
        ).unique().all():
            tariffs.setdefault(tariff.vehicle_type_id, tariff)
    rows: list[dict[str, Any]] = []
    for vehicle in vehicles:
        contracts = contracts_by_vehicle[vehicle.id]
        current = next((item for item in contracts if item.starts_on <= today < item.expires_on), None)
        latest = max(contracts, key=lambda item: (item.expires_on, item.starts_on), default=None)
        reference = current or latest
        coverage_start = min((item.starts_on for item in contracts), default=None)
        coverage_end = max((item.expires_on for item in contracts), default=None)
        if current:
            monthly_status = "VIGENTE"
        elif latest and latest.starts_on > today:
            monthly_status = "ANTICIPADA"
        else:
            monthly_status = "VENCIDA"
        payments = payments_by_vehicle[vehicle.id]
        last_payment = payments[0] if payments else None
        tariff = tariffs.get(vehicle.vehicle_type_id)
        period_start = last_payment.period_start if last_payment else reference.starts_on if reference else None
        period_end = last_payment.period_end if last_payment else reference.expires_on if reference else None
        expiring_soon = bool(current and coverage_end and (coverage_end - today).days <= 30)
        rows.append({
            "vehicle_id": vehicle.id,
            "plate": vehicle.plate,
            "type_name": vehicle.vehicle_type.name,
            "customer_name": vehicle.customer.full_name,
            "customer_document": vehicle.customer.document_number,
            "customer_document_type": vehicle.customer.document_type,
            "contract_id": reference.id if reference else None,
            "contract_code": f"CT-{reference.id:04d}" if reference else None,
            "contract_state": "Activo" if current else "Pendiente" if monthly_status == "ANTICIPADA" else "Vencido",
            "monthly_status": monthly_status,
            "expiring_soon": expiring_soon,
            "coverage_start": coverage_start.isoformat() if coverage_start else None,
            "coverage_end": coverage_end.isoformat() if coverage_end else None,
            "period_start": period_start.isoformat() if period_start else None,
            "period_end": period_end.isoformat() if period_end else None,
            "tariff": money_float(tariff.amount) if tariff else 0,
            "paid_amount": money_float(last_payment.amount) if last_payment else 0,
            "last_paid_at": iso_local(last_payment.paid_at) if last_payment else None,
            "payments_count": len(payments),
        })
    return rows


@app.get("/api/sites", dependencies=[Depends(permit("OPERATE"))])
def list_sites(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    return [{"id": site.id, "name": site.name, "address": site.address} for site in db.scalars(select(Site).where(Site.parking_lot_id == lot_id, Site.active.is_(True))).all()]


@app.post("/api/sites", status_code=201, dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def create_site(payload: SiteCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    resolve_parking_lot(db, payload.parking_lot_id)
    if not db.get(ParkingLot, payload.parking_lot_id):
        raise HTTPException(404, "Parqueadero no encontrado")
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "El nombre de la sede es obligatorio")
    duplicate = db.scalar(
        select(Site.id).where(
            Site.parking_lot_id == payload.parking_lot_id,
            func.lower(func.trim(Site.name)) == name.lower(),
        )
    )
    if duplicate:
        raise HTTPException(
            409,
            f"Ya existe una sede llamada '{name}' en este parqueadero. No se guardó el duplicado; elige otro nombre.",
        )
    site = Site(parking_lot_id=payload.parking_lot_id, name=name, address=payload.address.strip())
    db.add(site)
    db.flush()
    audit_admin(db, "SITE_CREATED", site.name)
    db.commit()
    db.refresh(site)
    return {"id": site.id, "name": site.name, "address": site.address}


@app.get("/api/zones", dependencies=[Depends(permit("OPERATE"))])
def list_zones(site_id: int | None = None, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    stmt = select(Zone).join(Site).where(Site.parking_lot_id == lot_id)
    if site_id:
        stmt = stmt.where(Zone.site_id == site_id)
    return [{"id": zone.id, "site_id": zone.site_id, "name": zone.name, "code": zone.code}
            for zone in db.scalars(stmt.order_by(Zone.name)).all()]


@app.post("/api/zones", status_code=201, dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def create_zone(payload: ZoneCreate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    site = db.get(Site, payload.site_id)
    if not site or site.parking_lot_id != lot_id:
        raise HTTPException(404, "Sede no encontrada en este parqueadero")
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "El nombre de la zona es obligatorio")
    duplicate = db.scalar(
        select(Zone.id).where(
            Zone.site_id == payload.site_id,
            func.lower(func.trim(Zone.name)) == name.lower(),
        )
    )
    if duplicate:
        raise HTTPException(
            409,
            f"Ya existe una zona llamada '{name}' en esta sede. No se guardó el duplicado; elige otro nombre.",
        )
    zone = Zone(site_id=payload.site_id, name=name, code=(payload.code or "").strip().upper())
    db.add(zone)
    db.flush()
    audit_admin(db, "ZONE_CREATED", zone.name)
    db.commit()
    db.refresh(zone)
    return {"id": zone.id, "site_id": zone.site_id, "name": zone.name, "code": zone.code}


def cell_payload(
    db: Session,
    cell: Cell,
    movement: Movement | None | object = _UNSET,
    zone: Zone | None | object = _UNSET,
    site: Site | None | object = _UNSET,
) -> dict[str, Any]:
    if movement is _UNSET:
        movement = db.scalar(select(Movement).where(Movement.cell_id == cell.id, Movement.exited_at.is_(None)).options(joinedload(Movement.vehicle)))
    if zone is _UNSET:
        zone = db.get(Zone, cell.zone_id)
    if site is _UNSET:
        site = db.get(Site, zone.site_id) if zone else None
    return {
        "id": cell.id, "zone_id": cell.zone_id, "zone_name": zone.name if zone else "",
        "site_id": site.id if site else None, "site_name": site.name if site else "",
        "code": cell.code, "operational_status": cell.operational_status,
        "description": cell.description,
        "occupied": movement is not None,
        "vehicle_id": movement.vehicle_id if movement else None,
        "vehicle_plate": movement.vehicle.plate if movement else None,
        "compatible_types": [{"id": item.id, "code": item.code, "name": item.name} for item in cell.compatible_types],
    }


@app.get("/api/cells", dependencies=[Depends(permit("VIEW_AVAILABILITY"))])
def list_cells(parking_lot_id: int | None = None, site_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    stmt = (
        select(Cell).join(Zone).join(Site)
        .options(joinedload(Cell.compatible_types), joinedload(Cell.zone).joinedload(Zone.site))
        .where(Site.parking_lot_id == lot_id)
    )
    if site_id:
        stmt = stmt.where(Site.id == site_id)
    cells = db.scalars(stmt.order_by(Cell.code)).unique().all()
    cell_ids = [cell.id for cell in cells]
    movements = db.scalars(
        select(Movement).where(Movement.cell_id.in_(cell_ids), Movement.exited_at.is_(None))
        .options(joinedload(Movement.vehicle))
    ).unique().all() if cell_ids else []
    movement_by_cell = {movement.cell_id: movement for movement in movements}
    return [
        cell_payload(db, cell, movement_by_cell.get(cell.id), cell.zone, cell.zone.site if cell.zone else None)
        for cell in cells
    ]


@app.post("/api/cells", status_code=201, dependencies=[Depends(permit("MANAGE_CELLS"))])
def create_cell(payload: CellCreate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    zone = db.get(Zone, payload.zone_id)
    site = db.get(Site, zone.site_id) if zone else None
    if not zone or not site or site.parking_lot_id != lot_id:
        raise HTTPException(404, "Zona no encontrada en este parqueadero")
    types = [db.get(VehicleType, type_id) for type_id in payload.compatible_type_ids]
    if any(item is None for item in types):
        raise HTTPException(422, "Hay tipos de vehículo no válidos")
    cell = Cell(zone_id=payload.zone_id, code=payload.code.strip().upper(), description=payload.description,
                compatible_types=[item for item in types if item is not None])
    db.add(cell)
    try:
        db.flush()
        audit_admin(db, "CELL_CREATED", cell.code)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una celda con ese código en esta zona")
    db.refresh(cell)
    return cell_payload(db, cell)


@app.patch("/api/cells/{cell_id}", dependencies=[Depends(permit("MANAGE_CELLS"))])
def update_cell(cell_id: int, payload: CellUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Edita código, zona, compatibilidad u observación de una celda libre."""
    cell = db.get(Cell, cell_id)
    if not cell:
        raise HTTPException(404, "Celda no encontrada")
    movement = db.scalar(select(Movement.id).where(Movement.cell_id == cell_id, Movement.exited_at.is_(None)))
    if movement:
        raise HTTPException(409, "No se puede editar una celda ocupada")
    zone_id = payload.zone_id if payload.zone_id is not None else cell.zone_id
    zone = db.get(Zone, zone_id)
    if not zone:
        raise HTTPException(404, "Zona no encontrada")
    code = (payload.code if payload.code is not None else cell.code).strip().upper()
    if not code:
        raise HTTPException(422, "El código de la celda es obligatorio")
    types = cell.compatible_types
    if payload.compatible_type_ids is not None:
        types = [db.get(VehicleType, type_id) for type_id in payload.compatible_type_ids]
        if not types or any(item is None for item in types):
            raise HTTPException(422, "Hay tipos de vehículo no válidos")
    duplicate = db.scalar(
        select(Cell.id).where(Cell.zone_id == zone_id, Cell.code == code, Cell.id != cell_id)
    )
    if duplicate:
        raise HTTPException(409, "Ya existe una celda con ese código en esta zona")
    cell.zone_id = zone_id
    cell.code = code
    cell.compatible_types = [item for item in types if item is not None]
    if payload.description is not None:
        cell.description = payload.description.strip()[:200]
    audit_admin(db, "CELL_UPDATED", cell.code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una celda con ese código en esta zona")
    db.refresh(cell)
    return cell_payload(db, cell)


@app.delete("/api/cells/{cell_id}", dependencies=[Depends(permit("MANAGE_CELLS"))])
def delete_cell(cell_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Elimina una celda solo si no hay restricciones de integridad.

    Reservado a administradores (permiso MANAGE_CELLS). Se bloquea cuando la
    celda tiene un movimiento activo, historial de movimientos o bitácora de
    cambios de estado: borrarla rompería la trazabilidad de la operación.
    """
    cell = db.get(Cell, cell_id)
    if not cell:
        raise HTTPException(404, "Celda no encontrada")

    active = db.scalar(
        select(Movement)
        .where(Movement.cell_id == cell_id, Movement.exited_at.is_(None))
        .options(joinedload(Movement.vehicle))
    )
    if active:
        plate = active.vehicle.plate if active.vehicle else "sin placa"
        raise HTTPException(
            409,
            f"No se puede eliminar {cell.code}: tiene un movimiento activo de la placa {plate}. "
            "Registra la salida del vehículo antes de eliminarla.",
        )

    total_movements = db.scalar(select(func.count(Movement.id)).where(Movement.cell_id == cell_id)) or 0
    if total_movements:
        raise HTTPException(
            409,
            f"No se puede eliminar {cell.code}: conserva {total_movements} movimiento(s) en el "
            "historial. La trazabilidad de entradas y salidas no se puede borrar.",
        )

    total_events = db.scalar(select(func.count(CellStatusEvent.id)).where(CellStatusEvent.cell_id == cell_id)) or 0
    if total_events:
        raise HTTPException(
            409,
            f"No se puede eliminar {cell.code}: tiene {total_events} cambio(s) registrado(s) de "
            "estado. La bitácora de la celda no se puede borrar.",
        )

    code = cell.code
    db.delete(cell)
    audit_admin(db, "CELL_DELETED", code)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se puede eliminar la celda: existen registros relacionados.")
    return {"detail": f"Celda {code} eliminada."}


@app.patch("/api/cells/{cell_id}/status", dependencies=[Depends(permit("MANAGE_CELLS"))])
def update_cell_status(
    cell_id: int,
    payload: CellStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.operational_status not in {"ACTIVE", "MAINTENANCE", "INACTIVE"}:
        raise HTTPException(422, "Estado operativo no válido")
    cell = db.get(Cell, cell_id)
    if not cell:
        raise HTTPException(404, "Celda no encontrada")
    movement = db.scalar(select(Movement.id).where(Movement.cell_id == cell_id, Movement.exited_at.is_(None)))
    if movement and payload.operational_status != "ACTIVE":
        raise HTTPException(409, "No se puede cambiar una celda ocupada")
    previous = cell.operational_status
    cell.operational_status = payload.operational_status
    # Bitácora del cambio: motivo, responsable y fecha/hora (sin datos sensibles).
    db.add(
        CellStatusEvent(
            cell_id=cell.id,
            from_status=previous,
            to_status=payload.operational_status,
            reason=payload.reason.strip()[:240],
            actor=acting_name(db, 0, None),
        )
    )
    audit_admin(db, "CELL_STATUS_CHANGED", f"{cell.code} -> {payload.operational_status}")
    db.commit()
    return cell_payload(db, cell)


@app.get("/api/cells/{cell_id}/status-events", dependencies=[Depends(permit("VIEW_AVAILABILITY"))])
def list_cell_status_events(
    cell_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Historial de cambios de estado de una celda (motivo, responsable, fecha)."""
    if not db.get(Cell, cell_id):
        raise HTTPException(404, "Celda no encontrada")
    rows = db.scalars(
        select(CellStatusEvent)
        .where(CellStatusEvent.cell_id == cell_id)
        .order_by(CellStatusEvent.created_at.desc(), CellStatusEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "cell_id": row.cell_id,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "reason": row.reason,
            "actor": row.actor or "Sistema",
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/api/tariffs", dependencies=[Depends(permit("OPERATE"))])
def list_tariffs(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Tarifa vigente de cada tipo de vehículo (la más reciente por tipo)."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    rows = db.execute(select(MonthlyTariff, VehicleType).join(VehicleType).where(MonthlyTariff.parking_lot_id == lot_id).order_by(VehicleType.id, MonthlyTariff.effective_from.desc())).all()
    latest_by_type: dict[int, dict[str, Any]] = {}
    for tariff, vehicle_type in rows:
        if vehicle_type.id not in latest_by_type:
            latest_by_type[vehicle_type.id] = tariff_payload(db, tariff, vehicle_type)
    return list(latest_by_type.values())


@app.put("/api/tariffs/{vehicle_type_id}", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def update_tariff(vehicle_type_id: int, amount: Decimal = Query(gt=0), parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    today = local_today()
    tariff = db.scalar(select(MonthlyTariff).where(MonthlyTariff.parking_lot_id == lot_id, MonthlyTariff.vehicle_type_id == vehicle_type_id,
                                                        MonthlyTariff.effective_until.is_(None)).order_by(MonthlyTariff.effective_from.desc()).limit(1))
    if not tariff:
        raise HTTPException(404, "Tarifa no encontrada")
    if tariff.effective_from >= today:
        tariff.amount = amount
    else:
        tariff.effective_until = today - timedelta(days=1)
        tariff = MonthlyTariff(parking_lot_id=lot_id, vehicle_type_id=vehicle_type_id, amount=amount, effective_from=today)
        db.add(tariff)
    db.commit()
    return {"vehicle_type_id": vehicle_type_id, "amount": money_float(tariff.amount), "effective_from": tariff.effective_from.isoformat()}


@app.post("/api/tariffs", status_code=201, dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def create_tariff(payload: TariffCreate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Crea una vigencia nueva y cierra la anterior para evitar periodos superpuestos."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    if not lot_id:
        raise HTTPException(404, "Parqueadero no encontrado")
    if not db.get(VehicleType, payload.vehicle_type_id):
        raise HTTPException(422, "Tipo de vehículo no válido")
    if payload.effective_until and payload.effective_until < payload.effective_from:
        raise HTTPException(422, "El fin de vigencia no puede ser anterior al inicio")
    overlapping = db.scalars(
        select(MonthlyTariff).where(
            MonthlyTariff.parking_lot_id == lot_id,
            MonthlyTariff.vehicle_type_id == payload.vehicle_type_id,
            MonthlyTariff.effective_until.is_not(None),
            MonthlyTariff.effective_from <= (payload.effective_until or date.max),
            MonthlyTariff.effective_until >= payload.effective_from,
        )
    ).all()
    if overlapping:
        raise HTTPException(409, "Ya existe una vigencia que se superpone con este periodo")
    previous = db.scalar(
        select(MonthlyTariff).where(
            MonthlyTariff.parking_lot_id == lot_id,
            MonthlyTariff.vehicle_type_id == payload.vehicle_type_id,
            MonthlyTariff.effective_until.is_(None),
        ).order_by(MonthlyTariff.effective_from.desc()).limit(1)
    )
    if previous:
        if previous.effective_from >= payload.effective_from:
            raise HTTPException(409, "Ya existe una vigencia vigente que inicia después de este periodo")
        previous.effective_until = payload.effective_from - timedelta(days=1)
    tariff = MonthlyTariff(
        parking_lot_id=lot_id,
        vehicle_type_id=payload.vehicle_type_id,
        amount=payload.amount,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        note=payload.note.strip(),
    )
    db.add(tariff)
    db.commit()
    db.refresh(tariff)
    return tariff_payload(db, tariff)


@app.get("/api/tariffs/history", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def list_tariff_history(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    rows = db.execute(
        select(MonthlyTariff, VehicleType)
        .join(VehicleType, MonthlyTariff.vehicle_type_id == VehicleType.id)
        .where(MonthlyTariff.parking_lot_id == lot_id)
        .order_by(VehicleType.id, MonthlyTariff.effective_from.desc())
    ).all()
    return [tariff_payload(db, tariff, vehicle_type) for tariff, vehicle_type in rows]


@app.get("/api/reports", dependencies=[Depends(permit("VIEW_HISTORY"))])
def build_report(
    parking_lot_id: int | None = None,
    report_date: date | None = None,
    site_id: int | None = None,
    zone_id: int | None = None,
    vehicle_type_id: int | None = None,
    search: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reporte operativo del día: indicadores, inventario, cobertura y flujo."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    if not lot_id:
        raise HTTPException(404, "Parqueadero no encontrado")
    lot = db.get(ParkingLot, lot_id)
    day = report_date or local_today()
    day_start = datetime.combine(day, datetime.min.time())
    day_end = datetime.combine(day, datetime.max.time())

    site_ids = [site.id for site in db.scalars(select(Site).where(Site.parking_lot_id == lot_id)).all()]
    if site_id:
        site_ids = [site_id] if site_id in site_ids else []
    zones = db.scalars(select(Zone).where(Zone.site_id.in_(site_ids))).all() if site_ids else []
    if zone_id:
        zones = [zone for zone in zones if zone.id == zone_id]
    zone_ids = [zone.id for zone in zones]
    zones_by_id = {zone.id: zone for zone in zones}

    cells = db.scalars(
        select(Cell).where(Cell.zone_id.in_(zone_ids)).options(joinedload(Cell.compatible_types))
    ).unique().all() if zone_ids else []
    cell_ids = [cell.id for cell in cells]
    active_cells = [cell for cell in cells if cell.operational_status == "ACTIVE"]
    maintenance_cells = [cell for cell in cells if cell.operational_status == "MAINTENANCE"]

    movements = db.scalars(
        select(Movement).join(Vehicle)
        .where(Vehicle.parking_lot_id == lot_id)
        .options(joinedload(Movement.vehicle).joinedload(Vehicle.vehicle_type), joinedload(Movement.cell))
    ).all()
    if vehicle_type_id:
        movements = [item for item in movements if item.vehicle.vehicle_type_id == vehicle_type_id]
    inside = [item for item in movements if item.exited_at is None]
    occupied_cell_ids = {item.cell_id for item in inside}

    inventory: list[dict[str, Any]] = []
    types = db.scalars(select(VehicleType).order_by(VehicleType.id)).all()

    def _build_row(label: str, type_ids: set[int], track_id: int) -> dict[str, Any]:
        compatible = [cell for cell in cells
                      if type_ids & {item.id for item in cell.compatible_types}]
        compatible_active = [cell for cell in compatible if cell.operational_status == "ACTIVE"]
        compatible_maintenance = [cell for cell in compatible if cell.operational_status == "MAINTENANCE"]
        occupied = len([cell for cell in compatible if cell.id in occupied_cell_ids])
        return {
            "vehicle_type_id": track_id,
            "type_name": label,
            "total": len(compatible),
            "occupied": occupied,
            "available": max(len(compatible_active) - occupied, 0),
            "maintenance": len(compatible_maintenance),
        }

    # Agrupa carro + camioneta en una sola fila como en Figma.
    car_group = {t.id for t in types if t.code in ("CAR", "TRUCK")}
    moto_group = {t.id for t in types if t.code == "MOTO"}
    other_groups: list[tuple[str, set[int]]] = []
    grouped_ids = car_group | moto_group
    for t in types:
        if t.id not in grouped_ids:
            other_groups.append((t.name, {t.id}))

    if car_group:
        first_car = next(t for t in types if t.id in car_group)
        inventory.append(_build_row("Carro / camioneta", car_group, first_car.id))
    for label, ids in other_groups:
        inventory.append(_build_row(label, ids, next(iter(ids))))
    if moto_group:
        first_moto = next(t for t in types if t.id in moto_group)
        inventory.append(_build_row("Moto", moto_group, first_moto.id))

    # Total físico (unión de todas las celdas compatibles con cualquier tipo).
    all_ids = {t.id for t in types}
    if all_ids:
        inventory.append(_build_row("Total físico", all_ids, 0))

    day_entries = [item for item in movements if day_start <= item.entered_at <= day_end]
    day_exits = [item for item in movements if item.exited_at and day_start <= item.exited_at <= day_end]
    inside_at_start = len([item for item in movements
                            if item.entered_at < day_start and (item.exited_at is None or item.exited_at >= day_start)])

    payments = db.scalars(
        select(Payment).join(MonthlyContract).join(Vehicle)
        .where(Vehicle.parking_lot_id == lot_id, Payment.paid_at >= day_start, Payment.paid_at <= day_end)
    ).all()
    payments_by_method: dict[str, dict[str, Any]] = {}
    for payment in payments:
        bucket = payments_by_method.setdefault(payment.method, {"method": payment.method, "amount": 0.0, "count": 0})
        bucket["amount"] += money_float(payment.amount)
        bucket["count"] += 1

    vehicles = db.scalars(
        select(Vehicle).where(Vehicle.parking_lot_id == lot_id, Vehicle.active.is_(True))
        .options(joinedload(Vehicle.vehicle_type))
    ).unique().all()
    if vehicle_type_id:
        vehicles = [item for item in vehicles if item.vehicle_type_id == vehicle_type_id]
    customers_count = db.scalar(select(func.count(Customer.id)).where(Customer.parking_lot_id == lot_id, Customer.active.is_(True))) or 0
    today = local_today()
    active_contracts: dict[int, MonthlyContract] = {}
    coverage_end_by_vehicle: dict[int, date] = {}
    vehicle_ids = [vehicle.id for vehicle in vehicles]
    if vehicle_ids:
        for contract in db.scalars(
            select(MonthlyContract).where(
                MonthlyContract.vehicle_id.in_(vehicle_ids),
                MonthlyContract.status == "ACTIVE",
            ).order_by(MonthlyContract.expires_on)
        ).unique().all():
            coverage_end_by_vehicle[contract.vehicle_id] = contract.expires_on
            if contract.starts_on <= today < contract.expires_on:
                active_contracts[contract.vehicle_id] = contract
    expiring_soon = 0
    expired = 0
    active_monthly = 0
    for vehicle in vehicles:
        contract = active_contracts.get(vehicle.id)
        if contract:
            active_monthly += 1
            coverage_end = coverage_end_by_vehicle.get(vehicle.id, contract.expires_on)
            if (coverage_end - today).days <= 30:
                expiring_soon += 1
        else:
            expired += 1

    day_movements = sorted(day_entries + day_exits, key=lambda item: item.entered_at, reverse=True)
    if search.strip():
        needle = search.strip().lower()
        day_movements = [
            item for item in day_movements
            if needle in (item.vehicle.plate or "").lower()
            or needle in ((item.vehicle.customer.document_number if item.vehicle.customer else "") or "").lower()
            or needle in ((item.vehicle.customer.full_name if item.vehicle.customer else "") or "").lower()
        ]
    total_movements = len(day_movements)
    start = (page - 1) * page_size
    page_items = day_movements[start:start + page_size]
    employee_names = {employee.id: employee.full_name for employee in db.scalars(select(Employee)).all()}
    movement_rows = [{
        "id": item.id,
        "plate": item.vehicle.plate,
        "type_name": item.vehicle.vehicle_type.name,
        "entered_at": iso_local(item.entered_at),
        "exited_at": iso_local(item.exited_at),
        "cell_code": item.cell.code,
        "zone_name": zones_by_id[item.cell.zone_id].name if item.cell.zone_id in zones_by_id else "",
        "entry_employee_id": item.entry_employee_id,
        "exit_employee_id": item.exit_employee_id,
        "entry_employee": employee_names.get(item.entry_employee_id),
        "exit_employee": employee_names.get(item.exit_employee_id),
        "state": "CERRADO" if item.exited_at else "ACTIVO",
    } for item in page_items]

    cells_total = len(active_cells)
    cells_occupied = len([cell for cell in active_cells if cell.id in occupied_cell_ids])
    return {
        "parking_lot": {"id": lot.id, "name": lot.name},
        "report_date": day.isoformat(),
        "cutoff": iso_local(local_now_naive()),
        "indicators": {
            "customers": customers_count,
            "vehicles": len(vehicles),
            "vehicles_inside": len(inside),
            "vehicles_outside": max(len(vehicles) - len(inside), 0),
            "cells_total": cells_total,
            "cells_occupied": cells_occupied,
            "cells_available": max(cells_total - cells_occupied, 0),
            "cells_maintenance": len(maintenance_cells),
            "occupancy_rate": round(cells_occupied * 100 / cells_total, 1) if cells_total else 0.0,
            "payments_amount": sum(bucket["amount"] for bucket in payments_by_method.values()),
            "payments_count": len(payments),
        },
        "inventory": inventory,
        "monthly": {
            "active": active_monthly,
            "expiring_soon": expiring_soon,
            "expired": expired,
        },
        "payments_by_method": sorted(payments_by_method.values(), key=lambda item: item["amount"], reverse=True),
        "flow": {
            "entries": len(day_entries),
            "exits": len(day_exits),
            "inside_at_start": inside_at_start,
            "inside_now": len(inside),
        },
        "movements": movement_rows,
        "movements_total": total_movements,
        "movements_page": page,
        "movements_page_size": page_size,
    }


@app.get("/api/employees", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def list_employees(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    employees = db.scalars(
        select(Employee).where(Employee.parking_lot_id == lot_id)
        .options(joinedload(Employee.shift)).order_by(Employee.active.desc(), Employee.full_name)
    ).unique().all()
    return [employee_payload(employee) for employee in employees]


@app.post("/api/employees", status_code=201, dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    resolve_parking_lot(db, payload.parking_lot_id)
    if not db.get(ParkingLot, payload.parking_lot_id):
        raise HTTPException(404, "Parqueadero no encontrado")
    if payload.shift_id and not db.get(Shift, payload.shift_id):
        raise HTTPException(422, "El turno indicado no existe")
    employee = Employee(
        parking_lot_id=payload.parking_lot_id,
        document_number=payload.document_number.strip(),
        full_name=payload.full_name.strip(),
        username=payload.username.strip(),
        role=normalize_role_code(payload.role),
        shift_id=payload.shift_id,
    )
    db.add(employee)
    try:
        db.flush()
        audit_admin(db, "EMPLOYEE_CREATED", employee.full_name)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un empleado con ese usuario en este parqueadero")
    db.refresh(employee)
    return employee_payload(employee)


@app.patch("/api/employees/{employee_id}", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def update_employee(employee_id: int, payload: EmployeeUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = resolve_parking_lot(db, None)
    employee = db.get(Employee, employee_id)
    if not employee or employee.parking_lot_id != lot_id:
        raise HTTPException(403, "El empleado no pertenece al parqueadero de la sesión.")
    data = payload.model_dump(exclude_unset=True)
    if data.get("full_name") is not None:
        employee.full_name = data["full_name"].strip()
    if data.get("username") is not None:
        employee.username = data["username"].strip()
    if data.get("role") is not None:
        employee.role = normalize_role_code(data["role"])
    if "shift_id" in data:
        if data["shift_id"] and not db.get(Shift, data["shift_id"]):
            raise HTTPException(422, "El turno indicado no existe")
        employee.shift_id = data["shift_id"]
    if data.get("active") is not None:
        employee.active = data["active"]
    audit_admin(db, "EMPLOYEE_UPDATED", employee.full_name)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un empleado con ese usuario en este parqueadero")
    db.refresh(employee)
    return employee_payload(employee)


@app.get("/api/shifts", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def list_shifts(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    shifts = db.scalars(
        select(Shift).where(Shift.parking_lot_id == lot_id)
        .options(joinedload(Shift.employees)).order_by(Shift.starts_at, Shift.name)
    ).unique().all()
    return [shift_payload(shift) for shift in shifts]


@app.post("/api/shifts", status_code=201, dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def create_shift(payload: ShiftCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ParkingLot, payload.parking_lot_id):
        raise HTTPException(404, "Parqueadero no encontrado")
    shift = Shift(
        parking_lot_id=payload.parking_lot_id,
        name=payload.name.strip(),
        starts_at=parse_clock(payload.starts_at),
        ends_at=parse_clock(payload.ends_at),
        notes=payload.notes.strip(),
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift_payload(shift)


@app.patch("/api/shifts/{shift_id}", dependencies=[Depends(permit("MANAGE_STRUCTURE"))])
def update_shift(shift_id: int, payload: ShiftUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    shift = db.get(Shift, shift_id)
    if not shift:
        raise HTTPException(404, "Turno no encontrado")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        shift.name = data["name"].strip()
    if data.get("starts_at") is not None:
        shift.starts_at = parse_clock(data["starts_at"])
    if data.get("ends_at") is not None:
        shift.ends_at = parse_clock(data["ends_at"])
    if data.get("notes") is not None:
        shift.notes = data["notes"].strip()
    if data.get("active") is not None:
        shift.active = data["active"]
    db.commit()
    db.refresh(shift)
    return shift_payload(shift)


@app.get("/api/activity", dependencies=[Depends(permit("OPERATE"))])
def list_activity(parking_lot_id: int | None = None, limit: int = Query(default=10, ge=1, le=100),
                  db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Actividad reciente: ingresos, salidas y pagos con su responsable."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    entries = db.execute(
        select(Movement, Employee, Vehicle, Cell)
        .join(Vehicle, Movement.vehicle_id == Vehicle.id)
        .join(Cell, Movement.cell_id == Cell.id)
        .outerjoin(Employee, Movement.entry_employee_id == Employee.id)
        .where(Vehicle.parking_lot_id == lot_id)
        .order_by(Movement.entered_at.desc()).limit(limit)
    ).all()
    activity = [{
        "id": f"movement-{movement.id}",
        "occurred_at": iso_local(movement.entered_at),
        "employee": employee.full_name if employee else None,
        "operation": f"Ingreso {vehicle.plate} · {cell.code}",
        "kind": "ENTRY",
    } for movement, employee, vehicle, cell in entries]
    exits = db.execute(
        select(Movement, Employee, Vehicle, Cell)
        .join(Vehicle, Movement.vehicle_id == Vehicle.id)
        .join(Cell, Movement.cell_id == Cell.id)
        .outerjoin(Employee, Movement.exit_employee_id == Employee.id)
        .where(Vehicle.parking_lot_id == lot_id, Movement.exited_at.is_not(None))
        .order_by(Movement.exited_at.desc()).limit(limit)
    ).all()
    activity.extend({
        "id": f"exit-{movement.id}",
        "occurred_at": iso_local(movement.exited_at or movement.entered_at),
        "employee": employee.full_name if employee else None,
        "operation": f"Salida {vehicle.plate} · {cell.code}",
        "kind": "EXIT",
    } for movement, employee, vehicle, cell in exits)
    payments = db.execute(
        select(Payment, Employee, Vehicle)
        .join(MonthlyContract, Payment.contract_id == MonthlyContract.id)
        .join(Vehicle, MonthlyContract.vehicle_id == Vehicle.id)
        .outerjoin(Employee, Payment.employee_id == Employee.id)
        .where(Vehicle.parking_lot_id == lot_id)
        .order_by(Payment.paid_at.desc()).limit(limit)
    ).all()
    activity.extend({
        "id": f"payment-{payment.id}",
        "occurred_at": payment.paid_at.isoformat(),
        "employee": employee.full_name if employee else None,
        "operation": f"Pago {vehicle.plate} · {money_float(payment.amount):,.0f}".replace(",", "."),
        "kind": "PAYMENT",
    } for payment, employee, vehicle in payments)
    activity.sort(key=lambda item: item["occurred_at"], reverse=True)
    return activity[:limit]


@app.post("/api/movements/entry", status_code=201, dependencies=[Depends(permit("OPERATE"))])
def register_entry(payload: EntryCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = session_actor()
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicle_id).options(joinedload(Vehicle.vehicle_type)))
    cell = db.scalar(select(Cell).where(Cell.id == payload.cell_id).options(joinedload(Cell.compatible_types)))
    if not vehicle or not vehicle.active:
        raise HTTPException(404, "Vehículo no encontrado o inactivo")
    if not cell:
        raise HTTPException(404, "Celda no encontrada")
    if cell.operational_status != "ACTIVE":
        raise HTTPException(409, "La celda no está operativa")
    zone = db.get(Zone, cell.zone_id)
    site = db.get(Site, zone.site_id) if zone else None
    if not site or site.parking_lot_id != vehicle.parking_lot_id:
        raise HTTPException(422, "La celda pertenece a otro parqueadero")
    if vehicle.vehicle_type_id not in {item.id for item in cell.compatible_types}:
        raise HTTPException(422, "La celda no es compatible con este tipo de vehículo")
    active_movement = db.scalar(select(Movement.id).where(Movement.vehicle_id == vehicle.id, Movement.exited_at.is_(None)))
    if active_movement:
        raise HTTPException(409, "El vehículo ya tiene un ingreso activo")
    today = local_today()
    contract = current_contract(db, vehicle.id)
    if not contract or contract.starts_on > today or contract.expires_on <= today:
        raise HTTPException(409, "La mensualidad está vencida o aún no inicia")
    cell_used = db.scalar(select(Movement.id).where(Movement.cell_id == cell.id, Movement.exited_at.is_(None)))
    if cell_used:
        raise HTTPException(409, "La celda ya está ocupada")
    movement = Movement(
        vehicle_id=vehicle.id,
        cell_id=cell.id,
        notes=payload.notes,
        entry_employee_id=actor.employee_id,
        entered_at=local_now_naive(),
    )
    db.add(movement)
    record_activity(
        db,
        lot_id=actor.parking_lot_id,
        action="MOVEMENT_ENTRY",
        detail=f"{vehicle.plate} · {cell.code}",
        actor=actor.display_name,
        user_id=actor.user_id,
        employee_id=actor.employee_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La celda o el vehículo acaba de ser asignado por otro empleado")
    db.refresh(movement)
    return {"id": movement.id, "vehicle_id": vehicle.id, "plate": vehicle.plate, "cell_id": cell.id,
            "cell_code": cell.code, "entered_at": iso_local(movement.entered_at), "exited_at": None,
            "entry_employee_id": actor.employee_id, "entry_employee": actor.display_name}


@app.post("/api/movements/{movement_id}/exit", dependencies=[Depends(permit("OPERATE"))])
def register_exit(movement_id: int, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = session_actor()
    lot_id = resolve_parking_lot(db, parking_lot_id)
    movement = db.scalar(select(Movement).join(Vehicle).where(
        Movement.id == movement_id,
        Movement.exited_at.is_(None),
        Vehicle.parking_lot_id == lot_id,
    ).options(joinedload(Movement.vehicle), joinedload(Movement.cell)))
    if not movement:
        raise HTTPException(404, "No se encontró un ingreso activo con ese identificador")
    exited_at = local_now_naive()
    movement.exited_at = exited_at
    movement.exit_employee_id = actor.employee_id
    record_activity(
        db,
        lot_id=actor.parking_lot_id,
        action="MOVEMENT_EXIT",
        detail=f"{movement.vehicle.plate} · {movement.cell.code}",
        actor=actor.display_name,
        user_id=actor.user_id,
        employee_id=actor.employee_id,
    )
    db.commit()
    return {"id": movement.id, "plate": movement.vehicle.plate, "cell_code": movement.cell.code,
            "exited_at": iso_local(exited_at),
            "exit_employee_id": actor.employee_id, "exit_employee": actor.display_name}


@app.get("/api/movements", dependencies=[Depends(permit("OPERATE"))])
def list_movements(active: bool = False, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    stmt = select(Movement).join(Vehicle).join(Cell).join(Zone).join(Site).options(joinedload(Movement.vehicle).joinedload(Vehicle.customer), joinedload(Movement.vehicle).joinedload(Vehicle.vehicle_type), joinedload(Movement.cell)).where(Vehicle.parking_lot_id == lot_id)
    if active:
        stmt = stmt.where(Movement.exited_at.is_(None))
    movements = db.scalars(stmt.order_by(Movement.entered_at.desc()).limit(100)).unique().all()
    employee_names = {employee.id: employee.full_name for employee in db.scalars(select(Employee)).all()}
    return [{"id": item.id, "vehicle_id": item.vehicle_id, "plate": item.vehicle.plate,
             "brand": item.vehicle.brand, "color": item.vehicle.color, "type_name": item.vehicle.vehicle_type.name,
             "customer_name": item.vehicle.customer.full_name, "cell_id": item.cell_id, "cell_code": item.cell.code,
             "entered_at": iso_local(item.entered_at), "exited_at": iso_local(item.exited_at),
             "entry_employee_id": item.entry_employee_id,
             "exit_employee_id": item.exit_employee_id,
             "entry_employee": employee_names.get(item.entry_employee_id),
             "exit_employee": employee_names.get(item.exit_employee_id)}
            for item in movements]


@app.post("/api/payments", status_code=201, dependencies=[Depends(permit("OPERATE"))])
def register_payment(payload: PaymentCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = session_actor()
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicle_id).options(joinedload(Vehicle.vehicle_type)))
    if not vehicle:
        raise HTTPException(404, "Vehículo no encontrado")
    today = (payload.paid_at.date() if payload.paid_at else local_today())
    tariff = db.scalar(select(MonthlyTariff).where(MonthlyTariff.parking_lot_id == vehicle.parking_lot_id,
                                                  MonthlyTariff.vehicle_type_id == vehicle.vehicle_type_id,
                                                  MonthlyTariff.effective_from <= today,
                                                  (MonthlyTariff.effective_until.is_(None)) | (MonthlyTariff.effective_until >= today))
                       .order_by(MonthlyTariff.effective_from.desc()).limit(1))
    if not tariff:
        raise HTTPException(409, "No hay una tarifa vigente para este tipo de vehículo")
    latest_expiry = db.scalar(select(func.max(MonthlyContract.expires_on)).where(MonthlyContract.vehicle_id == vehicle.id, MonthlyContract.status == "ACTIVE"))
    period_start = max(today, latest_expiry) if latest_expiry else today
    due_date = add_months(period_start, payload.months)
    period_end = due_date - timedelta(days=1)
    contract = MonthlyContract(vehicle_id=vehicle.id, tariff_id=tariff.id, starts_on=period_start, expires_on=due_date)
    db.add(contract)
    db.flush()
    payment = Payment(contract_id=contract.id, amount=tariff.amount * payload.months,
                      paid_at=payload.paid_at or local_now_naive(), period_start=period_start,
                      period_end=period_end, method=payload.method, notes=payload.notes,
                      employee_id=actor.employee_id)
    db.add(payment)
    record_activity(db, lot_id=actor.parking_lot_id, action="PAYMENT_RECORDED", detail=f"{vehicle.plate} · {payload.months} mes(es)", actor=actor.display_name, user_id=actor.user_id, employee_id=actor.employee_id)
    db.commit()
    db.refresh(payment)
    return {"id": payment.id, "vehicle_id": vehicle.id, "plate": vehicle.plate, "amount": money_float(payment.amount),
            "paid_at": iso_local(payment.paid_at), "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "method": payment.method, "reference": payment.notes or None,
            "employee_id": actor.employee_id, "employee": actor.display_name}


@app.get("/api/payments", dependencies=[Depends(permit("OPERATE"))])
def list_payments(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    payments = db.scalars(select(Payment).join(MonthlyContract).join(Vehicle).where(Vehicle.parking_lot_id == lot_id)
                          .options(joinedload(Payment.contract).joinedload(MonthlyContract.vehicle)).order_by(Payment.paid_at.desc()).limit(100)).unique().all()
    employee_names = {employee.id: employee.full_name for employee in db.scalars(select(Employee)).all()}
    return [{"id": item.id, "vehicle_id": item.contract.vehicle_id, "plate": item.contract.vehicle.plate,
             "amount": money_float(item.amount), "paid_at": iso_local(item.paid_at),
             "period_start": item.period_start.isoformat(), "period_end": item.period_end.isoformat(),
             "method": item.method, "reference": item.notes or None,
             "employee_id": item.employee_id, "employee": employee_names.get(item.employee_id)} for item in payments]


@app.get("/api/novelties", dependencies=[Depends(permit("OPERATE"))])
def list_novelties(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = resolve_parking_lot(db, parking_lot_id)
    rows = db.execute(select(Novelty, Vehicle, Employee).join(Vehicle, Novelty.vehicle_id == Vehicle.id)
                      .outerjoin(Employee, Novelty.employee_id == Employee.id)
                      .where(Vehicle.parking_lot_id == lot_id).order_by(Novelty.created_at.desc()).limit(100)).all()
    return [{"id": novelty.id, "vehicle_id": novelty.vehicle_id, "plate": vehicle.plate,
             "category": novelty.category, "description": novelty.description,
             "created_at": novelty.created_at.isoformat(), "status": novelty.status,
             "employee_name": employee.full_name if employee else None}
            for novelty, vehicle, employee in rows]


@app.post("/api/novelties", status_code=201, dependencies=[Depends(permit("OPERATE"))])
def create_novelty(payload: NoveltyCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    actor = session_actor()
    vehicle = db.get(Vehicle, payload.vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Vehículo no encontrado")
    novelty = Novelty(**payload.model_dump(), employee_id=actor.employee_id)
    db.add(novelty)
    record_activity(db, lot_id=actor.parking_lot_id, action="NOVELTY_RECORDED", detail=f"{novelty.category} · {vehicle.plate}", actor=actor.display_name, user_id=actor.user_id, employee_id=actor.employee_id)
    db.commit()
    db.refresh(novelty)
    return {"id": novelty.id, "vehicle_id": novelty.vehicle_id, "category": novelty.category,
            "description": novelty.description, "created_at": novelty.created_at.isoformat(), "status": novelty.status,
            "employee_id": actor.employee_id, "employee": actor.display_name}


# --------------------------------------------------------------------------- #
# Administración · Usuarios                                                     #
# Cuentas de acceso (`users`), catálogo de roles (`roles`), asignación N:M      #
# (`user_roles`), bitácora (`user_activity`) y vista `v_user_roles`.            #
# `employees` solo se lee para vincular el empleado: sus columnas heredadas     #
# (`username`, `password_hash`, `role`) no se usan ni se modifican aquí.        #
# --------------------------------------------------------------------------- #

#: `ACTOR_HEADER` se define junto a los imports (lo usan también los endpoints
#: de celdas, que guardan el responsable en `cell_status_events`).

#: ROLE_PERMISSIONS, PERMISSION_FUNCTIONS y ACTIVITY_LABELS se importan de
#: `app.rbac` para no duplicar la matriz entre backend y frontend.

USERNAME_PATTERN = re.compile(r"^[a-z0-9._]{4,30}$")
MIN_PASSWORD_LENGTH = 12


def resolve_parking_lot(db: Session, parking_lot_id: int | None) -> int:
    """Resuelve el parqueadero de la operación y aplica el aislamiento por sesión.

    La sesión determina el parqueadero por defecto. Un administrador con
    ``MANAGE_STRUCTURE`` puede seleccionar otro parqueadero existente para
    configurarlo; en ese caso el principal de la request se reemplaza por el
    parqueadero elegido para que la bitácora y las validaciones posteriores
    queden en el contexto correcto.
    """
    principal = current_principal.get()
    if principal is not None:
        if not parking_lot_id or int(parking_lot_id) == principal.parking_lot_id:
            return principal.parking_lot_id
        target_lot_id = int(parking_lot_id)
        if "MANAGE_STRUCTURE" not in principal.permissions:
            raise HTTPException(403, "La cuenta autenticada no pertenece a este parqueadero.")
        if not db.get(ParkingLot, target_lot_id):
            raise HTTPException(404, "Parqueadero no encontrado")
        current_principal.set(replace(principal, parking_lot_id=target_lot_id))
        return target_lot_id
    if parking_lot_id:
        if not db.get(ParkingLot, parking_lot_id):
            raise HTTPException(404, "Parqueadero no encontrado")
        return parking_lot_id
    lot_id = db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    if not lot_id:
        raise HTTPException(404, "No hay parqueaderos registrados")
    return lot_id


def session_actor() -> Principal:
    """Responsable de la operación, tomado de la sesión firmada (nunca del cliente)."""
    principal = current_principal.get()
    if principal is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return principal


def role_ids_for_codes(db: Session, codes: tuple[str, ...]) -> list[int]:
    return list(db.scalars(select(Role.id).where(Role.code.in_(codes)).order_by(Role.sort, Role.id)))


def role_codes_of(db: Session, user_id: int) -> set[str]:
    rows = db.execute(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).scalars()
    return set(rows)


def actor_permissions(db: Session, lot_id: int, actor: str | None) -> set[str]:
    """Compatibilidad: devuelve los permisos de la cuenta de la sesión actual."""
    principal = current_principal.get()
    return set(principal.permissions) if principal else set()


def require_permission(db: Session, lot_id: int, actor: str | None, permission: str) -> None:
    """Compatibilidad con endpoints antiguos: delega en la dependencia de sesión.

    La autorización real la ejecuta ``app.auth.permit`` antes de entrar al
    endpoint; esta función solo evita que un endpoint olvidado quede abierto.
    """
    principal = current_principal.get()
    if principal is None:
        raise HTTPException(401, "Inicia sesión para continuar.")
    if principal.parking_lot_id != lot_id:
        raise HTTPException(403, "La cuenta autenticada no pertenece a este parqueadero.")
    if permission not in principal.permissions:
        raise HTTPException(403, "Tu rol no tiene permiso para esta operación.")


def acting_name(db: Session, lot_id: int, actor: str | None) -> str:
    """Nombre de quien realiza la operación, tomado de la sesión firmada."""
    principal = current_principal.get()
    return principal.display_name if principal else (actor or "Sistema")[:60]


def validate_username(value: str | None) -> str:
    """Formato del usuario único: 4–30 caracteres en minúsculas, números, . o _."""
    username = (value or "").strip()
    if not username:
        raise HTTPException(422, "El usuario es obligatorio.")
    if not USERNAME_PATTERN.fullmatch(username):
        if len(username) < 4 or len(username) > 30:
            raise HTTPException(422, "El usuario debe tener entre 4 y 30 caracteres.")
        raise HTTPException(
            422,
            "Formato inválido: no uses espacios, tildes ni signos no admitidos. "
            "Admite letras minúsculas, números, punto o guion bajo.",
        )
    return username


def validate_password(value: str | None, *, required: bool) -> str | None:
    """Política de contraseña: mínimo 12 caracteres. Vacío = sin cambios."""
    password = value or ""
    if not password:
        if required:
            raise HTTPException(422, "La contraseña es obligatoria para crear la cuenta.")
        return None
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(422, "No cumple la política propuesta: usa al menos 12 caracteres.")
    if len(password) > 200:
        raise HTTPException(422, "La contraseña no puede superar los 200 caracteres.")
    return password


def validate_role_ids(db: Session, value: list[int] | None) -> list[int]:
    ids = list(dict.fromkeys(int(item) for item in (value or [])))
    if not ids:
        raise HTTPException(422, "Selecciona Administrador o Empleado.")
    roles = list(db.scalars(select(Role).where(Role.id.in_(ids))))
    if len(roles) != len(ids):
        raise HTTPException(422, "El rol indicado no existe.")
    return [role.id for role in sorted(roles, key=lambda item: (item.sort, item.id))]


def role_names(db: Session, role_ids: list[int]) -> str:
    if not role_ids:
        return ""
    names = db.scalars(
        select(Role.name).where(Role.id.in_(role_ids)).order_by(Role.sort, Role.id)
    ).all()
    return " · ".join(names)


def split_csv(value: str | None) -> list[str]:
    return [item for item in (value or "").split(",") if item]


def role_payload(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "permissions": list(ROLE_PERMISSIONS.get(role.code, ())),
    }


def user_payload(row: Any) -> dict[str, Any]:
    """Fila de `v_user_roles`. No incluye `password_hash` por construcción."""
    return {
        "id": row.id,
        "parking_lot_id": row.parking_lot_id,
        "employee_id": row.employee_id,
        "username": row.username,
        "active": bool(row.active),
        "employee_name": row.employee_name,
        "document_number": row.document_number,
        "role_codes": split_csv(row.role_codes),
        "role_names": split_csv(row.role_names),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_login": row.last_login.isoformat() if row.last_login else None,
    }


def fetch_user_payload(db: Session, user_id: int, lot_id: int) -> dict[str, Any]:
    row = db.execute(
        select(v_user_roles).where(v_user_roles.c.id == user_id, v_user_roles.c.parking_lot_id == lot_id)
    ).first()
    if not row:
        raise HTTPException(404, "Cuenta no encontrada")
    return user_payload(row)


def record_activity(
    db: Session,
    *,
    lot_id: int,
    action: str,
    detail: str = "",
    actor: str = "",
    user_id: int | None = None,
    employee_id: int | None = None,
) -> None:
    """Registra la operación administrativa. Nunca guarda contraseñas ni hashes."""
    db.add(
        UserActivity(
            parking_lot_id=lot_id,
            user_id=user_id,
            employee_id=employee_id,
            action=action,
            detail=detail[:240],
            actor=actor[:60],
        )
    )


def normalize_role_code(code: str | None, default: str = ROLE_EMPLOYEE) -> str:
    """Acepta códigos heredados pero persiste solo la nomenclatura canónica."""
    value = (code or "").strip().upper()
    if value == "ADMIN":
        return ROLE_ADMIN
    if value == "OPERATOR":
        return ROLE_EMPLOYEE
    return value or default


def audit_admin(db: Session, action: str, detail: str = "") -> None:
    """Registra una operación administrativa con el responsable de la sesión."""
    principal = current_principal.get()
    if principal is None:
        return
    record_activity(
        db,
        lot_id=principal.parking_lot_id,
        action=action,
        detail=detail,
        actor=principal.display_name,
    )


def activity_payload(item: UserActivity, account: UserAccount | None) -> dict[str, Any]:
    label = ACTIVITY_LABELS.get(item.action, item.action)
    operation = f"{label} · {item.detail}" if item.detail else label
    return {
        "id": item.id,
        "occurred_at": item.occurred_at.isoformat(),
        "actor": item.actor or "Sistema",
        "action": item.action,
        "operation": operation,
        "detail": item.detail,
        "username": account.username if account else "",
    }


@app.get("/api/roles", dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def list_roles(db: Session = Depends(get_db)) -> list[RoleOut]:
    """Catálogo de roles con los permisos que esta API aplica en sus endpoints."""
    roles = db.scalars(select(Role).order_by(Role.sort, Role.id)).all()
    return [role_payload(role) for role in roles]


@app.get("/api/users/employees-available", dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def list_available_employees(
    parking_lot_id: int | None = None,
    actor: str | None = Header(default=None, alias=ACTOR_HEADER),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Empleados del parqueadero que todavía no tienen cuenta de acceso."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    require_permission(db, lot_id, actor, "MANAGE_ACCOUNTS")
    already_account = select(UserAccount.employee_id).where(UserAccount.parking_lot_id == lot_id)
    employees = db.scalars(
        select(Employee)
        .where(Employee.parking_lot_id == lot_id, ~Employee.id.in_(already_account))
        .options(joinedload(Employee.shift))
        .order_by(Employee.full_name)
    ).unique().all()
    return [employee_payload(employee) for employee in employees]


@app.get("/api/users/activity", dependencies=[Depends(permit("VIEW_ACTIVITY"))])
def list_user_activity(
    parking_lot_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    actor: str | None = Header(default=None, alias=ACTOR_HEADER),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Bitácora administrativa: visible solo para quien tiene VIEW_ACTIVITY."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    require_permission(db, lot_id, actor, "VIEW_ACTIVITY")
    rows = db.execute(
        select(UserActivity, UserAccount)
        .outerjoin(UserAccount, UserActivity.user_id == UserAccount.id)
        .where(UserActivity.parking_lot_id == lot_id)
        .order_by(UserActivity.occurred_at.desc(), UserActivity.id.desc())
        .limit(limit)
    ).all()
    return [activity_payload(item, account) for item, account in rows]


@app.get("/api/users", dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def list_users(
    parking_lot_id: int | None = None,
    search: str = "",
    role: str = "",
    status: str = "",
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Directorio de cuentas a través de `v_user_roles` (sin contraseñas)."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    stmt = select(v_user_roles).where(v_user_roles.c.parking_lot_id == lot_id)
    term = search.strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                v_user_roles.c.employee_name.ilike(like),
                v_user_roles.c.document_number.ilike(like),
                v_user_roles.c.username.ilike(like),
            )
        )
    if status == "ACTIVE":
        stmt = stmt.where(v_user_roles.c.active.is_(True))
    elif status == "INACTIVE":
        stmt = stmt.where(v_user_roles.c.active.is_(False))
    if role:
        role_id = db.scalar(select(Role.id).where(Role.code == role))
        if not role_id:
            return []
        stmt = stmt.where(
            select(UserRole.user_id)
            .where(UserRole.role_id == role_id, UserRole.user_id == v_user_roles.c.id)
            .exists()
        )
    rows = db.execute(
        stmt.order_by(v_user_roles.c.active.desc(), v_user_roles.c.employee_name)
    ).all()
    return [user_payload(row) for row in rows]


@app.get("/api/users/{user_id}", dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def get_user(
    user_id: int,
    parking_lot_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Detalle de una cuenta. Nunca devuelve la contraseña ni su hash."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    return fetch_user_payload(db, user_id, lot_id)


@app.post("/api/users", status_code=201, dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def create_user(
    payload: UserCreate,
    actor: str | None = Header(default=None, alias=ACTOR_HEADER),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Crea la cuenta de un empleado ya registrado y le asigna sus roles."""
    lot_id = resolve_parking_lot(db, payload.parking_lot_id)
    require_permission(db, lot_id, actor, "MANAGE_ACCOUNTS")
    username = validate_username(payload.username)
    password = validate_password(payload.password, required=True)
    role_ids = validate_role_ids(db, payload.role_ids)

    employee = db.get(Employee, payload.employee_id)
    if not employee or employee.parking_lot_id != lot_id:
        raise HTTPException(404, "El empleado indicado no existe en este parqueadero")
    existing_employee = db.scalar(select(UserAccount).where(UserAccount.employee_id == employee.id))
    if existing_employee:
        raise HTTPException(409, "Este empleado ya tiene una cuenta de acceso")
    conflict = db.scalar(
        select(UserAccount)
        .join(Employee, Employee.id == UserAccount.employee_id)
        .where(UserAccount.parking_lot_id == lot_id, UserAccount.username == username)
    )
    if conflict:
        owner = db.get(Employee, conflict.employee_id)
        raise HTTPException(
            409,
            f"Este usuario ya pertenece a {owner.full_name if owner else conflict.username}. "
            "Elige otro usuario.",
        )

    user = UserAccount(
        parking_lot_id=lot_id,
        employee_id=employee.id,
        username=username,
        password_hash=hash_password(password or ""),
        active=bool(payload.active),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    for role_id in role_ids:
        db.add(UserRole(user_id=user.id, role_id=role_id))
    record_activity(
        db,
        lot_id=lot_id,
        action="USER_CREATED",
        detail=role_names(db, role_ids),
        actor=acting_name(db, lot_id, actor),
        user_id=user.id,
        employee_id=employee.id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este empleado ya tiene una cuenta de acceso")
    return fetch_user_payload(db, user.id, lot_id)


@app.patch("/api/users/{user_id}", dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def update_user(
    user_id: int,
    payload: UserUpdate,
    parking_lot_id: int | None = None,
    actor: str | None = Header(default=None, alias=ACTOR_HEADER),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Edita usuario, contraseña y/o roles de una cuenta de este parqueadero."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    require_permission(db, lot_id, actor, "MANAGE_ACCOUNTS")
    user = db.scalar(
        select(UserAccount).where(UserAccount.id == user_id, UserAccount.parking_lot_id == lot_id)
    )
    if not user:
        raise HTTPException(404, "Cuenta no encontrada")

    data = payload.model_dump(exclude_unset=True)
    log_name = acting_name(db, lot_id, actor)
    changes: list[str] = []
    password_changed = False

    if "username" in data:
        username = validate_username(data.get("username"))
        if username != user.username:
            conflict = db.scalar(
                select(UserAccount)
                .join(Employee, Employee.id == UserAccount.employee_id)
                .where(
                    UserAccount.parking_lot_id == lot_id,
                    UserAccount.username == username,
                    UserAccount.id != user.id,
                )
            )
            if conflict:
                owner = db.get(Employee, conflict.employee_id)
                raise HTTPException(
                    409,
                    f"Este usuario ya pertenece a {owner.full_name if owner else conflict.username}. "
                    "Elige un usuario diferente.",
                )
            user.username = username
            changes.append(f"Usuario: {username}")

    if "password" in data:
        password = validate_password(data.get("password"), required=False)
        if password:
            user.password_hash = hash_password(password)
            user.must_change_password = True
            password_changed = True

    roles_changed = False
    if "role_ids" in data:
        role_ids = validate_role_ids(db, data.get("role_ids"))
        current = list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)))
        if set(role_ids) != set(current):
            roles_changed = True
            db.execute(delete(UserRole).where(UserRole.user_id == user.id))
            for role_id in role_ids:
                db.add(UserRole(user_id=user.id, role_id=role_id))
            changes.append(f"Roles: {role_names(db, role_ids)}")

    if data.get("active") is not None:
        target = bool(data["active"])
        if user.active != target:
            user.active = target
            changes.append("Activo" if target else "Inactivo")

    if not changes and not password_changed:
        return fetch_user_payload(db, user.id, lot_id)

    user.updated_at = local_now_naive()
    if changes:
        record_activity(
            db,
            lot_id=lot_id,
            action="USER_UPDATED",
            detail=" · ".join(changes),
            actor=log_name,
            user_id=user.id,
            employee_id=user.employee_id,
        )
    if roles_changed:
        record_activity(
            db,
            lot_id=lot_id,
            action="ROLES_UPDATED",
            detail=role_names(db, list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)))),
            actor=log_name,
            user_id=user.id,
            employee_id=user.employee_id,
        )
    if password_changed:
        # Solo se registra el hecho: nunca la contraseña ni su hash.
        record_activity(
            db,
            lot_id=lot_id,
            action="PASSWORD_CHANGED",
            detail=user.username,
            actor=log_name,
            user_id=user.id,
            employee_id=user.employee_id,
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este usuario ya pertenece a otra cuenta")
    return fetch_user_payload(db, user.id, lot_id)


@app.patch("/api/users/{user_id}/status", dependencies=[Depends(permit("MANAGE_ACCOUNTS"))])
def set_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    parking_lot_id: int | None = None,
    actor: str | None = Header(default=None, alias=ACTOR_HEADER),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Activa o desactiva una cuenta y lo registra en la bitácora."""
    lot_id = resolve_parking_lot(db, parking_lot_id)
    require_permission(db, lot_id, actor, "MANAGE_ACCOUNTS")
    user = db.scalar(
        select(UserAccount).where(UserAccount.id == user_id, UserAccount.parking_lot_id == lot_id)
    )
    if not user:
        raise HTTPException(404, "Cuenta no encontrada")

    target = bool(payload.active)
    if user.active != target:
        user.active = target
        user.updated_at = local_now_naive()
        record_activity(
            db,
            lot_id=lot_id,
            action="USER_ACTIVATED" if target else "USER_DEACTIVATED",
            actor=acting_name(db, lot_id, actor),
            user_id=user.id,
            employee_id=user.employee_id,
        )
        db.commit()
    return fetch_user_payload(db, user.id, lot_id)


@app.post("/api/users/access-check")
def access_check(payload: UserAccessCheck, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Comprueba credenciales sin crear sesión ni registrar la contraseña.

    Estados que la interfaz representa: credenciales incorrectas y cuenta
    inactiva. No crea sesión: para entrar se usa `POST /api/auth/login`.
    """
    lot_id = resolve_parking_lot(db, payload.parking_lot_id)
    username = (payload.username or "").strip()
    user = db.scalar(
        select(UserAccount).where(UserAccount.parking_lot_id == lot_id, UserAccount.username == username)
    )
    invalid = {
        "status": "BAD_CREDENTIALS",
        "message": "El usuario o la contraseña no coinciden. Verifica los datos e inténtalo de nuevo.",
    }
    if not user or not verify_password(payload.password or "", user.password_hash):
        return invalid
    if not user.active:
        return {
            "status": "INACTIVE",
            "message": "Contacta al administrador para revisar el estado de tu cuenta. No se inició sesión.",
        }
    role_ids = list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)))
    return {
        "status": "OK",
        "username": user.username,
        "roles": role_names(db, role_ids),
        "message": "Credenciales verificadas. Usa el inicio de sesión para entrar.",
    }
