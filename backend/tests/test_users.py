"""Pruebas de autenticación, RBAC y bitácora del módulo Administración · Usuarios.

Cubre: catálogo canónico de roles, hash de contraseñas, cambio obligatorio en el
primer inicio de sesión, 401/403 reales en FastAPI, aislamiento por parqueadero,
sesión persistente y cuentas desactivadas.
"""

from sqlalchemy import select, text

from app.database import engine
from app.models import UserAccount, UserActivity
from app.rbac import ROLE_ADMIN, ROLE_EMPLOYEE
from app.security import verify_password

TEMP_PASSWORD = "TemporalSegura123!"


def role_ids(client, *codes):
    roles = client.get("/api/roles").json()
    return [next(role for role in roles if role["code"] == code)["id"] for code in codes]


def create_employee(client, username, full_name="Persona de prueba", document="1.000.001"):
    response = client.post("/api/employees", json={
        "parking_lot_id": 1,
        "full_name": full_name,
        "document_number": document,
        "username": username,
        "role": ROLE_EMPLOYEE,
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_user(client, employee_id, username, *, roles=(ROLE_EMPLOYEE,), password=TEMP_PASSWORD):
    return client.post("/api/users", json={
        "parking_lot_id": 1,
        "employee_id": employee_id,
        "username": username,
        "password": password,
        "role_ids": role_ids(client, *roles),
    })


def auth_client(anon_client, username, password):
    response = anon_client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    anon_client.headers.update({"Authorization": f"Bearer {response.json()['access_token']}"})
    return response.json()


def test_role_catalog_is_canonical_and_has_only_two_roles(client):
    """Solo ADMINISTRADOR y EMPLEADO, con permisos distintos y sin duplicados."""
    response = client.get("/api/roles")
    assert response.status_code == 200
    codes = [role["code"] for role in response.json()]
    assert codes == [ROLE_ADMIN, ROLE_EMPLOYEE], codes
    admin = next(role for role in response.json() if role["code"] == ROLE_ADMIN)
    employee = next(role for role in response.json() if role["code"] == ROLE_EMPLOYEE)
    for permission in ("OPERATE", "VIEW_AVAILABILITY", "MANAGE_ACCOUNTS", "MANAGE_STRUCTURE",
                       "MANAGE_CELLS", "VIEW_ACTIVITY", "VIEW_HISTORY"):
        assert permission in admin["permissions"]
    for permission in ("MANAGE_ACCOUNTS", "MANAGE_STRUCTURE", "VIEW_ACTIVITY", "VIEW_HISTORY"):
        assert permission not in employee["permissions"]
    for permission in ("OPERATE", "VIEW_AVAILABILITY", "MANAGE_CELLS"):
        assert permission in employee["permissions"]


def test_create_user_hashes_password_and_forces_change(client):
    """La contraseña nunca se guarda en texto plano y el alta exige cambio."""
    employee = create_employee(client, "camila.torres", "Camila Torres")
    response = create_user(client, employee["id"], "camila.torres")
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["username"] == "camila.torres"
    assert payload["role_codes"] == [ROLE_EMPLOYEE]
    assert "password" not in payload and "password_hash" not in payload

    with engine.connect() as connection:
        stored = connection.execute(
            text("select password_hash, must_change_password from users where username = :u"),
            {"u": "camila.torres"},
        ).one()
    assert stored.password_hash != TEMP_PASSWORD
    assert verify_password(TEMP_PASSWORD, stored.password_hash)
    assert stored.must_change_password is True


def test_admin_can_manage_accounts_and_records_activity(client):
    employee = create_employee(client, "diego.ramirez", "Diego Ramírez")
    user = create_user(client, employee["id"], "diego.ramirez", roles=(ROLE_ADMIN,))
    assert user.status_code == 201, user.text
    user_id = user.json()["id"]

    listing = client.get("/api/users").json()
    assert [item["username"] for item in listing] == ["admin.prueba", "diego.ramirez"]
    assert client.get(f"/api/users/{user_id}").json()["role_codes"] == [ROLE_ADMIN]

    changed = client.patch(f"/api/users/{user_id}", json={"role_ids": role_ids(client, ROLE_EMPLOYEE)})
    assert changed.status_code == 200, changed.text
    assert changed.json()["role_codes"] == [ROLE_EMPLOYEE]

    deactivated = client.patch(f"/api/users/{user_id}/status", json={"active": False})
    assert deactivated.json()["active"] is False
    activated = client.patch(f"/api/users/{user_id}/status", json={"active": True})
    assert activated.json()["active"] is True

    activity = client.get("/api/users/activity").json()
    actions = [item["action"] for item in activity]
    for action in ("USER_CREATED", "ROLES_UPDATED", "USER_DEACTIVATED", "USER_ACTIVATED"):
        assert action in actions
    assert all(item["actor"] == "Administrador de prueba" for item in activity)


def test_employee_is_denied_admin_endpoints_but_can_operate_and_manage_cells(employee_client):
    """EMPLEADO opera y gestiona celdas; el resto de administración devuelve 403."""
    forbidden = [
        ("get", "/api/users", None),
        ("get", "/api/roles", None),
        ("get", "/api/users/activity", None),
        ("get", "/api/reports", None),
        ("get", "/api/tariffs/history", None),
        ("get", "/api/employees", None),
        ("get", "/api/shifts", None),
        ("post", "/api/parking-lots", {"name": "No permitido"}),
        ("post", "/api/users", {"username": "x", "password": "y", "role_ids": []}),
    ]
    for method, path, body in forbidden:
        response = getattr(employee_client, method)(path, json=body) if body else getattr(employee_client, method)(path)
        assert response.status_code == 403, f"{method.upper()} {path}: {response.status_code} {response.text}"

    for path in ("/api/dashboard", "/api/customers", "/api/vehicles", "/api/cells",
                 "/api/movements", "/api/novelties", "/api/activity"):
        response = employee_client.get(path)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"

    cell = employee_client.post("/api/cells", json={
        "zone_id": 1, "code": "EMP-01", "compatible_type_ids": [1],
    })
    assert cell.status_code == 201, cell.text
    edited = employee_client.patch(f"/api/cells/{cell.json()['id']}", json={"code": "EMP-01-R"})
    assert edited.status_code == 200, edited.text

    customer = employee_client.post("/api/customers", json={
        "parking_lot_id": 1, "document_type": "CC", "document_number": "EMP-001",
        "full_name": "Cliente operativo", "phone": "", "email": "",
    })
    assert customer.status_code == 201, customer.text


def test_anonymous_and_forged_actor_header_cannot_authorize(anon_client):
    """Sin token no hay acceso; la cabecera heredada X-Actor-Username no autoriza."""
    assert anon_client.get("/api/customers").status_code == 401
    forged = anon_client.get("/api/customers", headers={"X-Actor-Username": "admin.prueba"})
    assert forged.status_code == 401
    assert anon_client.post("/api/parking-lots", json={"name": "x"}).status_code == 401
    assert anon_client.get("/api/health").status_code == 200


def test_inactive_account_cannot_login(anon_client, client):
    employee = create_employee(client, "inactivo.prueba", "Usuario Inactivo", "INACT-1")
    created = create_user(client, employee["id"], "inactivo.prueba")
    assert created.status_code == 201
    client.patch(f"/api/users/{created.json()['id']}/status", json={"active": False})

    response = anon_client.post("/api/auth/login", json={
        "username": "inactivo.prueba", "password": TEMP_PASSWORD,
    })
    assert response.status_code == 403
    assert "desactivada" in response.json()["detail"].lower()


def test_first_login_requires_password_change(anon_client, client):
    """El token se expide, pero bloquea la API hasta cambiar la contraseña temporal."""
    employee = create_employee(client, "cambio.prueba", "Cambio Temporal", "CAMB-1")
    assert create_user(client, employee["id"], "cambio.prueba").status_code == 201

    login = anon_client.post("/api/auth/login", json={
        "username": "cambio.prueba", "password": TEMP_PASSWORD,
    })
    assert login.status_code == 200, login.text
    data = login.json()
    assert data["user"]["must_change_password"] is True
    assert "MANAGE_ACCOUNTS" not in data["user"]["permissions"]
    anon_client.headers.update({"Authorization": f"Bearer {data['access_token']}"})

    assert anon_client.get("/api/customers").status_code == 403
    assert anon_client.get("/api/auth/me").status_code == 200

    new_password = "NuevaSegura987654!"
    changed = anon_client.post("/api/auth/change-password", json={
        "current_password": TEMP_PASSWORD, "new_password": new_password,
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["must_change_password"] is False
    assert anon_client.get("/api/customers").status_code == 200

    anon_client.headers.clear()
    assert anon_client.post("/api/auth/login", json={
        "username": "cambio.prueba", "password": TEMP_PASSWORD,
    }).status_code == 401
    relogin = anon_client.post("/api/auth/login", json={
        "username": "cambio.prueba", "password": new_password,
    })
    assert relogin.status_code == 200


def test_tampered_token_is_rejected(client):
    token = client.headers["Authorization"].split(" ", 1)[1]
    tampered = token[:-2] + ("ab" if not token.endswith("ab") else "cd")
    client.headers.update({"Authorization": f"Bearer {tampered}"})
    assert client.get("/api/customers").status_code == 401


def test_session_reflects_role_and_permissions(client):
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    data = me.json()
    assert data["username"] == "admin.prueba"
    assert data["role_codes"] == [ROLE_ADMIN]
    assert set(data["permissions"]) >= {"OPERATE", "MANAGE_ACCOUNTS", "MANAGE_STRUCTURE"}
    assert data["parking_lot_id"] == 1


def test_access_check_validates_credentials_without_granting_session(anon_client, client):
    employee = create_employee(client, "acceso.prueba", "Acceso Prueba", "ACCESO-1")
    assert create_user(client, employee["id"], "acceso.prueba").status_code == 201
    response = anon_client.post("/api/users/access-check", json={
        "parking_lot_id": 1, "username": "acceso.prueba", "password": TEMP_PASSWORD,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "OK"
    assert anon_client.get("/api/customers").status_code == 401


def test_laura_admin_oscar_employee_and_inactive_account(initial_accounts):
    """Laura administra, Oscar solo opera; al desactivarlo se le corta la API."""
    from conftest import LAURA_PASSWORD, OSCAR_PASSWORD

    laura = initial_accounts["laura"]
    oscar = initial_accounts["oscar"]
    anon = initial_accounts["anon"]

    laura_me = laura.get("/api/auth/me").json()
    assert laura_me["display_name"] == "Laura Martínez"
    assert laura_me["role_codes"] == [ROLE_ADMIN]
    assert "MANAGE_ACCOUNTS" in laura_me["permissions"]
    assert laura.get("/api/users").status_code == 200
    assert laura.get("/api/roles").status_code == 200
    assert laura.get("/api/users/activity").status_code == 200

    oscar_me = oscar.get("/api/auth/me").json()
    assert oscar_me["display_name"] == "Oscar Valencia"
    assert oscar_me["role_codes"] == [ROLE_EMPLOYEE]
    assert oscar_me["permissions"] == ["MANAGE_CELLS", "OPERATE", "VIEW_AVAILABILITY"]
    assert oscar.get("/api/cells").status_code == 200
    assert oscar.get("/api/customers").status_code == 200
    assert oscar.get("/api/users").status_code == 403
    assert oscar.get("/api/roles").status_code == 403
    assert oscar.get("/api/parking-lots").status_code == 200
    assert oscar.post("/api/parking-lots", json={"name": "No permitido"}).status_code == 403
    assert oscar.post("/api/cells", json={
        "zone_id": 1, "code": "OSCAR-01", "compatible_type_ids": [1],
    }).status_code == 201

    deactivated = laura.patch(f"/api/users/{initial_accounts['oscar_id']}/status", json={"active": False})
    assert deactivated.status_code == 200, deactivated.text
    assert oscar.get("/api/customers").status_code == 403
    blocked = anon.post("/api/auth/login", json={
        "username": "oscar.valencia", "password": OSCAR_PASSWORD,
    })
    assert blocked.status_code == 403
    assert "desactivada" in blocked.json()["detail"].lower()
    # Laura sigue operando con su sesión intacta.
    assert laura.get("/api/dashboard").status_code == 200
    assert anon.post("/api/auth/login", json={
        "username": "laura.martinez", "password": LAURA_PASSWORD,
    }).status_code == 200
