# Requisitos e historias de usuario

## Requisitos funcionales

| Código | Requisito |
| --- | --- |
| RF-01 | Registrar y consultar clientes, evitando documentos duplicados dentro del parqueadero. |
| RF-02 | Registrar vehículos con placa única por parqueadero y asociarlos a un cliente. |
| RF-03 | Buscar/listar vehículos por placa, propietario, marca y estado. |
| RF-04 | Registrar tipos de vehículo, sedes, zonas y celdas configurables. |
| RF-05 | Definir uno o varios tipos compatibles por celda. |
| RF-06 | Consultar capacidad, ocupación y disponibilidad por sede y tipo. |
| RF-07 | Registrar contratos y pagos de mensualidad por vehículo; admitir anticipos consecutivos. |
| RF-08 | Bloquear el ingreso si el contrato no cubre la fecha actual. |
| RF-09 | Registrar ingreso con vehículo, celda compatible, fecha/hora y mensualidad válida. |
| RF-10 | Registrar salida y liberar la celda mediante el cierre del movimiento. |
| RF-11 | Impedir ingreso duplicado del vehículo y uso simultáneo de una celda. |
| RF-12 | Mantener historial de entradas/salidas, pagos y novedades. |
| RF-13 | Crear y administrar más de un parqueadero y mantener sus datos separados. |
| RF-14 | Modificar tarifas manteniendo vigencias e historial de los valores aplicados. |
| RF-15 | Mostrar resumen de clientes, vehículos registrados, vehículos dentro, ocupación y pagos. |
| RF-16 | Crear parqueaderos desde la interfaz y construir su estructura (sede → zona → celda) paso a paso. |
| RF-17 | Registrar el equipo del parqueadero con su turno asignado y su rol. |
| RF-18 | Consultar reportes operativos del parqueadero seleccionado y exportarlos. |
| RF-19 | Administrar vigencias de tarifa por tipo de vehículo sin alterar pagos ya cerrados. |
| RF-20 | Dejar constancia del responsable de cada operación registrada. |

## Requisitos no funcionales

- RNF-01 Integridad: claves foráneas, unicidad y transacción al registrar ingresos.
- RNF-02 Portabilidad: PostgreSQL mediante `DATABASE_URL`; no existe respaldo en SQLite.
- RNF-03 Facilidad de uso: interfaz Angular en español, usable en escritorio y móvil.
- RNF-04 Disponibilidad local: API documentada con OpenAPI/Swagger.
- RNF-05 Trazabilidad: preservar movimientos y pagos, sin borrar el registro por cada salida.
- RNF-06 Seguridad: proteger datos personales y pagos. La versión de prueba local no trae autenticación; no es apta para publicarse con información real.
- RNF-07 Mantenibilidad: API FastAPI, modelos SQLAlchemy, migraciones Alembic y módulos Angular.

## Historias de usuario y aceptación

### HU-01 — Registrar un cliente

Como empleado, quiero registrar datos del cliente para identificarlo y asociarle sus vehículos.

- Requiere tipo y número de documento y nombre.
- El número de documento no se duplica dentro del mismo parqueadero.
- Después de guardar, aparece en el directorio y puede elegirse como propietario.

### HU-02 — Registrar un vehículo

Como empleado, quiero asociar un vehículo a un cliente para verificarlo por placa.

- Requiere placa, marca, color, tipo y cliente del mismo parqueadero.
- La placa se almacena en mayúscula y no se duplica dentro del parqueadero.
- Un vehículo nuevo no puede ingresar hasta tener mensualidad vigente.

### HU-03 — Configurar celdas

Como administrador, quiero inventariar espacios y compatibilidades para que el sistema calcule capacidad real.

- Cada celda tiene código único dentro de su zona.
- Se puede asignar más de un tipo compatible.
- Las celdas en mantenimiento no cuentan como disponibles.
- Una celda ocupada no se puede poner en mantenimiento.

### HU-04 — Registrar pago mensual

Como empleado, quiero registrar el pago de un vehículo y su periodo cubierto.

- El valor se calcula desde la tarifa vigente para el tipo.
- Se guarda fecha, método, importe y periodo.
- El pago anticipado cubre el siguiente periodo consecutivo sin alterar pagos previos.
- El historial muestra el vehículo y el periodo cubierto.

### HU-05 — Registrar ingreso

Como empleado, quiero ingresar un vehículo validando contrato y celda para mantener la ocupación correcta.

- Solo se ofrecen vehículos con mensualidad vigente y sin movimiento activo.
- Solo se ofrecen celdas operativas, disponibles y compatibles.
- Si la mensualidad no cubre el día de ingreso, la operación se rechaza con explicación.
- Dos peticiones simultáneas no pueden asignar la misma celda o vehículo.

### HU-06 — Registrar salida

Como empleado, quiero registrar la salida del vehículo para liberar su celda.

- Solo se puede cerrar un movimiento activo.
- Se guarda la hora de salida.
- Al consultar celdas y ocupación, la celda queda disponible inmediatamente.
- El movimiento se conserva en el historial.

### HU-07 — Consultar ocupación

Como administrador, quiero ver vehículos dentro, celdas libres y ocupadas para tomar decisiones operativas.

- Se distingue cantidad de vehículos registrados de los vehículos dentro.
- La vista muestra el inventario por zona y el total físico sin duplicar celdas compatibles con varios tipos.

### HU-08 — Registrar novedad

Como empleado, quiero dejar una observación ligada a un vehículo para mantener la trazabilidad del turno.

- Se requiere vehículo, categoría y descripción.
- La novedad queda con fecha y estado inicial.

### HU-09 — Administrar distintos parqueaderos

Como administrador, quiero crear y seleccionar parqueaderos independientes para reutilizar la aplicación.

- Un parqueadero nuevo nace vacío: no trae sedes, zonas ni celdas prefijadas.
- La estructura se construye paso a paso en la misma pantalla: primero la sede, luego la zona y luego las celdas con sus tipos compatibles.
- Clientes, placas, celdas y tarifas se consultan dentro del parqueadero seleccionado.
- La capacidad solo cambia al editar su inventario.

### HU-10 — Registrar el equipo y sus turnos

Como administrador, quiero registrar a las personas que operan el parqueadero y en qué turno trabajan para saber quién responde por cada operación.

- Un turno tiene nombre, hora de inicio y hora de fin.
- Una persona se registra con nombre, usuario, rol y turno asignado opcional.
- El usuario es único dentro del parqueadero.
- El turno se puede cambiar o desactivar sin borrar el historial.
- Si no hay personal registrado, la pantalla muestra un estado vacío explícito.

### HU-11 — Consultar reportes operativos

Como administrador, quiero ver el estado del parqueadero en un solo lugar para tomar decisiones sin revisar pantalla por pantalla.

- El reporte se calcula sobre el parqueadero y la fecha seleccionados.
- Incluye inventario por compatibilidad, cobertura de mensualidades, pagos por método y entradas y salidas del día.
- Los datos se pueden exportar a CSV; la exportación a PDF usa el diálogo de impresión del navegador.

### HU-12 — Administrar tarifas y vigencias

Como administrador, quiero cambiar el valor de una tarifa conservando el historial para no alterar pagos ya cobrados.

- Cada tarifa tiene importe, fecha de inicio, fecha de cierre opcional y nota.
- Al crear una vigencia, la anterior queda cerrada el día previo a su inicio.
- No se admiten vigencias que se superpongan con periodos ya cerrados.
- Los contratos y pagos ya registrados conservan el importe que se les aplicó.

### HU-13 — Identificar al responsable de cada operación

Como administrador, quiero saber quién realizó cada movimiento para auditar el turno.

- La actividad reciente lista ingresos, salidas y pagos con su responsable.
- Cuando el responsable no está identificado se informa como sesión de demostración, sin inventar un nombre.

## Supuestos que deben validarse

- Se bloquea el ingreso de mensualidades vencidas o de periodos anticipados aún no iniciados.
- Un periodo pagado comienza el día del pago o al vencimiento anterior si se anticipa; el vencimiento siguiente corresponde al mismo día del ciclo (ajustado al final del mes si aplica).
- Los valores iniciales $250.000 para carro/camioneta y $100.000 para moto son referencias, no tarifas aprobadas.
- Se usa un administrador de demostración sin login únicamente para facilitar la prueba local.
- El equipo del parqueadero no se precarga en la demostración: los nombres de personas y sus documentos se registran en la base local de cada instalación.
