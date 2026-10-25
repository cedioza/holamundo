from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CustomerCreate(BaseModel):
    parking_lot_id: int
    document_type: str = "CC"
    document_number: str = Field(min_length=3, max_length=40)
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = ""
    email: str = ""


class VehicleCreate(BaseModel):
    parking_lot_id: int
    customer_id: int
    vehicle_type_id: int
    plate: str = Field(min_length=4, max_length=12)
    brand: str
    color: str


class CellCreate(BaseModel):
    zone_id: int
    code: str = Field(min_length=1, max_length=30)
    compatible_type_ids: list[int] = Field(min_length=1)
    description: str = ""


class CellStatusUpdate(BaseModel):
    operational_status: str


class SiteCreate(BaseModel):
    parking_lot_id: int
    name: str
    address: str = ""


class ZoneCreate(BaseModel):
    site_id: int
    name: str
    code: str = ""


class EntryCreate(BaseModel):
    vehicle_id: int
    cell_id: int
    notes: str = ""


class PaymentCreate(BaseModel):
    vehicle_id: int
    months: int = Field(default=1, ge=1, le=24)
    method: str = "CASH"
    paid_at: datetime | None = None
    notes: str = ""


class NoveltyCreate(BaseModel):
    vehicle_id: int
    category: str = "GENERAL"
    description: str = Field(min_length=3, max_length=500)


class ParkingLotCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    tax_id: str | None = None
    city: str = ""
    address: str = ""


class ParkingLotUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    tax_id: str | None = None
    city: str | None = None
    address: str | None = None
    active: bool | None = None


class EmployeeCreate(BaseModel):
    parking_lot_id: int
    document_number: str = ""
    full_name: str = Field(min_length=2, max_length=160)
    username: str = Field(min_length=3, max_length=60)
    role: str = "OPERATOR"
    shift_id: int | None = None


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    username: str | None = Field(default=None, min_length=3, max_length=60)
    role: str | None = None
    shift_id: int | None = None
    active: bool | None = None


class ShiftCreate(BaseModel):
    parking_lot_id: int
    name: str = Field(min_length=2, max_length=80)
    starts_at: str = Field(pattern=r"^\d{2}:\d{2}$")
    ends_at: str = Field(pattern=r"^\d{2}:\d{2}$")
    notes: str = ""


class ShiftUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    starts_at: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    ends_at: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    notes: str | None = None
    active: bool | None = None


class TariffCreate(BaseModel):
    vehicle_type_id: int
    amount: Decimal = Field(gt=0)
    effective_from: date
    effective_until: date | None = None
    note: str = ""
