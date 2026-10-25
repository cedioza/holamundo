# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated: Angular frontend, FastAPI backend, SQLAlchemy/Alembic, PostgreSQL for local development and deployment.

## Users

- Empleados que registran clientes, vehículos, pagos y movimientos durante la operación del parqueadero.
- Administradores que configuran celdas, tarifas y empleados, y consultan ocupación e historial.

## Product Purpose

Autos Colombia es un sistema web para centralizar la administración de uno o más parqueaderos que trabajan mediante mensualidades. El éxito significa registrar con precisión quién es el cliente, qué vehículos tiene, si su mensualidad está vigente, dónde está estacionado el vehículo y qué cupos permanecen disponibles.

## Positioning

La capacidad y la compatibilidad se derivan de las celdas configuradas por sede, lo que permite adaptar el sistema a diferentes distribuciones y establecimientos sin cambiar el código. La administración del parqueadero (estructura, equipo, reportes y tarifas) vive en un módulo propio, separado del flujo operativo de entrada y salida.

## Operating Context

Los empleados consultan vehículos por placa, verifican la relación con el cliente y la mensualidad, asignan una celda al ingreso y la liberan al registrar la salida. Administradores necesitan distinguir vehículos registrados de vehículos actualmente dentro del parqueadero.

## Capabilities and Constraints

- Gestión de parqueaderos, sedes, zonas, celdas, compatibilidades, clientes, vehículos, mensualidades, pagos y movimientos.
- Módulo de administración con cuatro pantallas: parqueaderos (creación y estructura sede → zona → celda), empleados y turnos, reportes operativos y tarifas y vigencias.
- Un parqueadero nuevo nace vacío: su estructura (sedes, zonas, celdas) se construye en la misma pantalla, paso a paso, para que la capacidad refleje el inventario real.
- Los empleados y turnos se registran desde la interfaz; la demostración no siembra personas, por lo que la pantalla inicia con un estado vacío explícito.
- Cada tarifa tiene vigencia: al crear una nueva se cierra la anterior el día anterior a su inicio y no se admiten solapamientos con periodos cerrados.
- Los reportes se calculan sobre los datos del parqueadero seleccionado y se pueden exportar a CSV; la exportación a PDF usa el diálogo de impresión del navegador.
- El servicio es por mensualidad; no se ofrecerá cobro por horas en el alcance inicial.
- Cada cliente puede tener varios vehículos y cada vehículo mantiene control individual de mensualidad.
- La ocupación se deriva de movimientos activos; el estado operativo de una celda es independiente de su ocupación.
- El resumen operativo replica el diseño de Figma: cuatro indicadores, estado de operación (anillo de ocupación física y disponibilidad por tipo), tres cuadros de mensualidades (vigentes, próximas a vencer en 7 días y vencidas) y tabla de movimientos recientes.
- La pantalla de ocupación y celdas replica el frame de Figma "Operación · Ocupación y celdas": cuatro indicadores de inventario, búsqueda por código o placa con filtros de sede, zona y tipo, un mapa de celdas agrupado por zonas con su leyenda de estados y una columna de detalle con el estado y la configuración de la celda enfocada.
- La ocupación física se mide sobre el inventario total de celdas (operativas más mantenimiento) y la disponibilidad por tipo separa las celdas exclusivas de motos de las de carros y camionetas, sin duplicar celdas compatibles con varios tipos.
- El mapa de celdas solo dibuja las celdas registradas en la base de datos: el inventario de demostración (12 celdas etiquetadas como "demo") se muestra con el aviso de capacidad por confirmar, sin inventar espacios ni códigos.
- La pantalla de clientes replica el frame de Figma "Clientes · Directorio": tres indicadores (clientes registrados, vehículos asociados y clientes con más de un vehículo), pestañas de corte, campo de búsqueda, filtros de estado y de orden, tabla de clientes, paginación, aviso de alcance y enlace al módulo de vehículos.
- La tabla de clientes se deriva de los datos reales (`/api/customers` y `/api/vehicles` agrupados por cliente) y resume el estado de mensualidades de cada cliente con su pluralidad real: "Sin contratos", "Vigente", "N vigentes · $importe", "Próxima a vencer", "Vencida" o la mezcla de ambos estados.
- El alta y la edición de clientes se hacen en un modal con el patrón de diálogo ya usado en el módulo de celdas; "Consultar" abre la ficha del cliente con sus vehículos y "Editar" abre el mismo formulario en modo edición.
- La demostración no siembra clientes ni vehículos: el directorio inicia con un estado vacío honesto (0 clientes) en lugar de datos ficticios verosímiles.
- El buscador global del encabezado también filtra el directorio de clientes (por nombre, documento, celular o placa) cuando el campo de búsqueda de la página está vacío.
- Clientes y placas serán únicos dentro del parqueadero, no globalmente.
- Las tarifas y el inventario de celdas serán configurables por parqueadero.
- Datos de capacidad mencionados (80 carros/camionetas y 10 motos) son provisionales y requieren verificación física; no se codificarán como límites fijos.
- Se asume inicialmente que una mensualidad vencida bloquea el ingreso normal; no se implementará excepción de autorización hasta confirmar una política distinta.
- Los anticipos se registrarán asociados a periodos futuros, evitando alterar el historial de pagos.
- Las novedades podrán asociarse a vehículos y empleados.

## Evidence on Hand

No se proporcionaron logos, identidad visual, datos reales de clientes ni contenido comercial aprobado. Cualquier dato de demostración debe ser sintético y claramente identificable como tal.

## Product Principles

- Evitar asignaciones duplicadas mediante validación transaccional e integridad de datos.
- Hacer configurable por parqueadero la capacidad, compatibilidad y tarifa.
- Mantener trazabilidad de entradas, salidas, pagos y novedades.
- Mostrar claramente la diferencia entre vehículos registrados y ocupación actual.
- No inventar ni presentar información de demostración como información real.
- Cuando falte un dato confirmado (personal, responsables, precios), mostrar un estado vacío honesto en lugar de datos ficticios verosímiles.
- Mantener el menú lateral y el área de contenido como áreas de desplazamiento independientes, de modo que el usuario pueda recorrer módulos largos sin perder la barra superior ni la referencia del menú.
