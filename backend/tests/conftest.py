import os
import sys
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Las pruebas corren contra PostgreSQL, en una base propia para no tocar datos
# reales. Se deriva de DATABASE_URL conservando usuario, clave y servidor.
configured = os.environ.get("DATABASE_URL", "").strip()
if not configured:
    raise RuntimeError(
        "Define DATABASE_URL antes de ejecutar las pruebas: "
        "las pruebas usan PostgreSQL y se derivan de esa conexión."
    )

parsed = urlparse(configured)
if not parsed.scheme.startswith("postgresql"):
    raise RuntimeError(f"Las pruebas usan PostgreSQL. DATABASE_URL recibida: {parsed.scheme}://")

os.environ["DATABASE_URL"] = configured.rsplit("/", 1)[0] + "/autos_colombia_test"
# Firma determinista solo para la suite; Nunca se usa en producción.
os.environ["SESSION_SECRET"] = "test-only-secret-" + "x" * 40
# La suite usa una BD aislada: ahí sí se permite la inicialización automática.
os.environ["AUTO_INIT_DB"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app, seed_database  # noqa: E402
from app.models import Employee, ParkingLot, Role, UserAccount, UserRole  # noqa: E402
from app.rbac import ROLE_ADMIN, ROLE_EMPLOYEE  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.views import drop_reporting_views  # noqa: E402

ADMIN_USERNAME = "admin.prueba"
ADMIN_PASSWORD = "AdminTemporal12345!"
EMPLOYEE_USERNAME = "empleado.prueba"
EMPLOYEE_PASSWORD = "EmpleadoTemporal123!"
# Datos sintéticos de prueba (NO son los documentos reales de las personas).
LAURA_USERNAME = "laura.martinez"
LAURA_PASSWORD = "LauraTemporal12345!"
OSCAR_USERNAME = "oscar.valencia"
OSCAR_PASSWORD = "OscarTemporal12345!"


def reset_schema() -> None:
    """Retira la vista propia antes de `drop_all()`: si no, PG bloquea el DROP."""
    with engine.begin() as connection:
        drop_reporting_views(connection)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with Session(bind=engine) as db:
        seed_database(db)


def seed_account(username: str, password: str, full_name: str, role_code: str, document: str) -> int:
    """Crea empleado + cuenta + rol para las pruebas de sesión."""
    with Session(bind=engine) as db:
        lot_id = db.scalar(select(ParkingLot.id).order_by(ParkingLot.id).limit(1))
        role = db.scalar(select(Role).where(Role.code == role_code))
        employee = Employee(
            parking_lot_id=lot_id,
            document_number=document,
            full_name=full_name,
            username=username,
            password_hash=None,
            role=role_code,
            active=True,
        )
        db.add(employee)
        db.flush()
        user = UserAccount(
            parking_lot_id=lot_id,
            employee_id=employee.id,
            username=username,
            password_hash=hash_password(password),
            active=True,
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        return user.id


def login(test_client: TestClient, username: str, password: str) -> str:
    response = test_client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def anon_client():
    """Cliente sin autenticar: comprueba 401 en endpoints protegidos."""
    reset_schema()
    with TestClient(app) as test_client:
        yield test_client
    reset_schema()


@pytest.fixture
def client():
    """Cliente autenticado como ADMINISTRADOR (operaciones administrativas)."""
    reset_schema()
    seed_account(ADMIN_USERNAME, ADMIN_PASSWORD, "Administrador de prueba", ROLE_ADMIN, "AUTH-001")
    with TestClient(app) as test_client:
        token = login(test_client, ADMIN_USERNAME, ADMIN_PASSWORD)
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
    reset_schema()


@pytest.fixture
def employee_client():
    """Cliente autenticado como EMPLEADO (solo permisos operativos)."""
    reset_schema()
    seed_account(EMPLOYEE_USERNAME, EMPLOYEE_PASSWORD, "Empleado de prueba", ROLE_EMPLOYEE, "AUTH-002")
    with TestClient(app) as test_client:
        token = login(test_client, EMPLOYEE_USERNAME, EMPLOYEE_PASSWORD)
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
    reset_schema()


@pytest.fixture
def initial_accounts():
    """Laura (ADMINISTRADOR) y Oscar (EMPLEADO) con documentos sintéticos de prueba."""
    reset_schema()
    seed_account(LAURA_USERNAME, LAURA_PASSWORD, "Laura Martínez", ROLE_ADMIN, "TEST-LAURA-001")
    oscar_id = seed_account(OSCAR_USERNAME, OSCAR_PASSWORD, "Oscar Valencia", ROLE_EMPLOYEE, "TEST-OSCAR-001")
    try:
        with ExitStack() as stack:
            authenticated = {}
            for key, username, password in (
                ("laura", LAURA_USERNAME, LAURA_PASSWORD),
                ("oscar", OSCAR_USERNAME, OSCAR_PASSWORD),
            ):
                client = stack.enter_context(TestClient(app))
                token = login(client, username, password)
                client.headers.update({"Authorization": f"Bearer {token}"})
                authenticated[key] = client
            anon = stack.enter_context(TestClient(app))
            yield {"laura": authenticated["laura"], "oscar": authenticated["oscar"],
                   "anon": anon, "oscar_id": oscar_id}
    finally:
        reset_schema()
