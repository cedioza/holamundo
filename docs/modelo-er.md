# Base de datos y relaciones — Autos Colombia

La base permite administrar varios parqueaderos aislados en una sola instancia. El esquema físico está definido en `backend/app/models.py`; la migración inicial está en `backend/alembic/versions/`.

## 1. Diagrama entidad-relación

Este diagrama representa las tablas físicas, sus claves y cardinalidades. Los nombres de entidades están en español; la tabla siguiente muestra su correspondencia con los nombres SQL reales.

```mermaid
erDiagram
    PARQUEADERO ||--o{ SEDE : contiene
    SEDE ||--o{ ZONA : organiza
    ZONA ||--o{ CELDA : contiene

    CELDA ||--o{ CELDA_TIPO_VEHICULO : compatibilidad
    TIPO_VEHICULO ||--o{ CELDA_TIPO_VEHICULO : compatibilidad

    PARQUEADERO ||--o{ CLIENTE : registra
    PARQUEADERO ||--o{ VEHICULO : administra
    CLIENTE ||--o{ VEHICULO : propietario
    TIPO_VEHICULO ||--o{ VEHICULO : clasifica

    PARQUEADERO ||--o{ EMPLEADO : tiene
    PARQUEADERO ||--o{ TURNO : define
    TURNO o|--o{ EMPLEADO : asigna
    PARQUEADERO ||--o{ TARIFA_MENSUAL : define
    TIPO_VEHICULO ||--o{ TARIFA_MENSUAL : tarifa_para
    VEHICULO ||--o{ CONTRATO_MENSUALIDAD : contrata
    TARIFA_MENSUAL ||--o{ CONTRATO_MENSUALIDAD : aplica
    CONTRATO_MENSUALIDAD ||--o{ PAGO : recibe
    EMPLEADO o|--o{ PAGO : registra

    VEHICULO ||--o{ MOVIMIENTO : historial
    CELDA ||--o{ MOVIMIENTO : asignacion
    EMPLEADO o|--o{ MOVIMIENTO : registra_ingreso
    EMPLEADO o|--o{ MOVIMIENTO : registra_salida

    VEHICULO ||--o{ NOVEDAD : presenta
    EMPLEADO o|--o{ NOVEDAD : registra

    PARQUEADERO {
        int id PK
        string name
        string tax_id "nullable"
        string city
        string address
        boolean active
    }
    SEDE {
        int id PK
        int parking_lot_id FK
        string name
        string address
        boolean active
    }
    ZONA {
        int id PK
        int site_id FK
        string name
        string code
    }
    CELDA {
        int id PK
        int zone_id FK
        string code
        string operational_status
        string description
    }
    TIPO_VEHICULO {
        int id PK
        string code UK
        string name
    }
    CELDA_TIPO_VEHICULO {
        int cell_id PK, FK
        int vehicle_type_id PK, FK
    }
    CLIENTE {
        int id PK
        int parking_lot_id FK
        string document_type
        string document_number
        string full_name
        string phone
        string email
        boolean active
    }
    VEHICULO {
        int id PK
        int parking_lot_id FK
        int customer_id FK
        int vehicle_type_id FK
        string plate
        string brand
        string color
        boolean active
    }
    EMPLEADO {
        int id PK
        int parking_lot_id FK
        int shift_id FK "nullable"
        string document_number
        string full_name
        string username
        string password_hash "nullable"
        string role
        boolean active
    }
    TURNO {
        int id PK
        int parking_lot_id FK
        string name
        time starts_at
        time ends_at
        boolean active
        string notes
    }
    TARIFA_MENSUAL {
        int id PK
        int parking_lot_id FK
        int vehicle_type_id FK
        decimal amount
        date effective_from
        date effective_until "nullable"
        string note
    }
    CONTRATO_MENSUALIDAD {
        int id PK
        int vehicle_id FK
        int tariff_id FK
        date starts_on
        date expires_on
        string status
    }
    PAGO {
        int id PK
        int contract_id FK
        int employee_id FK "nullable"
        decimal amount
        datetime paid_at
        date period_start
        date period_end
        string method
        string notes
    }
    MOVIMIENTO {
        int id PK
        int vehicle_id FK
        int cell_id FK
        int entry_employee_id FK "nullable"
        int exit_employee_id FK "nullable"
        datetime entered_at
        datetime exited_at "nullable"
        string notes
    }
    NOVEDAD {
        int id PK
        int vehicle_id FK
        int employee_id FK "nullable"
        datetime created_at
        string category
        string description
        string status
    }
```

### Nombres de las tablas físicas

| Entidad del diagrama | Tabla SQL |
| --- | --- |
| Parqueadero | `parking_lots` |
| Sede | `sites` |
| Zona | `zones` |
| Celda | `cells` |
| Tipo de vehículo | `vehicle_types` |
| Compatibilidad celda/tipo | `cell_vehicle_types` |
| Cliente | `customers` |
| Vehículo | `vehicles` |
| Empleado | `employees` |
| Turno | `shifts` |
| Tarifa mensual | `monthly_tariffs` |
| Contrato de mensualidad | `monthly_contracts` |
| Pago | `payments` |
| Movimiento | `movements` |
| Novedad | `novelties` |

## 2. Cómo se construye y conecta la base

```mermaid
flowchart LR
    Operador[Operador en navegador] --> UI[Angular 22]
    UI -->|HTTP JSON| API[FastAPI]
    API --> Validacion[Esquemas Pydantic]
    API --> ORM[Modelos SQLAlchemy 2]
    ORM --> Sesion[Engine y SessionLocal]
    Sesion -->|DATABASE_URL (.env)| PostgreSQL[(PostgreSQL)]

    CodigoModelos[backend/app/models.py] --> Metadata[Metadatos SQLAlchemy]
    Metadata --> Alembic[Alembic: migraciones versionadas]
    Alembic --> PostgreSQL

    Inicio[run-local.sh] --> Migracion[alembic upgrade head]
    Migracion --> API
    API --> Seed[Inicialización de datos demo<br/>solo si no hay parqueaderos]
    Seed --> PostgreSQL
```

### Arranque paso a paso

1. `run-local.sh` prepara el entorno Python y las dependencias del frontend si aún no existen.
2. Ejecuta `alembic upgrade head`; Alembic crea o actualiza las tablas según las migraciones versionadas.
3. Inicia FastAPI y Angular. Al iniciar, la API crea las tablas que falten y agrega datos **de demostración** solo cuando la base no tiene parqueaderos.
4. SQLAlchemy abre sesiones y lee/escribe en el motor indicado por `DATABASE_URL`.

Configuración de la conexión (archivo `.env`, no versionado):

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:tu_clave@127.0.0.1:5432/autos_colombia_app
```

La misma variable configura la base de datos; el modelo relacional no cambia. Si falta o apunta a otro motor, el backend se detiene con un mensaje claro en lugar de crear un respaldo alternativo.

## 3. Reglas e integridad

- `parking_lots` es el límite de aislamiento: clientes, vehículos, empleados y tarifas se asocian a un parqueadero. La API verifica que las asociaciones de una operación pertenezcan al mismo parqueadero.
- `UNIQUE(parking_lot_id, document_number)` evita documentos repetidos dentro de un parqueadero.
- `UNIQUE(parking_lot_id, plate)` evita placas repetidas dentro de un parqueadero.
- `UNIQUE(zone_id, code)` evita códigos de celda repetidos dentro de una zona.
- `cell_vehicle_types` materializa la relación muchos-a-muchos entre celdas y tipos de vehículo mediante una clave primaria compuesta. Una celda compatible con varios tipos sigue siendo un solo espacio físico.
- Índices únicos parciales en `movements` permiten como máximo un movimiento activo por vehículo y por celda; un movimiento activo es aquel cuyo `exited_at` es `NULL`.
- PostgreSQL aplica las claves foráneas de forma nativa en cada operación.
- La capacidad no es un número fijo: se obtiene del inventario de celdas activas. La ocupación se deriva de movimientos activos, no se almacena duplicada en la celda.
- `employees.shift_id` es opcional: una persona puede estar registrada sin turno asignado. Los turnos (`shifts`) pertenecen al parqueadero y definen el horario de referencia del equipo.
- Tarifas y pagos guardan vigencias e importes aplicados para conservar el historial cuando se actualice una tarifa. Al crear una vigencia se cierra la anterior el día anterior a su inicio; el solapamiento entre periodos ya cerrados se rechaza.

## 4. Datos provisionales

La base local inicial tiene 8 celdas para carro/camioneta y 4 para moto, más tarifas de demostración. No representan la capacidad ni precios confirmados de Autos Colombia. La versión local no tiene autenticación: no introducir datos personales reales ni exponerla en Internet.
