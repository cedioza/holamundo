from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .database import Base, engine, get_db
from .models import (
    Cell, Customer, Employee, MonthlyContract, MonthlyTariff, Movement, Novelty,
    ParkingLot, Payment, Shift, Site, Vehicle, VehicleType, Zone,
)
from .schemas import (
    CellCreate, CellStatusUpdate, CustomerCreate, EmployeeCreate, EmployeeUpdate,
    EntryCreate, NoveltyCreate, ParkingLotCreate, ParkingLotUpdate, PaymentCreate,
    ShiftCreate, ShiftUpdate, SiteCreate, TariffCreate, VehicleCreate, ZoneCreate,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        seed_database(db)
    yield


app = FastAPI(title="Autos Colombia API", version="0.1.0", description="Gestión configurable de parqueaderos mensuales", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    today = date.today()
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


def seed_database(db: Session) -> None:
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
    today = date.today()
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


@app.get("/api/parking-lots")
def list_parking_lots(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lots = db.scalars(select(ParkingLot).order_by(ParkingLot.active.desc(), ParkingLot.name)).all()
    return [parking_lot_summary(db, lot) for lot in lots]


@app.post("/api/parking-lots", status_code=201)
def create_parking_lot(payload: ParkingLotCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Crea un parqueadero vacío: sin sedes, zonas, celdas ni tarifas."""
    lot = ParkingLot(
        name=payload.name.strip(),
        tax_id=(payload.tax_id or None),
        city=payload.city.strip(),
        address=payload.address.strip(),
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return parking_lot_summary(db, lot)


@app.patch("/api/parking-lots/{lot_id}")
def update_parking_lot(lot_id: int, payload: ParkingLotUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot = db.get(ParkingLot, lot_id)
    if not lot:
        raise HTTPException(404, "Parqueadero no encontrado")
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
    db.commit()
    db.refresh(lot)
    return parking_lot_summary(db, lot)


@app.get("/api/bootstrap")
def bootstrap(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lots = db.scalars(select(ParkingLot).where(ParkingLot.active.is_(True)).order_by(ParkingLot.id)).all()
    lot = next((item for item in lots if item.id == parking_lot_id), None) if parking_lot_id else (lots[0] if lots else None)
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


@app.patch("/api/parking-lot")
def update_parking_lot(payload: ParkingLotUpdate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    lot = db.get(ParkingLot, lot_id) if lot_id else None
    if not lot:
        raise HTTPException(404, "Parqueadero no encontrado")
    lot.name = payload.name.strip()
    lot.tax_id = payload.tax_id
    db.commit()
    return {"id": lot.id, "name": lot.name, "tax_id": lot.tax_id}


@app.get("/api/vehicle-types")
def list_vehicle_types(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [{"id": item.id, "code": item.code, "name": item.name} for item in db.scalars(select(VehicleType).order_by(VehicleType.id)).all()]


@app.get("/api/dashboard")
def dashboard(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
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
    today = date.today()
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
    expiring_soon = len({
        contract.vehicle_id for contract in active_contracts
        if (contract.expires_on - today).days <= 7
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


@app.get("/api/customers")
def list_customers(parking_lot_id: int | None = None, search: str = "", db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    stmt = select(Customer).where(Customer.parking_lot_id == lot_id, Customer.active.is_(True)).options(joinedload(Customer.vehicles))
    if search:
        needle = f"%{search.strip()}%"
        stmt = stmt.where((Customer.full_name.ilike(needle)) | (Customer.document_number.ilike(needle)))
    return [{"id": customer.id, "document_type": customer.document_type, "document_number": customer.document_number,
             "full_name": customer.full_name, "phone": customer.phone, "email": customer.email,
             "vehicles_count": len(customer.vehicles)} for customer in db.scalars(stmt.order_by(Customer.full_name)).unique().all()]


@app.post("/api/customers", status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    customer_data = payload.model_dump()
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


@app.put("/api/customers/{customer_id}")
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
    today = date.today()
    return db.scalar(select(MonthlyContract).where(
        MonthlyContract.vehicle_id == vehicle_id,
        MonthlyContract.status == "ACTIVE",
        MonthlyContract.starts_on <= today,
        MonthlyContract.expires_on > today,
    ).order_by(MonthlyContract.expires_on.desc()).limit(1))


def latest_contract(db: Session, vehicle_id: int) -> MonthlyContract | None:
    return db.scalar(select(MonthlyContract).where(MonthlyContract.vehicle_id == vehicle_id, MonthlyContract.status == "ACTIVE")
                     .order_by(MonthlyContract.expires_on.desc()).limit(1))


def vehicle_payload(db: Session, vehicle: Vehicle) -> dict[str, Any]:
    today = date.today()
    contract = current_contract(db, vehicle.id)
    displayed_contract = contract or latest_contract(db, vehicle.id)
    upcoming = displayed_contract is not None and displayed_contract.starts_on > today
    monthly_status = "VIGENTE" if contract else "ANTICIPADA" if upcoming else "VENCIDA"
    active_movement = db.scalar(select(Movement).where(Movement.vehicle_id == vehicle.id, Movement.exited_at.is_(None)))
    return {
        "id": vehicle.id, "parking_lot_id": vehicle.parking_lot_id, "customer_id": vehicle.customer_id,
        "customer_name": vehicle.customer.full_name, "vehicle_type_id": vehicle.vehicle_type_id,
        "type_code": vehicle.vehicle_type.code, "type_name": vehicle.vehicle_type.name,
        "plate": vehicle.plate, "brand": vehicle.brand, "color": vehicle.color,
        "monthly_status": monthly_status,
        "expires_on": displayed_contract.expires_on.isoformat() if displayed_contract else None,
        "inside": active_movement is not None, "movement_id": active_movement.id if active_movement else None,
        "cell_code": active_movement.cell.code if active_movement else None,
    }


@app.get("/api/vehicles")
def list_vehicles(parking_lot_id: int | None = None, search: str = "", inside: bool | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    stmt = select(Vehicle).where(Vehicle.parking_lot_id == lot_id, Vehicle.active.is_(True)).options(joinedload(Vehicle.customer), joinedload(Vehicle.vehicle_type))
    if search:
        stmt = stmt.where(Vehicle.plate.ilike(f"%{search.strip()}%"))
    vehicles = db.scalars(stmt.order_by(Vehicle.plate)).unique().all()
    result = [vehicle_payload(db, vehicle) for vehicle in vehicles]
    return [item for item in result if inside is None or item["inside"] is inside]


@app.post("/api/vehicles", status_code=201)
def create_vehicle(payload: VehicleCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    customer = db.get(Customer, payload.customer_id)
    if not customer or customer.parking_lot_id != payload.parking_lot_id:
        raise HTTPException(422, "El cliente no pertenece a este parqueadero")
    vehicle_type = db.get(VehicleType, payload.vehicle_type_id)
    if not vehicle_type:
        raise HTTPException(422, "Tipo de vehículo no válido")
    vehicle_data = payload.model_dump()
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


@app.get("/api/contracts")
def list_contracts(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Cobertura contractual por vehículo para la pantalla de mensualidades.

    Cada fila resume el contrato vigente, el periodo pagado, la tarifa vigente
    y el último cobro registrado. Las fechas se toman de los datos reales: la
    cobertura une todos los periodos pagados del vehículo.
    """
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    today = date.today()
    vehicles = db.scalars(
        select(Vehicle)
        .where(Vehicle.parking_lot_id == lot_id, Vehicle.active.is_(True))
        .options(joinedload(Vehicle.customer), joinedload(Vehicle.vehicle_type))
        .order_by(Vehicle.plate)
    ).unique().all()
    rows: list[dict[str, Any]] = []
    for vehicle in vehicles:
        contracts = db.scalars(
            select(MonthlyContract)
            .where(MonthlyContract.vehicle_id == vehicle.id)
            .order_by(MonthlyContract.starts_on.desc(), MonthlyContract.expires_on.desc())
        ).all()
        current = next((item for item in contracts if item.starts_on <= today <= item.expires_on), None)
        latest = contracts[0] if contracts else None
        reference = current or latest
        coverage_start = min((item.starts_on for item in contracts), default=None)
        coverage_end = max((item.expires_on for item in contracts), default=None)
        if current:
            monthly_status = "VIGENTE"
        elif latest and latest.starts_on > today:
            monthly_status = "ANTICIPADA"
        else:
            monthly_status = "VENCIDA"
        payments = db.scalars(
            select(Payment)
            .join(MonthlyContract, Payment.contract_id == MonthlyContract.id)
            .where(MonthlyContract.vehicle_id == vehicle.id)
            .order_by(Payment.paid_at.desc())
        ).all()
        last_payment = payments[0] if payments else None
        tariff = db.scalar(
            select(MonthlyTariff)
            .where(
                MonthlyTariff.parking_lot_id == vehicle.parking_lot_id,
                MonthlyTariff.vehicle_type_id == vehicle.vehicle_type_id,
                MonthlyTariff.effective_from <= today,
                (MonthlyTariff.effective_until.is_(None)) | (MonthlyTariff.effective_until >= today),
            )
            .order_by(MonthlyTariff.effective_from.desc())
            .limit(1)
        )
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
            "expiring_soon": bool(current and (current.expires_on - today).days <= 30),
            "coverage_start": coverage_start.isoformat() if coverage_start else None,
            "coverage_end": coverage_end.isoformat() if coverage_end else None,
            "period_start": reference.starts_on.isoformat() if reference else None,
            "period_end": reference.expires_on.isoformat() if reference else None,
            "tariff": money_float(tariff.amount) if tariff else 0,
            "paid_amount": money_float(last_payment.amount) if last_payment else 0,
            "last_paid_at": last_payment.paid_at.isoformat() if last_payment else None,
            "payments_count": len(payments),
        })
    return rows


@app.get("/api/sites")
def list_sites(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    return [{"id": site.id, "name": site.name, "address": site.address} for site in db.scalars(select(Site).where(Site.parking_lot_id == lot_id, Site.active.is_(True))).all()]


@app.post("/api/sites", status_code=201)
def create_site(payload: SiteCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ParkingLot, payload.parking_lot_id):
        raise HTTPException(404, "Parqueadero no encontrado")
    site = Site(**payload.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return {"id": site.id, "name": site.name, "address": site.address}


@app.get("/api/zones")
def list_zones(site_id: int | None = None, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Zone).join(Site)
    if site_id:
        stmt = stmt.where(Zone.site_id == site_id)
    if parking_lot_id:
        stmt = stmt.where(Site.parking_lot_id == parking_lot_id)
    return [{"id": zone.id, "site_id": zone.site_id, "name": zone.name, "code": zone.code}
            for zone in db.scalars(stmt.order_by(Zone.name)).all()]


@app.post("/api/zones", status_code=201)
def create_zone(payload: ZoneCreate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    site = db.get(Site, payload.site_id)
    if not site or (parking_lot_id and site.parking_lot_id != parking_lot_id):
        raise HTTPException(404, "Sede no encontrada en este parqueadero")
    zone = Zone(site_id=payload.site_id, name=payload.name.strip(), code=(payload.code or "").strip().upper())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return {"id": zone.id, "site_id": zone.site_id, "name": zone.name, "code": zone.code}


def cell_payload(db: Session, cell: Cell) -> dict[str, Any]:
    movement = db.scalar(select(Movement).where(Movement.cell_id == cell.id, Movement.exited_at.is_(None)).options(joinedload(Movement.vehicle)))
    zone = db.get(Zone, cell.zone_id)
    site = db.get(Site, zone.site_id) if zone else None
    return {
        "id": cell.id, "zone_id": cell.zone_id, "zone_name": zone.name if zone else "",
        "site_id": site.id if site else None, "site_name": site.name if site else "",
        "code": cell.code, "operational_status": cell.operational_status,
        "occupied": movement is not None,
        "vehicle_id": movement.vehicle_id if movement else None,
        "vehicle_plate": movement.vehicle.plate if movement else None,
        "compatible_types": [{"id": item.id, "code": item.code, "name": item.name} for item in cell.compatible_types],
    }


@app.get("/api/cells")
def list_cells(parking_lot_id: int | None = None, site_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Cell).join(Zone).join(Site).options(joinedload(Cell.compatible_types))
    if parking_lot_id:
        stmt = stmt.where(Site.parking_lot_id == parking_lot_id)
    if site_id:
        stmt = stmt.where(Site.id == site_id)
    return [cell_payload(db, cell) for cell in db.scalars(stmt.order_by(Cell.code)).unique().all()]


@app.post("/api/cells", status_code=201)
def create_cell(payload: CellCreate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    zone = db.get(Zone, payload.zone_id)
    site = db.get(Site, zone.site_id) if zone else None
    if not zone or not site or (parking_lot_id and site.parking_lot_id != parking_lot_id):
        raise HTTPException(404, "Zona no encontrada en este parqueadero")
    types = [db.get(VehicleType, type_id) for type_id in payload.compatible_type_ids]
    if any(item is None for item in types):
        raise HTTPException(422, "Hay tipos de vehículo no válidos")
    cell = Cell(zone_id=payload.zone_id, code=payload.code.strip().upper(), description=payload.description,
                compatible_types=[item for item in types if item is not None])
    db.add(cell)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una celda con ese código en esta zona")
    db.refresh(cell)
    return cell_payload(db, cell)


@app.patch("/api/cells/{cell_id}/status")
def update_cell_status(cell_id: int, payload: CellStatusUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if payload.operational_status not in {"ACTIVE", "MAINTENANCE", "INACTIVE"}:
        raise HTTPException(422, "Estado operativo no válido")
    cell = db.get(Cell, cell_id)
    if not cell:
        raise HTTPException(404, "Celda no encontrada")
    movement = db.scalar(select(Movement.id).where(Movement.cell_id == cell_id, Movement.exited_at.is_(None)))
    if movement and payload.operational_status != "ACTIVE":
        raise HTTPException(409, "No se puede cambiar una celda ocupada")
    cell.operational_status = payload.operational_status
    db.commit()
    return cell_payload(db, cell)


@app.get("/api/tariffs")
def list_tariffs(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Tarifa vigente de cada tipo de vehículo (la más reciente por tipo)."""
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    rows = db.execute(select(MonthlyTariff, VehicleType).join(VehicleType).where(MonthlyTariff.parking_lot_id == lot_id).order_by(VehicleType.id, MonthlyTariff.effective_from.desc())).all()
    latest_by_type: dict[int, dict[str, Any]] = {}
    for tariff, vehicle_type in rows:
        if vehicle_type.id not in latest_by_type:
            latest_by_type[vehicle_type.id] = tariff_payload(db, tariff, vehicle_type)
    return list(latest_by_type.values())


@app.put("/api/tariffs/{vehicle_type_id}")
def update_tariff(vehicle_type_id: int, amount: Decimal = Query(gt=0), parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    today = date.today()
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


@app.post("/api/tariffs", status_code=201)
def create_tariff(payload: TariffCreate, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Crea una vigencia nueva y cierra la anterior para evitar periodos superpuestos."""
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
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


@app.get("/api/tariffs/history")
def list_tariff_history(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    rows = db.execute(
        select(MonthlyTariff, VehicleType)
        .join(VehicleType, MonthlyTariff.vehicle_type_id == VehicleType.id)
        .where(MonthlyTariff.parking_lot_id == lot_id)
        .order_by(VehicleType.id, MonthlyTariff.effective_from.desc())
    ).all()
    return [tariff_payload(db, tariff, vehicle_type) for tariff, vehicle_type in rows]


@app.get("/api/reports")
def build_report(
    parking_lot_id: int | None = None,
    report_date: date | None = None,
    site_id: int | None = None,
    zone_id: int | None = None,
    vehicle_type_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reporte operativo del día: indicadores, inventario, cobertura y flujo."""
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    if not lot_id:
        raise HTTPException(404, "Parqueadero no encontrado")
    lot = db.get(ParkingLot, lot_id)
    day = report_date or date.today()
    day_start = datetime.combine(day, datetime.min.time())
    day_end = datetime.combine(day, datetime.max.time())

    site_ids = [site.id for site in db.scalars(select(Site).where(Site.parking_lot_id == lot_id)).all()]
    if site_id:
        site_ids = [site_id] if site_id in site_ids else []
    zone_ids = [zone.id for zone in db.scalars(select(Zone).where(Zone.site_id.in_(site_ids))).all()] if site_ids else []
    if zone_id:
        zone_ids = [zone_id] if zone_id in zone_ids else []

    cells = db.scalars(select(Cell).where(Cell.zone_id.in_(zone_ids))).all() if zone_ids else []
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
        .options(joinedload(Payment.contract).joinedload(MonthlyContract.vehicle))
    ).unique().all()
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
    today = date.today()
    expiring_soon = 0
    expired = 0
    active_monthly = 0
    for vehicle in vehicles:
        contract = db.scalar(
            select(MonthlyContract).where(
                MonthlyContract.vehicle_id == vehicle.id,
                MonthlyContract.status == "ACTIVE",
                MonthlyContract.starts_on <= today,
                MonthlyContract.expires_on > today,
            ).order_by(MonthlyContract.expires_on.desc()).limit(1)
        )
        if contract:
            active_monthly += 1
            if (contract.expires_on - today).days <= 30:
                expiring_soon += 1
        else:
            expired += 1

    day_movements = sorted(day_entries + day_exits, key=lambda item: item.entered_at, reverse=True)
    total_movements = len(day_movements)
    start = (page - 1) * page_size
    page_items = day_movements[start:start + page_size]
    employee_names = {employee.id: employee.full_name for employee in db.scalars(select(Employee)).all()}
    movement_rows = [{
        "id": item.id,
        "plate": item.vehicle.plate,
        "type_name": item.vehicle.vehicle_type.name,
        "entered_at": item.entered_at.isoformat(),
        "exited_at": item.exited_at.isoformat() if item.exited_at else None,
        "cell_code": item.cell.code,
        "zone_name": db.get(Zone, item.cell.zone_id).name if item.cell.zone_id else "",
        "entry_employee": employee_names.get(item.entry_employee_id),
        "exit_employee": employee_names.get(item.exit_employee_id),
        "state": "CERRADO" if item.exited_at else "ACTIVO",
    } for item in page_items]

    cells_total = len(active_cells)
    cells_occupied = len([cell for cell in active_cells if cell.id in occupied_cell_ids])
    return {
        "parking_lot": {"id": lot.id, "name": lot.name},
        "report_date": day.isoformat(),
        "cutoff": datetime.now().isoformat(),
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


@app.get("/api/employees")
def list_employees(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    employees = db.scalars(
        select(Employee).where(Employee.parking_lot_id == lot_id)
        .options(joinedload(Employee.shift)).order_by(Employee.active.desc(), Employee.full_name)
    ).unique().all()
    return [employee_payload(employee) for employee in employees]


@app.post("/api/employees", status_code=201)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(ParkingLot, payload.parking_lot_id):
        raise HTTPException(404, "Parqueadero no encontrado")
    if payload.shift_id and not db.get(Shift, payload.shift_id):
        raise HTTPException(422, "El turno indicado no existe")
    employee = Employee(
        parking_lot_id=payload.parking_lot_id,
        document_number=payload.document_number.strip(),
        full_name=payload.full_name.strip(),
        username=payload.username.strip(),
        role=payload.role.strip().upper() or "OPERATOR",
        shift_id=payload.shift_id,
    )
    db.add(employee)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un empleado con ese usuario en este parqueadero")
    db.refresh(employee)
    return employee_payload(employee)


@app.patch("/api/employees/{employee_id}")
def update_employee(employee_id: int, payload: EmployeeUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, "Empleado no encontrado")
    data = payload.model_dump(exclude_unset=True)
    if data.get("full_name") is not None:
        employee.full_name = data["full_name"].strip()
    if data.get("username") is not None:
        employee.username = data["username"].strip()
    if data.get("role") is not None:
        employee.role = data["role"].strip().upper()
    if "shift_id" in data:
        if data["shift_id"] and not db.get(Shift, data["shift_id"]):
            raise HTTPException(422, "El turno indicado no existe")
        employee.shift_id = data["shift_id"]
    if data.get("active") is not None:
        employee.active = data["active"]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un empleado con ese usuario en este parqueadero")
    db.refresh(employee)
    return employee_payload(employee)


@app.get("/api/shifts")
def list_shifts(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    shifts = db.scalars(
        select(Shift).where(Shift.parking_lot_id == lot_id)
        .options(joinedload(Shift.employees)).order_by(Shift.starts_at, Shift.name)
    ).unique().all()
    return [shift_payload(shift) for shift in shifts]


@app.post("/api/shifts", status_code=201)
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


@app.patch("/api/shifts/{shift_id}")
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


@app.get("/api/activity")
def list_activity(parking_lot_id: int | None = None, limit: int = Query(default=10, ge=1, le=100),
                  db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Actividad reciente: ingresos, salidas y pagos con su responsable."""
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
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
        "occurred_at": movement.entered_at.isoformat(),
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
        "occurred_at": movement.exited_at.isoformat() if movement.exited_at else movement.entered_at.isoformat(),
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


@app.post("/api/movements/entry", status_code=201)
def register_entry(payload: EntryCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
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
    today = date.today()
    contract = current_contract(db, vehicle.id)
    if not contract or contract.starts_on > today or contract.expires_on <= today:
        raise HTTPException(409, "La mensualidad está vencida o aún no inicia")
    cell_used = db.scalar(select(Movement.id).where(Movement.cell_id == cell.id, Movement.exited_at.is_(None)))
    if cell_used:
        raise HTTPException(409, "La celda ya está ocupada")
    movement = Movement(vehicle_id=vehicle.id, cell_id=cell.id, notes=payload.notes)
    db.add(movement)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La celda o el vehículo acaba de ser asignado por otro empleado")
    db.refresh(movement)
    return {"id": movement.id, "vehicle_id": vehicle.id, "plate": vehicle.plate, "cell_id": cell.id,
            "cell_code": cell.code, "entered_at": movement.entered_at.isoformat(), "exited_at": None}


@app.post("/api/movements/{movement_id}/exit")
def register_exit(movement_id: int, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    movement = db.scalar(select(Movement).join(Vehicle).where(
        Movement.id == movement_id,
        Movement.exited_at.is_(None),
        Vehicle.parking_lot_id == lot_id,
    ).options(joinedload(Movement.vehicle), joinedload(Movement.cell)))
    if not movement:
        raise HTTPException(404, "No se encontró un ingreso activo con ese identificador")
    exited_at = datetime.now()
    movement.exited_at = exited_at
    db.commit()
    return {"id": movement.id, "plate": movement.vehicle.plate, "cell_code": movement.cell.code,
            "exited_at": exited_at.isoformat()}


@app.get("/api/movements")
def list_movements(active: bool = False, parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = select(Movement).join(Vehicle).join(Cell).join(Zone).join(Site).options(joinedload(Movement.vehicle).joinedload(Vehicle.customer), joinedload(Movement.vehicle).joinedload(Vehicle.vehicle_type), joinedload(Movement.cell))
    if parking_lot_id:
        stmt = stmt.where(Vehicle.parking_lot_id == parking_lot_id)
    if active:
        stmt = stmt.where(Movement.exited_at.is_(None))
    movements = db.scalars(stmt.order_by(Movement.entered_at.desc()).limit(100)).unique().all()
    employee_names = {employee.id: employee.full_name for employee in db.scalars(select(Employee)).all()}
    return [{"id": item.id, "vehicle_id": item.vehicle_id, "plate": item.vehicle.plate,
             "brand": item.vehicle.brand, "color": item.vehicle.color, "type_name": item.vehicle.vehicle_type.name,
             "customer_name": item.vehicle.customer.full_name, "cell_id": item.cell_id, "cell_code": item.cell.code,
             "entered_at": item.entered_at.isoformat(), "exited_at": item.exited_at.isoformat() if item.exited_at else None,
             "entry_employee": employee_names.get(item.entry_employee_id),
             "exit_employee": employee_names.get(item.exit_employee_id)}
            for item in movements]


@app.post("/api/payments", status_code=201)
def register_payment(payload: PaymentCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicle_id).options(joinedload(Vehicle.vehicle_type)))
    if not vehicle:
        raise HTTPException(404, "Vehículo no encontrado")
    today = (payload.paid_at.date() if payload.paid_at else date.today())
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
                      paid_at=payload.paid_at or datetime.now(), period_start=period_start,
                      period_end=period_end, method=payload.method, notes=payload.notes)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"id": payment.id, "vehicle_id": vehicle.id, "plate": vehicle.plate, "amount": money_float(payment.amount),
            "paid_at": payment.paid_at.isoformat(), "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "method": payment.method}


@app.get("/api/payments")
def list_payments(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    payments = db.scalars(select(Payment).join(MonthlyContract).join(Vehicle).where(Vehicle.parking_lot_id == lot_id)
                          .options(joinedload(Payment.contract).joinedload(MonthlyContract.vehicle)).order_by(Payment.paid_at.desc()).limit(100)).unique().all()
    return [{"id": item.id, "plate": item.contract.vehicle.plate, "amount": money_float(item.amount),
             "paid_at": item.paid_at.isoformat(), "period_start": item.period_start.isoformat(),
             "period_end": item.period_end.isoformat(), "method": item.method} for item in payments]


@app.get("/api/novelties")
def list_novelties(parking_lot_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    lot_id = parking_lot_id or db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
    rows = db.execute(select(Novelty, Vehicle, Employee).join(Vehicle, Novelty.vehicle_id == Vehicle.id)
                      .outerjoin(Employee, Novelty.employee_id == Employee.id)
                      .where(Vehicle.parking_lot_id == lot_id).order_by(Novelty.created_at.desc()).limit(100)).all()
    return [{"id": novelty.id, "vehicle_id": novelty.vehicle_id, "plate": vehicle.plate,
             "category": novelty.category, "description": novelty.description,
             "created_at": novelty.created_at.isoformat(), "status": novelty.status,
             "employee_name": employee.full_name if employee else None}
            for novelty, vehicle, employee in rows]


@app.post("/api/novelties", status_code=201)
def create_novelty(payload: NoveltyCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Vehicle, payload.vehicle_id):
        raise HTTPException(404, "Vehículo no encontrado")
    novelty = Novelty(**payload.model_dump())
    db.add(novelty)
    db.commit()
    db.refresh(novelty)
    return {"id": novelty.id, "vehicle_id": novelty.vehicle_id, "category": novelty.category,
            "description": novelty.description, "created_at": novelty.created_at.isoformat(), "status": novelty.status}
