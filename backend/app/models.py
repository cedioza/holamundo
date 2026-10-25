from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Table, Column, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


cell_vehicle_types = Table(
    "cell_vehicle_types",
    Base.metadata,
    Column("cell_id", ForeignKey("cells.id", ondelete="CASCADE"), primary_key=True),
    Column("vehicle_type_id", ForeignKey("vehicle_types.id", ondelete="CASCADE"), primary_key=True),
)


class ParkingLot(Base):
    __tablename__ = "parking_lots"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tax_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    city: Mapped[str] = mapped_column(String(80), default="")
    address: Mapped[str] = mapped_column(String(160), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sites: Mapped[list["Site"]] = relationship(back_populates="parking_lot", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(240), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    parking_lot: Mapped[ParkingLot] = relationship(back_populates="sites")
    zones: Mapped[list["Zone"]] = relationship(back_populates="site", cascade="all, delete-orphan")


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(20), default="")
    site: Mapped[Site] = relationship(back_populates="zones")
    cells: Mapped[list["Cell"]] = relationship(back_populates="zone", cascade="all, delete-orphan")


class VehicleType(Base):
    __tablename__ = "vehicle_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(60))
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="vehicle_type")


class Cell(Base):
    __tablename__ = "cells"
    __table_args__ = (UniqueConstraint("zone_id", "code", name="uq_cell_code_per_zone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    code: Mapped[str] = mapped_column(String(30))
    operational_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    description: Mapped[str] = mapped_column(String(200), default="")
    zone: Mapped[Zone] = relationship(back_populates="cells")
    compatible_types: Mapped[list[VehicleType]] = relationship(secondary=cell_vehicle_types)
    movements: Mapped[list["Movement"]] = relationship(back_populates="cell")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("parking_lot_id", "document_number", name="uq_customer_document_per_parking"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    document_type: Mapped[str] = mapped_column(String(20), default="CC")
    document_number: Mapped[str] = mapped_column(String(40))
    full_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="customer")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("parking_lot_id", "plate", name="uq_vehicle_plate_per_parking"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    plate: Mapped[str] = mapped_column(String(12), index=True)
    brand: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    customer: Mapped[Customer] = relationship(back_populates="vehicles")
    vehicle_type: Mapped[VehicleType] = relationship(back_populates="vehicles")
    contracts: Mapped[list["MonthlyContract"]] = relationship(back_populates="vehicle")
    movements: Mapped[list["Movement"]] = relationship(back_populates="vehicle")


class Shift(Base):
    """Turno operativo con horario de referencia para el equipo del parqueadero."""

    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    name: Mapped[str] = mapped_column(String(80))
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(240), default="")
    employees: Mapped[list["Employee"]] = relationship(back_populates="shift")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("parking_lot_id", "username", name="uq_employee_username_per_parking"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    document_number: Mapped[str] = mapped_column(String(40), default="")
    full_name: Mapped[str] = mapped_column(String(160))
    username: Mapped[str] = mapped_column(String(60))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default="EMPLOYEE")
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    shift: Mapped["Shift | None"] = relationship(back_populates="employees")


class MonthlyTariff(Base):
    __tablename__ = "monthly_tariffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    parking_lot_id: Mapped[int] = mapped_column(ForeignKey("parking_lots.id"))
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(240), default="")


class MonthlyContract(Base):
    __tablename__ = "monthly_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    tariff_id: Mapped[int] = mapped_column(ForeignKey("monthly_tariffs.id"))
    starts_on: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    vehicle: Mapped[Vehicle] = relationship(back_populates="contracts")
    tariff: Mapped[MonthlyTariff] = relationship()
    payments: Mapped[list["Payment"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("monthly_contracts.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(30), default="CASH")
    notes: Mapped[str] = mapped_column(String(240), default="")
    contract: Mapped[MonthlyContract] = relationship(back_populates="payments")


class Movement(Base):
    __tablename__ = "movements"
    __table_args__ = (
        Index("uq_active_movement_vehicle", "vehicle_id", unique=True, sqlite_where=(Column("exited_at").is_(None)), postgresql_where=(Column("exited_at").is_(None))),
        Index("uq_active_movement_cell", "cell_id", unique=True, sqlite_where=(Column("exited_at").is_(None)), postgresql_where=(Column("exited_at").is_(None))),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    cell_id: Mapped[int] = mapped_column(ForeignKey("cells.id"))
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entry_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    exit_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    notes: Mapped[str] = mapped_column(String(240), default="")
    vehicle: Mapped[Vehicle] = relationship(back_populates="movements")
    cell: Mapped[Cell] = relationship(back_populates="movements")


class Novelty(Base):
    __tablename__ = "novelties"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    category: Mapped[str] = mapped_column(String(40), default="GENERAL")
    description: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
