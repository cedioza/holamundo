from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import engine
from app.models import ParkingLot


def create_customer(client, document="100200300"):
    response = client.post("/api/customers", json={
        "parking_lot_id": 1,
        "document_type": "CC",
        "document_number": document,
        "full_name": "Cliente de prueba",
        "phone": "3001234567",
        "email": "prueba@example.test",
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_vehicle(client, customer_id, plate="ABC123"):
    response = client.post("/api/vehicles", json={
        "parking_lot_id": 1,
        "customer_id": customer_id,
        "vehicle_type_id": 1,
        "plate": plate,
        "brand": "Prueba",
        "color": "Verde",
    })
    assert response.status_code == 201, response.text
    return response.json()


def register_month(client, vehicle_id, months=1):
    response = client.post("/api/payments", json={"vehicle_id": vehicle_id, "months": months, "method": "CASH"})
    assert response.status_code == 201, response.text
    return response.json()


def test_entry_payment_exit_and_cell_reuse(client):
    customer = create_customer(client)
    vehicle = create_vehicle(client, customer["id"])
    payment = register_month(client, vehicle["id"])
    assert payment["amount"] == 250000
    assert payment["period_start"] <= payment["period_end"]
    prepaid = register_month(client, vehicle["id"])
    assert prepaid["period_start"] > payment["period_start"]
    assert client.get("/api/vehicles").json()[0]["monthly_status"] == "VIGENTE"

    cells = client.get("/api/cells").json()
    cell = next(item for item in cells if item["code"] == "C-01")
    entry = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": cell["id"]})
    assert entry.status_code == 201, entry.text
    assert client.get("/api/dashboard").json()["vehicles_inside"] == 1

    second_entry = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": cell["id"]})
    assert second_entry.status_code == 409

    exit_response = client.post(f"/api/movements/{entry.json()['id']}/exit", json={})
    assert exit_response.status_code == 200
    assert client.get("/api/dashboard").json()["vehicles_inside"] == 0
    assert next(item for item in client.get("/api/cells").json() if item["id"] == cell["id"])["occupied"] is False


def test_cannot_enter_without_valid_payment_or_use_incompatible_cell(client):
    customer = create_customer(client)
    vehicle = create_vehicle(client, customer["id"])
    cells = client.get("/api/cells").json()
    car_cell = next(item for item in cells if item["code"] == "C-01")
    unpaid = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": car_cell["id"]})
    assert unpaid.status_code == 409

    moto_cell = next(item for item in cells if item["code"] == "M-01")
    register_month(client, vehicle["id"])
    incompatible = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": moto_cell["id"]})
    assert incompatible.status_code == 422


def test_entry_is_blocked_until_prepaid_period_starts(client):
    customer = create_customer(client)
    vehicle = create_vehicle(client, customer["id"])
    future_payment = client.post("/api/payments", json={
        "vehicle_id": vehicle["id"], "months": 1, "method": "CASH",
        "paid_at": (datetime.now() + timedelta(days=10)).isoformat(),
    })
    assert future_payment.status_code == 201, future_payment.text
    assert client.get("/api/vehicles").json()[0]["monthly_status"] == "ANTICIPADA"

    cell = next(item for item in client.get("/api/cells").json() if item["code"] == "C-01")
    not_yet_covered = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": cell["id"]})
    assert not_yet_covered.status_code == 409


def test_prepaid_payment_updates_vehicle_and_contract_coverage(client):
    """Un pago anticipado debe reflejarse en vehículos y mensualidades."""
    customer = create_customer(client)
    vehicle = create_vehicle(client, customer["id"])
    first = register_month(client, vehicle["id"])
    second = register_month(client, vehicle["id"], months=3)

    expected_expiry = (datetime.fromisoformat(second["period_end"]).date() + timedelta(days=1)).isoformat()
    assert expected_expiry > first["period_end"]

    listed = client.get("/api/vehicles").json()[0]
    assert listed["monthly_status"] == "VIGENTE"
    assert listed["expires_on"] == expected_expiry

    row = next(item for item in client.get("/api/contracts").json() if item["plate"] == "ABC123")
    assert row["monthly_status"] == "VIGENTE"
    assert row["period_start"] == second["period_start"]
    assert row["period_end"] == second["period_end"]
    assert row["coverage_end"] == expected_expiry
    assert row["expiring_soon"] is False

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["monthly_expiring_soon"] == 0


def test_admin_can_operate_on_another_parking_lot(client):
    """Un administrador puede seleccionar otro parqueadero y trabajar en su contexto."""
    second_lot = client.post("/api/parking-lots", json={"name": "Parqueadero de prueba", "tax_id": "900123456"})
    assert second_lot.status_code == 201, second_lot.text
    lot_id = second_lot.json()["id"]

    bootstrap = client.get(f"/api/bootstrap?parking_lot_id={lot_id}")
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json()["parking_lot"]["id"] == lot_id
    assert client.get(f"/api/zones?parking_lot_id={lot_id}").json() == []
    assert client.get(f"/api/cells?parking_lot_id={lot_id}").json() == []
    assert client.get(f"/api/dashboard?parking_lot_id={lot_id}").status_code == 200

    customer = client.post("/api/customers", json={
        "parking_lot_id": lot_id, "document_type": "CC", "document_number": "100200300",
        "full_name": "Cliente de otro parqueadero", "phone": "", "email": "",
    })
    assert customer.status_code == 201, customer.text
    assert client.get("/api/customers?parking_lot_id=1").json() == []
    assert [item["id"] for item in client.get(f"/api/customers?parking_lot_id={lot_id}").json()] == [customer.json()["id"]]
    assert client.get("/api/bootstrap").json()["parking_lot"]["id"] == 1

    first_lot_customer = create_customer(client, document="FIRST-LOT")
    vehicle = create_vehicle(client, first_lot_customer["id"], plate="FIRST1")
    register_month(client, vehicle["id"])
    cell = next(item for item in client.get("/api/cells?parking_lot_id=1").json() if item["code"] == "C-01")
    movement = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": cell["id"]}).json()
    cross_lot_exit = client.post(f"/api/movements/{movement['id']}/exit?parking_lot_id={lot_id}", json={})
    assert cross_lot_exit.status_code == 404
    assert client.get("/api/movements?active=true&parking_lot_id=1").json()


def test_employee_cannot_operate_on_another_parking_lot(employee_client):
    """El cambio de contexto sigue reservado a cuentas con MANAGE_STRUCTURE."""
    with Session(bind=engine) as db:
        lot = ParkingLot(name="Parqueadero ajeno", city="Medellín")
        db.add(lot)
        db.commit()
        lot_id = lot.id

    assert employee_client.get(f"/api/bootstrap?parking_lot_id={lot_id}").status_code == 403
    site = employee_client.post("/api/sites", json={
        "parking_lot_id": lot_id, "name": "Sede ajena", "address": "Calle 10",
    })
    assert site.status_code == 403


def test_admin_can_build_new_parking_lot_from_another_lot_session(client):
    """HU-09: el parqueadero recién creado se configura desde la misma sesión."""
    lot = client.post("/api/parking-lots", json={"name": "Parqueadero en construcción", "city": "Medellín"})
    assert lot.status_code == 201, lot.text
    lot_id = lot.json()["id"]

    bootstrap = client.get(f"/api/bootstrap?parking_lot_id={lot_id}")
    assert bootstrap.status_code == 200, bootstrap.text
    type_id = bootstrap.json()["vehicle_types"][0]["id"]

    site = client.post("/api/sites", json={"parking_lot_id": lot_id, "name": "Sede norte", "address": "Calle 10"})
    assert site.status_code == 201, site.text
    site_id = site.json()["id"]

    zone = client.post("/api/zones", json={"site_id": site_id, "name": "Zona autos", "code": "au"},
                       params={"parking_lot_id": lot_id})
    assert zone.status_code == 201, zone.text
    zone_id = zone.json()["id"]

    cell = client.post("/api/cells", json={
        "zone_id": zone_id, "code": "au-01", "compatible_type_ids": [type_id],
    }, params={"parking_lot_id": lot_id})
    assert cell.status_code == 201, cell.text

    summary = next(item for item in client.get("/api/parking-lots").json() if item["id"] == lot_id)
    assert summary["sites_count"] == 1
    assert summary["zones_count"] == 1
    assert summary["cells_total"] == 1


def test_duplicate_plate_and_cell_maintenance_rules(client):
    customer = create_customer(client)
    vehicle = create_vehicle(client, customer["id"])
    duplicate = client.post("/api/vehicles", json={
        "parking_lot_id": 1, "customer_id": customer["id"], "vehicle_type_id": 1,
        "plate": "ABC123", "brand": "Otra", "color": "Azul",
    })
    assert duplicate.status_code == 409

    cell = next(item for item in client.get("/api/cells").json() if item["code"] == "C-01")
    updated = client.patch(f"/api/cells/{cell['id']}/status", json={"operational_status": "MAINTENANCE"})
    assert updated.status_code == 200
    assert updated.json()["operational_status"] == "MAINTENANCE"
    assert client.get("/api/dashboard").json()["cells_total"] == 11
