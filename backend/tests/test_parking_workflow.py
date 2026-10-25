from datetime import datetime, timedelta


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


def test_parking_lots_keep_inventory_and_customers_separate(client):
    second_lot = client.post("/api/parking-lots", json={"name": "Parqueadero de prueba", "tax_id": "900123456"})
    assert second_lot.status_code == 201, second_lot.text
    lot_id = second_lot.json()["id"]

    second_bootstrap = client.get(f"/api/bootstrap?parking_lot_id={lot_id}").json()
    assert second_bootstrap["parking_lot"]["name"] == "Parqueadero de prueba"
    assert second_bootstrap["sites"] == []
    assert client.get(f"/api/zones?parking_lot_id={lot_id}").json() == []
    assert client.get(f"/api/cells?parking_lot_id={lot_id}").json() == []
    assert client.get(f"/api/dashboard?parking_lot_id={lot_id}").json()["cells_total"] == 0

    customer = client.post("/api/customers", json={
        "parking_lot_id": lot_id, "document_type": "CC", "document_number": "100200300",
        "full_name": "Cliente de otro parqueadero", "phone": "", "email": "",
    })
    assert customer.status_code == 201
    assert client.get("/api/customers?parking_lot_id=1").json() == []
    assert len(client.get(f"/api/customers?parking_lot_id={lot_id}").json()) == 1

    first_lot_customer = create_customer(client, document="FIRST-LOT")
    vehicle = create_vehicle(client, first_lot_customer["id"], plate="FIRST1")
    register_month(client, vehicle["id"])
    cell = next(item for item in client.get("/api/cells?parking_lot_id=1").json() if item["code"] == "C-01")
    movement = client.post("/api/movements/entry", json={"vehicle_id": vehicle["id"], "cell_id": cell["id"]}).json()
    cross_lot_exit = client.post(f"/api/movements/{movement['id']}/exit?parking_lot_id={lot_id}", json={})
    assert cross_lot_exit.status_code == 404
    assert client.get("/api/movements?active=true&parking_lot_id=1").json()


def test_new_parking_lot_is_built_with_sites_zones_and_cells(client):
    """Un parqueadero nuevo nace vacío y su inventario se construye paso a paso."""
    lot = client.post("/api/parking-lots", json={"name": "Parqueadero en construcción", "city": "Medellín"})
    assert lot.status_code == 201, lot.text
    lot_id = lot.json()["id"]

    site = client.post("/api/sites", json={"parking_lot_id": lot_id, "name": "Sede norte", "address": "Calle 10"})
    assert site.status_code == 201, site.text
    zone = client.post("/api/zones", json={"site_id": site.json()["id"], "name": "Zona autos", "code": "au"})
    assert zone.status_code == 201, zone.text
    assert zone.json()["code"] == "AU"
    cell = client.post("/api/cells", json={
        "zone_id": zone.json()["id"], "code": "au-01", "compatible_type_ids": [1],
    })
    assert cell.status_code == 201, cell.text
    assert cell.json()["code"] == "AU-01"

    summary = next(item for item in client.get("/api/parking-lots").json() if item["id"] == lot_id)
    assert summary["sites_count"] == 1
    assert summary["zones_count"] == 1
    assert summary["cells_total"] == 1
    assert summary["cells_available"] == 1
    assert client.get(f"/api/dashboard?parking_lot_id={lot_id}").json()["cells_total"] == 1


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
