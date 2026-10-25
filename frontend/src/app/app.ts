import { CommonModule, DatePipe, registerLocaleData } from '@angular/common';
import localeEsCo from '@angular/common/locales/es-CO';
import type { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, ElementRef, type OnInit, ViewChild, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  type ActivityItem,
  type Bootstrap,
  type Cell,
  type ContractRow,
  type Customer,
  type Dashboard,
  type Employee,
  type Movement,
  type Novelty,
  type OccupancyGroup,
  type ParkingLotSummary,
  type Payment,
  type Report,
  type Shift,
  type Site,
  type Tariff,
  type TariffHistory,
  type Vehicle,
  type VehicleType,
  type Zone,
} from './api.service';

registerLocaleData(localeEsCo);

type Page =
  | 'dashboard'
  | 'vehicles'
  | 'customers'
  | 'cells'
  | 'history'
  | 'payments'
  | 'payments-register'
  | 'novelties'
  | 'settings'
  | 'entry'
  | 'exit'
  | 'parking-lots'
  | 'employees'
  | 'reports'
  | 'tariffs';

/** Pestañas del módulo de empleados y turnos. */
type EmployeeTab = 'team' | 'roles' | 'activity';

/** Pestañas del módulo de configuración operativa. */
type ConfigTab = 'inventory' | 'types' | 'rules' | 'roles';

/** Pestañas del directorio de clientes. */
type CustomerTab = 'all' | 'inside' | 'expired';

/** Filtro por estado de mensualidad del directorio de clientes. */
type CustomerStatusFilter = 'ALL' | 'VIGENTE' | 'ANTICIPADA' | 'VENCIDA' | 'SIN';

/** Orden del directorio de clientes. */
type CustomerSort = 'recent' | 'name' | 'document';

/** Pestañas del módulo de vehículos: directorio de la flota y búsqueda global. */
type VehicleTab = 'directory' | 'search';

/** Filtro de tipo de vehículo de la búsqueda global. */
type VehicleTypeFilter = 'TODOS' | string;

/** Filtro de situación del vehículo dentro o fuera del parqueadero. */
type VehicleSituationFilter = 'TODOS' | 'DENTRO' | 'FUERA';

/** Filtro de marca de vehículo de la búsqueda global. */
type VehicleBrandFilter = 'TODOS' | string;

/** Pestañas de mensualidades: todas, vigentes, próximas a vencer y vencidas. */
type MonthlyTab = 'all' | 'active' | 'expiring' | 'expired';

/** Filtro por tipo de vehículo en la pantalla de mensualidades. */
type MonthlyTypeFilter = 'TODOS' | string;

/** Filtro de cobertura contractual en la pantalla de mensualidades. */
type MonthlyCoverageFilter = 'TODAS' | 'ACTIVO' | 'POR_VENCER' | 'VENCIDO' | 'SIN';

/** Fila del resultado de búsqueda: un propietario y los vehículos que conserva. */
interface VehicleOwnerGroup {
  customerId: number;
  customerName: string;
  documentLabel: string;
  vehicles: Vehicle[];
}

/** Pestañas del módulo de tarifas y vigencias. */
type TariffTab = 'active' | 'history';

interface NavItem {
  id: Page;
  label: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

interface PageMeta {
  ruta: string;
  titulo: string;
  contexto: string;
}

/** Estado de una comprobación de ingreso. */
type CheckState = 'ok' | 'fail' | 'pending';

/** Comprobación de ingreso: texto explicativo y estado de la condición. */
interface EntryCheck {
  label: string;
  state: CheckState;
}

/** Zona del mapa de celdas con las celdas que ya superaron los filtros. */
interface MapZone {
  id: number;
  name: string;
  kindLabel: string;
  cells: Cell[];
}

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule, DatePipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private readonly api = inject(ApiService);
  private readonly changeDetector = inject(ChangeDetectorRef);
  /** Area de contenido con scroll propio: se reinicia al cambiar de modulo. */
  @ViewChild('workspace') private workspaceRef?: ElementRef<HTMLElement>;
  readonly navSections: NavSection[] = [
    {
      label: 'OPERACIÓN',
      items: [
        { id: 'dashboard', label: 'Resumen operativo' },
        { id: 'cells', label: 'Ocupación y celdas' },
        { id: 'entry', label: 'Registrar ingreso' },
        { id: 'exit', label: 'Registrar salida' },
      ],
    },
    {
      label: 'GESTIÓN',
      items: [
        { id: 'customers', label: 'Clientes' },
        { id: 'vehicles', label: 'Vehículos' },
        { id: 'payments', label: 'Mensualidades' },
        { id: 'history', label: 'Historial' },
        { id: 'novelties', label: 'Novedades' },
      ],
    },
    {
      label: 'ADMINISTRACIÓN',
      items: [
        { id: 'parking-lots', label: 'Parqueaderos' },
        { id: 'employees', label: 'Empleados y turnos' },
        { id: 'reports', label: 'Reportes' },
        { id: 'settings', label: 'Configuración' },
        { id: 'tariffs', label: 'Tarifas y vigencias' },
      ],
    },
  ];
  readonly pageMeta: Record<Page, PageMeta> = {
    dashboard: {
      ruta: 'OPERACIÓN / RESUMEN OPERATIVO',
      titulo: 'Resumen operativo',
      contexto: 'Todo listo para el turno de hoy. Este es el estado actual.',
    },
    cells: {
      ruta: 'OPERACIÓN / INVENTARIO / OCUPACIÓN Y CELDAS',
      titulo: 'Ocupación y celdas',
      contexto:
        'Inventario de Sede principal. Selecciona una celda para consultar su detalle.',
    },
    customers: {
      ruta: 'CLIENTES Y VEHÍCULOS / CLIENTES',
      titulo: 'Clientes',
      contexto: 'Consulta los propietarios y administra sus datos en este parqueadero.',
    },
    vehicles: {
      ruta: 'CLIENTES Y VEHÍCULOS / VEHÍCULOS',
      titulo: 'Vehículos',
      contexto:
        'Búsqueda operativa de vehículos registrados. No se permite el ingreso de placas no registradas.',
    },
    payments: {
      ruta: 'Mensualidades y pagos / Mensualidades y contratos',
      titulo: 'Mensualidades y contratos',
      contexto: 'Cobertura individual por vehículo. La fecha de vencimiento conserva el día aniversario.',
    },
    'payments-register': {
      ruta: 'Mensualidades y pagos / Registrar pago y anticipo',
      titulo: 'Registrar pago y anticipo',
      contexto: 'Selecciona el vehículo y revisa cada periodo cubierto antes de confirmar.',
    },
    history: {
      ruta: 'GESTIÓN / HISTORIAL',
      titulo: 'Historial de movimientos',
      contexto:
        'Registro de entradas y salidas del parqueadero, hasta los últimos 100 movimientos.',
    },
    novelties: {
      ruta: 'Trazabilidad / Novedades',
      titulo: 'Novedades',
      contexto: 'Registra observaciones vinculadas a un vehículo y conserva su seguimiento.',
    },
    settings: {
      ruta: 'Administración / Configuración operativa',
      titulo: 'Configuración operativa',
      contexto: 'Administra las sedes, zonas e inventario del parqueadero seleccionado.',
    },
    'parking-lots': {
      ruta: 'Acceso y contexto / Tus parqueaderos',
      titulo: 'Tus parqueaderos',
      contexto: 'Selecciona el espacio de trabajo. Cada parqueadero mantiene su propia información.',
    },
    employees: {
      ruta: 'ADMINISTRACIÓN / EMPLEADOS Y TURNOS',
      titulo: 'Empleados y turnos',
      contexto: 'Asigna responsabilidades por usuario y consulta quién realiza cada operación.',
    },
    reports: {
      ruta: 'ADMINISTRACIÓN / ANÁLISIS / REPORTES OPERATIVOS',
      titulo: 'Reportes operativos',
      contexto: 'Resumen consultable del parqueadero seleccionado con el corte del momento.',
    },
    tariffs: {
      ruta: 'ADMINISTRACIÓN / CONFIGURACIÓN / TARIFAS Y VIGENCIAS',
      titulo: 'Tarifas y vigencias',
      contexto: 'Gestiona importes por tipo y periodo de aplicación sin reescribir los pagos anteriores.',
    },
    entry: {
      ruta: 'OPERACIÓN / MOVIMIENTOS / REGISTRAR INGRESO',
      titulo: 'Registrar ingreso',
      contexto:
        'Valida el vehículo antes de asignar una celda. No se permiten excepciones de ingreso.',
    },
    exit: {
      ruta: 'OPERACIÓN / MOVIMIENTOS / REGISTRAR SALIDA',
      titulo: 'Registrar salida',
      contexto: 'Cierra el movimiento activo y libera la celda. El historial se conserva.',
    },
  };
  page: Page = 'dashboard';
  readonly today = new Date();
  busy = false;
  error = '';
  notice = '';
  /** Temporizador que retira el aviso en pantalla; se reinicia en cada operación. */
  private noticeTimer: ReturnType<typeof setTimeout> | null = null;
  search = '';
  vehicleStatusFilter = 'TODAS';
  historyPage = 1;
  readonly historyPageSize = 10;
  bootstrap: Bootstrap | null = null;
  dashboard: Dashboard | null = null;
  customers: Customer[] = [];
  vehicles: Vehicle[] = [];
  cells: Cell[] = [];
  movements: Movement[] = [];
  payments: Payment[] = [];
  contracts: ContractRow[] = [];
  tariffs: Tariff[] = [];
  novelties: Novelty[] = [];
  /** Búsqueda y paginación de la tabla de novedades. */
  noveltyQuery = '';
  noveltyPage = 1;
  sites: Site[] = [];
  zones: Zone[] = [];
  adminZones: Zone[] = [];
  parkingLots: ParkingLotSummary[] = [];
  employees: Employee[] = [];
  shifts: Shift[] = [];
  activity: ActivityItem[] = [];
  report: Report | null = null;
  tariffHistory: TariffHistory[] = [];

  /* Módulo de administración · parqueaderos */
  parkingLotForm = { name: '', city: '', address: '', tax_id: '' };
  parkingLotDialogOpen = false;
  lotSiteForm = { name: '', address: '' };
  lotZoneForm = { site_id: 0, name: '', code: '' };
  lotCellForm = { zone_id: 0, code: '', compatible_type_ids: [] as number[] };

  /* Módulo de administración · configuración operativa */
  configTab: ConfigTab = 'inventory';

  /* Módulo de administración · empleados y turnos */
  employeeTab: EmployeeTab = 'team';
  employeeForm = { full_name: '', document_number: '', username: '', role: 'OPERATOR', shift_id: 0 };
  shiftForm = { name: '', starts_at: '06:00', ends_at: '18:00', notes: '' };
  editingEmployeeId = 0;
  editingEmployeeActive = false;
  employeeDialogOpen = false;

  /* Módulo de administración · reportes */
  reportFilters = { site_id: 0, zone_id: 0, vehicle_type_id: 0, report_date: '' };
  reportPage = 1;
  readonly reportPageSize = 10;

  /* Módulo de administración · tarifas y vigencias */
  tariffTab: TariffTab = 'active';
  tariffForm = { vehicle_type_id: 0, amount: 0, effective_from: '', effective_until: '', note: '' };

  customerForm = { document_type: 'CC', document_number: '', full_name: '', phone: '', email: '' };
  vehicleForm = { customer_id: 0, vehicle_type_id: 0, plate: '', brand: '', color: '' };

  /* Módulo de gestión · directorio de clientes */
  customerSearch = '';
  customerTab: CustomerTab = 'all';
  customerStatusFilter: CustomerStatusFilter = 'ALL';
  customerSort: CustomerSort = 'recent';
  customerPage = 1;
  readonly customerPageSize = 7;
  customerDialogOpen = false;
  customerEditingId = 0;
  customerProfileId = 0;
  cellForm = { zone_id: 0, code: '', compatible_type_ids: [] as number[] };
  siteForm = { name: '', address: '' };

  /* Módulo de gestión · directorio y búsqueda de vehículos */
  vehicleTab: VehicleTab = 'search';
  vehicleSearch = '';
  vehicleTypeFilter: VehicleTypeFilter = 'TODOS';
  vehicleSituationFilter: VehicleSituationFilter = 'TODOS';
  vehicleBrandFilter: VehicleBrandFilter = 'TODOS';
  recentlyConsulted: Vehicle[] = [];
  vehicleDetailId = 0;
  vehicleDialogOpen = false;

  /* Módulo de gestión · mensualidades y contratos */
  monthlyTab: MonthlyTab = 'all';
  monthlySearch = '';
  monthlyTypeFilter: MonthlyTypeFilter = 'TODOS';
  monthlyCoverageFilter: MonthlyCoverageFilter = 'TODAS';
  monthlyPage = 1;
  readonly monthlyPageSize = 5;
  monthlySelectedVehicleId = 0;
  paymentDialogOpen = false;
  paymentHistoryVehicleId = 0;

  /* Módulo de operación · ocupación y celdas */
  cellsSearch = '';
  mapSiteId = 0;
  mapZoneId = 0;
  mapTypeId = 0;
  mapCellId = 0;
  mapZoneOptions: Zone[] = [];
  cellDialogOpen = false;
  zoneForm = { site_id: 0, name: '' };
  parkingName = '';
  parkingTaxId = '';
  selectedLotId = 0;
  newParkingName = '';
  newParkingTaxId = '';
  selectedVehicleId = 0;
  selectedCellId = 0;
  paymentVehicleId = 0;
  paymentMonths = 1;
  paymentMethod = 'CASH';
  noveltyForm = { vehicle_id: 0, category: 'Observación de vehículo', description: '' };
  entryPlate = '';
  entrySiteId = 0;
  entryZoneId = 0;
  exitPlate = '';
  exitMovementId = 0;

  get vehicleTypes(): VehicleType[] {
    return this.bootstrap?.vehicle_types ?? [];
  }
  get availableCells(): Cell[] {
    const vehicle = this.vehicles.find((item) => item.id === Number(this.selectedVehicleId));
    if (!vehicle) return [];
    return this.cells.filter(
      (cell) =>
        cell.operational_status === 'ACTIVE' &&
        !cell.occupied &&
        cell.compatible_types.some((type) => type.id === vehicle.vehicle_type_id),
    );
  }
  get selectedVehicle(): Vehicle | undefined {
    return this.vehicles.find((item) => item.id === Number(this.selectedVehicleId));
  }
  get filteredVehicles(): Vehicle[] {
    const term = this.vehicleTerm;
    const byText = term
      ? this.vehicles.filter((item) =>
          `${item.plate} ${item.customer_name} ${item.brand}`.toLocaleLowerCase().includes(term),
        )
      : this.vehicles;
    if (this.vehicleStatusFilter === 'TODAS') return byText;
    return byText.filter((item) => item.monthly_status === this.vehicleStatusFilter);
  }
  get activeMovements(): Movement[] {
    return this.movements.filter((item) => !item.exited_at);
  }
  get pagedMovements(): Movement[] {
    const start = (this.historyPage - 1) * this.historyPageSize;
    return this.movements.slice(start, start + this.historyPageSize);
  }
  get historyTotalPages(): number {
    return Math.max(1, Math.ceil(this.movements.length / this.historyPageSize));
  }
  get historyPages(): number[] {
    const total = this.historyTotalPages;
    const window = 7;
    if (total <= window) {
      return Array.from({ length: total }, (_, index) => index + 1);
    }
    const end = Math.min(total, Math.max(window, this.historyPage + Math.floor(window / 2)));
    const start = Math.max(1, end - window + 1);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }
  get paginationFrom(): number {
    return this.movements.length ? (this.historyPage - 1) * this.historyPageSize + 1 : 0;
  }
  get paginationTo(): number {
    return Math.min(this.historyPage * this.historyPageSize, this.movements.length);
  }
  goToHistoryPage(page: number): void {
    this.historyPage = Math.min(Math.max(1, page), this.historyTotalPages);
  }
  get siteId(): number {
    return this.bootstrap?.sites[0]?.id ?? 0;
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de operación · registro de ingreso                          */
  /* ------------------------------------------------------------------ */
  /** Sedes del parqueadero, para acotar la asignación de celda. */
  get entrySites(): Site[] {
    return this.sites;
  }
  /** Zonas con al menos una celda libre compatible con el vehículo. */
  get entryZones(): { id: number; name: string }[] {
    const map = new Map<number, string>();
    for (const cell of this.cells) {
      if (!this.entryCellFits(cell)) continue;
      if (this.entrySiteId && cell.site_id !== this.entrySiteId) continue;
      map.set(cell.zone_id, cell.zone_name);
    }
    return [...map.entries()].map(([id, name]) => ({ id, name }));
  }
  /** Celdas operativas, libres y compatibles con el vehículo identificado. */
  get entryCells(): Cell[] {
    return this.cells.filter(
      (cell) =>
        this.entryCellFits(cell) &&
        (!this.entrySiteId || cell.site_id === this.entrySiteId) &&
        (!this.entryZoneId || cell.zone_id === this.entryZoneId),
    );
  }
  /** Las cinco comprobaciones de ingreso exigidas antes de confirmar. */
  get entryChecks(): EntryCheck[] {
    const vehicle = this.selectedVehicle;
    if (!vehicle) return [];
    const cell = this.entryCells.find((item) => item.id === Number(this.selectedCellId));
    const expiry = this.formatDate(vehicle.expires_on) || 'sin cobertura';
    const state = (ok: boolean): CheckState => (ok ? 'ok' : 'fail');
    return [
      {
        label: `Cliente registrado y asociado a ${vehicle.plate}`,
        state: state(vehicle.customer_id > 0),
      },
      {
        label: 'Contrato de mensualidad activo y con cobertura hoy',
        state: state(vehicle.monthly_status === 'VIGENTE'),
      },
      {
        label: `Mensualidad al día · Vence ${expiry}`,
        state: state(vehicle.monthly_status === 'VIGENTE'),
      },
      {
        label: 'Sin movimiento de ingreso activo',
        state: state(!vehicle.inside),
      },
      {
        label: cell
          ? `Celda ${cell.code} operativa, libre y compatible`
          : 'Celda operativa, libre y compatible (pendiente de asignar)',
        state: cell ? state(cell.operational_status === 'ACTIVE' && !cell.occupied) : 'pending',
      },
    ];
  }
  get entryApproved(): number {
    return this.entryChecks.filter((check) => check.state === 'ok').length;
  }
  /** El ingreso solo se bloquea cuando una comprobación falla de forma real. */
  get entryBlocked(): boolean {
    return this.entryChecks.some((check) => check.state === 'fail');
  }
  get vehiclesInside(): number {
    return this.dashboard?.vehicles_inside ?? 0;
  }
  get cellsAvailable(): number {
    return this.dashboard?.cells_available ?? 0;
  }

  /**
   * Vehículos dentro agrupados por tipo: "12 carros/camionetas · 3 motos".
   * Cada vehículo tiene un único tipo, así que no hay doble conteo.
   */
  get vehiclesInsideByGroup(): string {
    const dentro = this.vehicles.filter((vehicle) => vehicle.inside);
    const motos = dentro.filter((vehicle) => vehicle.type_code === 'MOTO').length;
    return `${dentro.length - motos} carros/camionetas · ${motos} motos`;
  }

  /**
   * Celdas libres agrupadas por tipo: "8 carros/camionetas · 4 motos".
   * Una celda compatible con varios tipos se cuenta una sola vez: las aptas
   * únicamente para motos van al grupo de motos y el resto al de autos.
   */
  get cellsAvailableByGroup(): string {
    const libres = this.cells.filter((celda) => !celda.occupied);
    let motos = 0;
    for (const celda of libres) {
      const codigos = celda.compatible_types.map((tipo) => tipo.code);
      const soloMotos =
        codigos.includes('MOTO') &&
        !codigos.some((codigo) => codigo === 'CAR' || codigo === 'TRUCK');
      if (soloMotos) motos += 1;
    }
    return `${libres.length - motos} carros/camionetas · ${motos} motos`;
  }

  /* ------------------------------------------------------------------ */
  /* Resumen operativo · estado de operación                            */
  /* ------------------------------------------------------------------ */

  /** Inventario total de celdas, incluidas las que están en mantenimiento. */
  get cellsInventory(): number {
    return (this.dashboard?.cells_total ?? 0) + (this.dashboard?.cells_maintenance ?? 0);
  }

  /** Porcentaje de ocupación física: celdas ocupadas sobre el inventario. */
  get occupancyRate(): number {
    const total = this.cellsInventory;
    if (!total) return 0;
    return ((this.dashboard?.cells_occupied ?? 0) / total) * 100;
  }

  /** Leyenda del anillo de ocupación. */
  get occupancyLegend(): { label: string; value: number }[] {
    return [
      { label: 'Ocupadas', value: this.dashboard?.cells_occupied ?? 0 },
      { label: 'Libres operativas', value: this.dashboard?.cells_available ?? 0 },
      { label: 'Mantenimiento', value: this.dashboard?.cells_maintenance ?? 0 },
    ];
  }

  /** Estado del anillo: avisa cuando el parqueadero está sobre capacidad. */
  get occupancyState(): { label: string; tone: 'ok' | 'alert' } {
    const ocupadas = this.dashboard?.cells_occupied ?? 0;
    return ocupadas > this.cellsInventory
      ? { label: 'Sobrecapacidad', tone: 'alert' }
      : { label: 'Sin sobrecapacidad', tone: 'ok' };
  }

  /**
   * Disponibilidad por tipo. Los grupos no se solapan: las celdas exclusivas
   * de motos van al grupo de motos y el resto al de carros y camionetas.
   */
  get availabilityByGroup(): {
    label: string;
    occupied: number;
    total: number;
    available: number;
    maintenance: number;
    percent: number;
  }[] {
    const groups = this.dashboard?.occupancy_by_group ?? {};
    const vacio: OccupancyGroup = { total: 0, occupied: 0, available: 0, maintenance: 0 };
    const bloque = (label: string, data: OccupancyGroup) => ({
      label,
      occupied: data.occupied,
      total: data.total,
      available: data.available,
      maintenance: data.maintenance,
      percent: data.total ? (data.occupied / data.total) * 100 : 0,
    });
    return [
      bloque('Carros y camionetas', groups['vehiculos'] ?? vacio),
      bloque('Motos', groups['motos'] ?? vacio),
    ];
  }

  /** Los tres cuadros de mensualidades del resumen. */
  get monthlyCards(): {
    value: string;
    description: string;
    pill: string;
    tone: 'ok' | 'warn' | 'alert';
  }[] {
    const vigentes = this.dashboard?.monthly_active ?? 0;
    const proximas = this.dashboard?.monthly_expiring_soon ?? 0;
    const vencidas = this.dashboard?.monthly_expired ?? 0;
    return [
      {
        value: `${vigentes} vigentes`,
        description: `Incluyen ${proximas} próximas a vencer.`,
        pill: '✓ Cobertura actual',
        tone: 'ok',
      },
      {
        value: `${proximas} próximas a vencer`,
        description: `Subconjunto de las ${vigentes} vigentes.`,
        pill: '◷ En los próximos 7 días',
        tone: 'warn',
      },
      {
        value: `${vencidas} vencidas`,
        description: 'Ingreso bloqueado hasta renovar.',
        pill: '! Requieren pago',
        tone: 'alert',
      },
    ];
  }

  /** Movimientos más recientes, ordenados por la fecha del evento. */
  get recentMovements(): Movement[] {
    const evento = (movement: Movement): number =>
      new Date(movement.exited_at ?? movement.entered_at).getTime();
    return [...this.movements]
      .sort((a, b) => evento(b) - evento(a))
      .slice(0, 4);
  }

  /** Responsable del movimiento: quien registró el ingreso o la salida. */
  movementOwner(movement: Movement): string {
    const nombre = movement.exited_at ? movement.exit_employee : movement.entry_employee;
    return nombre ?? 'Sesión demo';
  }

  /** Aviso honesto sobre el inventario de demostración. */
  get demoInventoryNote(): string {
    const grupos = this.dashboard?.occupancy_by_group ?? {};
    const vehiculos = grupos['vehiculos']?.total ?? 0;
    const motos = grupos['motos']?.total ?? 0;
    return `Inventario de demostración: ${vehiculos} carros/camionetas + ${motos} motos = ${
      vehiculos + motos
    } celdas; capacidad por confirmar.`;
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de operación · ocupación y celdas                            */
  /* ------------------------------------------------------------------ */
  /** Sede visible en el mapa: la elegida en el filtro o la primera disponible. */
  get mapSiteName(): string {
    const sitio = this.sites.find((item) => item.id === this.mapSiteId) ?? this.sites[0];
    return sitio?.name ?? 'Sede principal';
  }

  /** Contexto de la pantalla; en inventario refleja la sede real del mapa. */
  get pageContext(): string {
    if (this.page === 'cells') {
      return `Inventario de ${this.mapSiteName}. Selecciona una celda para consultar su detalle.`;
    }
    if (this.page === 'customers') {
      return `Consulta los propietarios y administra sus datos en ${this.customerScopeName}.`;
    }
    return this.pageMeta[this.page].contexto;
  }

  /** Celdas del mapa después de aplicar búsqueda y filtros. */
  get mapCells(): Cell[] {
    const busqueda = this.cellsSearch.trim().toLowerCase();
    return this.cells.filter((celda) => {
      if (this.mapSiteId && celda.site_id !== this.mapSiteId) return false;
      if (this.mapZoneId && celda.zone_id !== this.mapZoneId) return false;
      if (
        this.mapTypeId &&
        !celda.compatible_types.some((tipo) => tipo.id === this.mapTypeId)
      ) {
        return false;
      }
      if (!busqueda) return true;
      return (
        celda.code.toLowerCase().includes(busqueda) ||
        (celda.vehicle_plate ?? '').toLowerCase().includes(busqueda)
      );
    });
  }

  /** Zonas del mapa con sus celdas ya filtradas. */
  get mapZones(): MapZone[] {
    return this.mapZoneOptions
      .map((zona) => {
        const celdas = this.mapCells.filter((celda) => celda.zone_id === zona.id);
        return {
          id: zona.id,
          name: zona.name,
          kindLabel: this.zoneKindLabel(celdas),
          cells: celdas,
        };
      })
      .filter((zona) => zona.cells.length > 0);
  }

  /** Zonas de carros y camionetas: se reparten en dos columnas. */
  get mapCarZones(): MapZone[] {
    return this.mapZones.filter((zona) => zona.kindLabel !== 'Motos');
  }

  /** Zonas de motos: se muestran a lo ancho, después de la banda de circulación. */
  get mapMotoZones(): MapZone[] {
    return this.mapZones.filter((zona) => zona.kindLabel === 'Motos');
  }

  /** Tipo de zona según los vehículos que admiten sus celdas. */
  zoneKindLabel(cells: Cell[]): string {
    if (!cells.length) return 'Carros / camionetas';
    const soloMotos = cells.every((celda) => {
      const codigos = celda.compatible_types.map((tipo) => tipo.code);
      return codigos.includes('MOTO') && !codigos.some((codigo) => codigo !== 'MOTO');
    });
    return soloMotos ? 'Motos' : 'Carros / camionetas';
  }

  /** Celda enfocada en el mapa: la elegida o, en su defecto, la primera visible. */
  get mapCell(): Cell | undefined {
    const celdas = this.mapCells;
    return celdas.find((celda) => celda.id === this.mapCellId) ?? celdas[0];
  }

  /** Vehículo que ocupa la celda enfocada. */
  get mapCellVehicle(): Vehicle | undefined {
    const celda = this.mapCell;
    if (!celda || !celda.vehicle_id) return undefined;
    return this.vehicles.find((vehiculo) => vehiculo.id === celda.vehicle_id);
  }

  /** Movimiento activo de la celda enfocada. */
  get mapCellMovement(): Movement | undefined {
    const celda = this.mapCell;
    if (!celda) return undefined;
    return this.movements.find(
      (movimiento) => movimiento.cell_id === celda.id && !movimiento.exited_at,
    );
  }

  /** Estado de la celda enfocada: libre, ocupada o en mantenimiento. */
  get mapCellState(): 'free' | 'busy' | 'maintenance' {
    const celda = this.mapCell;
    if (!celda) return 'free';
    if (celda.operational_status !== 'ACTIVE') return 'maintenance';
    return celda.occupied ? 'busy' : 'free';
  }

  /** Estado de la celda enfocada, sin icono. */
  get mapCellStateName(): string {
    const celda = this.mapCell;
    if (!celda) return 'Sin celda seleccionada';
    if (celda.operational_status !== 'ACTIVE') return 'Mantenimiento';
    return celda.occupied ? 'Ocupada' : 'Libre';
  }

  /** Icono del estado de la celda enfocada, el mismo de la leyenda. */
  get mapCellStateIcon(): string {
    if (this.mapCellState === 'busy') return '●';
    if (this.mapCellState === 'maintenance') return '⚒';
    return '○';
  }

  /** Estado de una celda del mapa, con el icono de la leyenda. */
  mapCellStateLabel(cell: Cell): string {
    if (cell.operational_status !== 'ACTIVE') return '⚒ Mantenimiento';
    return cell.occupied ? '● Ocupada' : '○ Libre';
  }

  /** Tipos de vehículo admitidos por la celda enfocada, en texto. */
  get mapCellCompatibility(): string {
    const celda = this.mapCell;
    if (!celda) return '—';
    const nombres = celda.compatible_types.map((tipo) => tipo.name);
    if (nombres.length <= 1) return nombres[0] ?? 'Sin tipos definidos';
    const lista = nombres.map((nombre, indice) => (indice === 0 ? nombre : nombre.toLowerCase()));
    return `${lista.slice(0, -1).join(', ')} y ${lista[lista.length - 1]}`;
  }

  /** Carga las zonas de la sede visible en el mapa. */
  loadMapZones(): void {
    if (!this.mapSiteId) this.mapSiteId = this.sites[0]?.id ?? 0;
    if (!this.mapSiteId) return;
    this.api.zones(this.mapSiteId).subscribe({
      next: (data) => {
        this.mapZoneOptions = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Cambia la sede del mapa y recarga las zonas de esa sede. */
  changeMapSite(siteId: number): void {
    this.mapSiteId = siteId;
    this.mapZoneId = 0;
    this.loadMapZones();
  }

  /** Enfoca una celda del mapa para consultar su detalle. */
  selectMapCell(cell: Cell): void {
    this.mapCellId = cell.id;
  }

  /** Abre el alta de celdas desde el encabezado de la pantalla. */
  openCellDialog(): void {
    this.cellDialogOpen = true;
    if (!this.cellForm.zone_id) this.cellForm.zone_id = this.mapZoneOptions[0]?.id ?? 0;
  }

  /** Cierra el alta de celdas. */
  closeCellDialog(): void {
    this.cellDialogOpen = false;
  }

  /** Pasa la celda enfocada a mantenimiento o la reactiva. */
  applyCellStatus(): void {
    const celda = this.mapCell;
    if (!celda) return;
    if (celda.occupied) {
      this.error =
        'No puedes poner una celda ocupada en mantenimiento. Registra primero la salida del vehículo.';
      return;
    }
    this.toggleCell(celda);
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de gestión · directorio de clientes                          */
  /* ------------------------------------------------------------------ */

  /** Vehículos de un cliente, tomados del listado de la API. */
  customerVehicles(customerId: number): Vehicle[] {
    return this.vehicles.filter((vehiculo) => vehiculo.customer_id === customerId);
  }

  /** Columna "Vehículos": cantidad de placas y sus identificaciones. */
  customerVehiclesLabel(customer: Customer): string {
    const vehiculos = this.customerVehicles(customer.id);
    if (!vehiculos.length) return 'Sin vehículos';
    const placas = vehiculos.slice(0, 2).map((vehiculo) => vehiculo.plate);
    const resto = vehiculos.length - placas.length;
    return `${vehiculos.length} · ${placas.join(' / ')}${resto > 0 ? ` / +${resto}` : ''}`;
  }

  /** Columna "Documento": tipo de documento y número con separadores de miles. */
  customerDocumentLabel(customer: Customer): string {
    const numero = /^\d+$/.test(customer.document_number)
      ? customer.document_number.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
      : customer.document_number;
    return `${customer.document_type ?? 'CC'} · ${numero}`;
  }

  /** Columna "Contacto": celular del cliente o aviso de que no lo tiene. */
  customerContactLabel(customer: Customer): string {
    return customer.phone?.trim() ? customer.phone.trim() : 'Sin celular';
  }

  /**
   * Columna "Mensualidades": resumen de los contratos del cliente.
   * El importe se añade cuando hay dos o más contratos vigentes, porque con uno
   * solo la placa ya muestra su valor en el detalle del vehículo.
   */
  customerMonthlySummary(customer: Customer): string {
    const vehiculos = this.customerVehicles(customer.id);
    if (!vehiculos.length) return 'Sin contratos';
    const vigentes = vehiculos.filter((vehiculo) => vehiculo.monthly_status === 'VIGENTE');
    const proximas = vehiculos.filter((vehiculo) => vehiculo.monthly_status === 'ANTICIPADA');
    const vencidas = vehiculos.filter(
      (vehiculo) => vehiculo.monthly_status !== 'VIGENTE' && vehiculo.monthly_status !== 'ANTICIPADA',
    );
    if (vigentes.length === vehiculos.length) {
      return vigentes.length > 1
        ? `${vigentes.length} vigentes · ${this.formatMoney(this.customerMonthlyAmount(vigentes))}`
        : 'Vigente';
    }
    if (proximas.length === vehiculos.length) return 'Próxima a vencer';
    if (vencidas.length === vehiculos.length) return 'Vencida';
    const partes: string[] = [];
    if (vigentes.length) partes.push(`${vigentes.length} ${vigentes.length === 1 ? 'vigente' : 'vigentes'}`);
    if (proximas.length) partes.push(`${proximas.length} ${proximas.length === 1 ? 'próxima' : 'próximas'} a vencer`);
    if (vencidas.length) partes.push(`${vencidas.length} ${vencidas.length === 1 ? 'vencida' : 'vencidas'}`);
    return partes.join(' · ');
  }

  /** Suma de las tarifas mensuales de los vehículos indicados. */
  customerMonthlyAmount(vehicles: Vehicle[]): number {
    return vehicles.reduce((total, vehiculo) => total + this.monthlyPrice(vehiculo.id), 0);
  }

  /** Clientes del directorio después de búsqueda, pestañas, filtros y orden. */
  get customerRows(): Customer[] {
    // La búsqueda de la página tiene prioridad; si está vacía se aplica la del buscador global.
    const busqueda = (this.customerSearch.trim() || this.search.trim()).toLowerCase();
    const filtrados = this.customers.filter((customer) => {
      const vehiculos = this.customerVehicles(customer.id);
      if (busqueda) {
        const coincide =
          customer.full_name.toLowerCase().includes(busqueda) ||
          customer.document_number.toLowerCase().includes(busqueda) ||
          (customer.phone ?? '').toLowerCase().includes(busqueda) ||
          vehiculos.some((vehiculo) => vehiculo.plate.toLowerCase().includes(busqueda));
        if (!coincide) return false;
      }
      if (this.customerTab === 'inside' && !vehiculos.some((vehiculo) => vehiculo.inside)) return false;
      if (this.customerTab === 'expired' && !vehiculos.some((vehiculo) => vehiculo.monthly_status === 'VENCIDA')) {
        return false;
      }
      if (this.customerStatusFilter === 'SIN') {
        if (vehiculos.length) return false;
      } else if (this.customerStatusFilter !== 'ALL') {
        if (!vehiculos.some((vehiculo) => vehiculo.monthly_status === this.customerStatusFilter)) {
          return false;
        }
      }
      return true;
    });
    const ordenados = [...filtrados];
    if (this.customerSort === 'name') {
      ordenados.sort((a, b) => a.full_name.localeCompare(b.full_name, 'es'));
    } else if (this.customerSort === 'document') {
      ordenados.sort((a, b) => a.document_number.localeCompare(b.document_number, 'es'));
    } else {
      ordenados.sort((a, b) => b.id - a.id);
    }
    return ordenados;
  }

  /** Total de páginas del directorio, con un mínimo de una. */
  get customerTotalPages(): number {
    return Math.max(1, Math.ceil(this.customerRows.length / this.customerPageSize));
  }

  /** Página visible, ajustada al total disponible después de filtrar. */
  get customerCurrentPage(): number {
    return Math.min(Math.max(1, this.customerPage), this.customerTotalPages);
  }

  /** Clientes de la página visible. */
  get customerPagedRows(): Customer[] {
    const inicio = (this.customerCurrentPage - 1) * this.customerPageSize;
    return this.customerRows.slice(inicio, inicio + this.customerPageSize);
  }

  /** Ventana de páginas de la paginación, con un máximo de cinco números. */
  get customerPages(): number[] {
    const total = this.customerTotalPages;
    const inicio = Math.min(Math.max(1, this.customerCurrentPage - 2), Math.max(1, total - 4));
    const paginas: number[] = [];
    for (let indice = inicio; indice < inicio + 5 && indice <= total; indice++) paginas.push(indice);
    return paginas;
  }

  /** Resumen de la paginación: "Mostrando 7 de 96 clientes · Página 1 de 14". */
  get customerPaginationLabel(): string {
    const total = this.customerRows.length;
    const mostrados = Math.max(0, Math.min(this.customerPageSize, total - (this.customerCurrentPage - 1) * this.customerPageSize));
    return `Mostrando ${mostrados} de ${total} clientes · Página ${this.customerCurrentPage} de ${this.customerTotalPages}`;
  }

  /** Indicador: clientes registrados en el parqueadero. */
  get customerRegisteredCount(): number {
    return this.customers.length;
  }

  /** Indicador: vehículos asociados a los clientes del parqueadero. */
  get customerAssociatedVehicles(): number {
    return this.vehicles.length;
  }

  /** Indicador: clientes con más de un vehículo registrado. */
  get customerMultiVehicleCount(): number {
    return this.customers.filter((customer) => this.customerVehicles(customer.id).length > 1).length;
  }

  /** Cliente abierto en el perfil de consulta. */
  get customerProfile(): Customer | undefined {
    return this.customers.find((customer) => customer.id === this.customerProfileId);
  }

  /** Nombre de la sede del parqueadero, para el texto de alcance de la consulta. */
  get customerScopeName(): string {
    return this.sites[0]?.name ?? 'Sede principal';
  }

  /** Aplica la búsqueda escrita y vuelve a la primera página. */
  setCustomerSearch(value: string): void {
    this.customerSearch = value;
    this.customerPage = 1;
  }

  /** Cambia la pestaña del directorio y vuelve a la primera página. */
  setCustomerTab(tab: CustomerTab): void {
    this.customerTab = tab;
    this.customerPage = 1;
  }

  /** Cambia el filtro de estado de mensualidad y vuelve a la primera página. */
  setCustomerStatusFilter(status: CustomerStatusFilter): void {
    this.customerStatusFilter = status;
    this.customerPage = 1;
  }

  /** Cambia el orden del directorio y vuelve a la primera página. */
  setCustomerSort(sort: CustomerSort): void {
    this.customerSort = sort;
    this.customerPage = 1;
  }

  /** Salta a una página del directorio. */
  goToCustomerPage(page: number): void {
    this.customerPage = Math.min(Math.max(1, page), this.customerTotalPages);
  }

  /** Abre el perfil de consulta de un cliente. */
  openCustomerProfile(customer: Customer): void {
    this.customerProfileId = customer.id;
  }

  /** Cierra el perfil de consulta. */
  closeCustomerProfile(): void {
    this.customerProfileId = 0;
  }

  /** Abre el formulario de alta de clientes. */
  openCustomerDialog(): void {
    this.customerEditingId = 0;
    this.customerForm = {
      document_type: 'CC',
      document_number: '',
      full_name: '',
      phone: '',
      email: '',
    };
    this.customerDialogOpen = true;
  }

  /** Abre el formulario de edición con los datos del cliente. */
  editCustomer(customer: Customer): void {
    this.customerEditingId = customer.id;
    this.customerForm = {
      document_type: customer.document_type ?? 'CC',
      document_number: customer.document_number,
      full_name: customer.full_name,
      phone: customer.phone ?? '',
      email: customer.email ?? '',
    };
    this.customerDialogOpen = true;
  }

  /** Cierra el formulario de alta o de edición de clientes. */
  closeCustomerDialog(): void {
    this.customerDialogOpen = false;
    this.customerEditingId = 0;
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de gestión · directorio y búsqueda de vehículos             */
  /* ------------------------------------------------------------------ */

  /**
   * Texto de la consulta de vehículos. La búsqueda escrita en la pantalla
   * tiene prioridad; si está vacía se aplica la del buscador global.
   */
  get vehicleTerm(): string {
    return (this.vehicleSearch.trim() || this.search.trim()).toLowerCase();
  }

  /** Marcas registradas en el parqueadero, para el filtro de marcas. */
  get vehicleBrands(): string[] {
    const marcas = this.vehicles
      .map((vehiculo) => vehiculo.brand.trim())
      .filter((marca) => marca.length > 0);
    return [...new Set(marcas)].sort((a, b) => a.localeCompare(b, 'es'));
  }

  /** Propietario que coincide con la consulta escrita (resumen y pastilla). */
  get vehicleOwnerMatch(): Customer | undefined {
    const term = this.vehicleTerm;
    if (!term) return undefined;
    return this.customers.find(
      (cliente) =>
        cliente.full_name.toLowerCase().includes(term) ||
        cliente.document_number.toLowerCase().includes(term),
    );
  }

  /** Vehículos que superan la consulta escrita y los filtros del módulo. */
  get vehicleResults(): Vehicle[] {
    const term = this.vehicleTerm;
    return this.vehicles.filter((vehiculo) => {
      if (this.vehicleTypeFilter !== 'TODOS' && vehiculo.type_code !== this.vehicleTypeFilter) {
        return false;
      }
      if (this.vehicleSituationFilter === 'DENTRO' && !vehiculo.inside) return false;
      if (this.vehicleSituationFilter === 'FUERA' && vehiculo.inside) return false;
      if (this.vehicleBrandFilter !== 'TODOS' && vehiculo.brand !== this.vehicleBrandFilter) {
        return false;
      }
      if (!term) return true;
      const cliente = this.customers.find((item) => item.id === vehiculo.customer_id);
      const documento = cliente?.document_number ?? '';
      return [vehiculo.plate, vehiculo.brand, vehiculo.customer_name, documento]
        .join(' ')
        .toLowerCase()
        .includes(term);
    });
  }

  /** Resultados agrupados por propietario: una fila por cliente con sus placas. */
  get vehicleGroups(): VehicleOwnerGroup[] {
    const grupos = new Map<number, VehicleOwnerGroup>();
    for (const vehiculo of this.vehicleResults) {
      const grupo = grupos.get(vehiculo.customer_id);
      if (grupo) {
        grupo.vehicles.push(vehiculo);
        continue;
      }
      const cliente = this.customers.find((item) => item.id === vehiculo.customer_id);
      grupos.set(vehiculo.customer_id, {
        customerId: vehiculo.customer_id,
        customerName: vehiculo.customer_name,
        documentLabel: this.vehicleDocumentLabel(cliente),
        vehicles: [vehiculo],
      });
    }
    return [...grupos.values()];
  }

  /** Resumen de la búsqueda: "2 resultados por propietario · Nombre · CC 1.032.456.789". */
  get vehicleSearchSummary(): string {
    const total = this.vehicleGroups.length;
    const plural = total === 1 ? 'resultado' : 'resultados';
    const propietario = this.vehicleOwnerMatch;
    if (propietario) {
      return `${total} ${plural} por propietario · ${propietario.full_name} · ${this.vehicleDocumentLabel(propietario)}`;
    }
    if (this.vehicleTerm) return `${total} ${plural} por placa o marca`;
    return `${total} ${plural} por propietario`;
  }

  /** La pastilla informativa aparece cuando la consulta corresponde a un propietario. */
  get vehicleOwnerFilterActive(): boolean {
    return this.vehicleOwnerMatch !== undefined;
  }

  /** Indicador: vehículos registrados en el parqueadero. */
  get vehicleRegisteredCount(): number {
    return this.vehicles.length;
  }

  /** Indicador: vehículos con movimiento activo. */
  get vehicleInsideCount(): number {
    return this.vehicles.filter((vehiculo) => vehiculo.inside).length;
  }

  /** Indicador: vehículos sin movimiento activo. */
  get vehicleOutsideCount(): number {
    return this.vehicles.length - this.vehicleInsideCount;
  }

  /** Indicador: propietarios con al menos un vehículo registrado. */
  get vehicleOwnerCount(): number {
    return new Set(this.vehicles.map((vehiculo) => vehiculo.customer_id)).size;
  }

  /** Pie del indicador de vehículos dentro: "54 carros/camionetas · 8 motos". */
  get vehicleInsideBreakdown(): string {
    const dentro = this.vehicles.filter((vehiculo) => vehiculo.inside);
    const motos = dentro.filter((vehiculo) => vehiculo.type_code === 'MOTO').length;
    return `${dentro.length - motos} carros/camionetas · ${motos} motos`;
  }

  /** Últimos vehículos consultados por el operador, como máximo tres. */
  get vehicleQuickAccess(): Vehicle[] {
    return this.recentlyConsulted.slice(0, 3);
  }

  /** Vehículo abierto en la ficha de detalle. */
  get vehicleDetail(): Vehicle | undefined {
    return this.vehicles.find((vehiculo) => vehiculo.id === this.vehicleDetailId);
  }

  /** Movimientos del vehículo abierto en la ficha de detalle. */
  get vehicleDetailMovements(): Movement[] {
    return this.movements
      .filter((movimiento) => movimiento.vehicle_id === this.vehicleDetailId)
      .sort((a, b) => b.entered_at.localeCompare(a.entered_at));
  }

  /**
   * Documento del propietario con el formato de la tabla de vehículos:
   * "CC 1.032.456.789".
   */
  vehicleDocumentLabel(cliente: Customer | undefined): string {
    if (!cliente) return '';
    const numero = /^\d+$/.test(cliente.document_number)
      ? cliente.document_number.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
      : cliente.document_number;
    return `${cliente.document_type ?? 'CC'} ${numero}`;
  }

  /** Documento del propietario de un vehículo concreto. */
  vehicleOwnerDocument(vehiculo: Vehicle): string {
    const cliente = this.customers.find((item) => item.id === vehiculo.customer_id);
    return this.vehicleDocumentLabel(cliente);
  }

  /** Estado de la mensualidad con el símbolo del diseño. */
  vehicleMonthlyLabel(vehiculo: Vehicle): string {
    if (vehiculo.monthly_status === 'VIGENTE') return '✓ Vigente';
    if (vehiculo.monthly_status === 'ANTICIPADA') return '◷ Próxima a vencer';
    return '! Vencida';
  }

  /** Ubicación del vehículo: ["Dentro · C-01", "Sede principal / A"]. */
  vehicleLocationLines(vehiculo: Vehicle): string[] {
    if (!vehiculo.inside || !vehiculo.cell_code) return ['Fuera', 'Sin celda asignada'];
    const celda = this.cells.find((item) => item.code === vehiculo.cell_code);
    const zona = this.zones.find((item) => item.id === celda?.zone_id);
    const sede = celda?.site_name ?? '';
    const referencia = zona?.code?.trim() || celda?.zone_name || '';
    return [`Dentro · ${vehiculo.cell_code}`, `${sede} / ${referencia}`];
  }

  /** Situación resumida del vehículo para la tabla de acceso rápido. */
  vehicleSituationLabel(vehiculo: Vehicle): string {
    if (vehiculo.inside) return `Dentro · ${vehiculo.cell_code ?? ''}`;
    return vehiculo.monthly_status === 'VIGENTE' ? 'Fuera' : 'Fuera · Ingreso bloqueado';
  }

  /** Acción sugerida en la tabla de acceso rápido. */
  vehicleQuickActionLabel(vehiculo: Vehicle): string {
    return vehiculo.monthly_status === 'VIGENTE' ? 'Consultar →' : 'Registrar pago →';
  }

  /** Cambia la pestaña del módulo de vehículos. */
  setVehicleTab(tab: VehicleTab): void {
    this.vehicleTab = tab;
  }

  /** Aplica la consulta escrita de la búsqueda global. */
  setVehicleSearch(value: string): void {
    this.vehicleSearch = value;
  }

  /** Filtra la búsqueda por tipo de vehículo. */
  setVehicleTypeFilter(value: VehicleTypeFilter): void {
    this.vehicleTypeFilter = value;
  }

  /** Filtra la búsqueda por situación del vehículo. */
  setVehicleSituationFilter(value: VehicleSituationFilter): void {
    this.vehicleSituationFilter = value;
  }

  /** Filtra la búsqueda por marca de vehículo. */
  setVehicleBrandFilter(value: VehicleBrandFilter): void {
    this.vehicleBrandFilter = value;
  }

  /** Abre la ficha de detalle y deja el vehículo en el acceso rápido. */
  openVehicleDetail(vehiculo: Vehicle): void {
    this.vehicleDetailId = vehiculo.id;
    this.recentlyConsulted = [
      vehiculo,
      ...this.recentlyConsulted.filter((item) => item.id !== vehiculo.id),
    ].slice(0, 3);
  }

  /** Cierra la ficha de detalle del vehículo. */
  closeVehicleDetail(): void {
    this.vehicleDetailId = 0;
  }

  /** Abre el formulario de alta de vehículos. */
  openVehicleDialog(): void {
    this.vehicleForm = { customer_id: 0, vehicle_type_id: 0, plate: '', brand: '', color: '' };
    this.vehicleDialogOpen = true;
  }

  /** Cierra el formulario de alta de vehículos. */
  closeVehicleDialog(): void {
    this.vehicleDialogOpen = false;
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de operación · registro de salida                           */
  /* ------------------------------------------------------------------ */
  get exitMovement(): Movement | undefined {
    return this.movements.find(
      (item) => item.id === Number(this.exitMovementId) && !item.exited_at,
    );
  }
  get exitMovementVehicle(): Vehicle | undefined {
    const movement = this.exitMovement;
    if (!movement) return undefined;
    return this.vehicles.find((item) => item.id === movement.vehicle_id);
  }
  get exitCustomer(): Customer | undefined {
    const vehicle = this.exitMovementVehicle;
    if (!vehicle) return undefined;
    return this.customers.find((item) => item.id === vehicle.customer_id);
  }
  get exitCell(): Cell | undefined {
    const movement = this.exitMovement;
    if (!movement) return undefined;
    return this.cells.find((item) => item.id === movement.cell_id);
  }

  ngOnInit(): void {
    this.loadAll();
  }

  loadAll(): void {
    this.busy = true;
    this.error = '';
    this.api.bootstrap(this.selectedLotId || undefined).subscribe({
      next: (data) => {
        this.bootstrap = data;
        this.selectedLotId = data.parking_lot.id;
        this.zoneForm.site_id = data.sites[0]?.id ?? 0;
        this.cellForm.zone_id = 0;
        this.parkingName = data.parking_lot.name;
        this.parkingTaxId = data.parking_lot.tax_id ?? '';
        this.api.dashboard().subscribe({
          next: (value) => {
            this.dashboard = value;
            this.changeDetector.detectChanges();
          },
          error: (err: unknown) => this.fail(err),
        });
        this.refreshLists();
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => {
        this.fail(err);
        this.busy = false;
      },
    });
  }

  selectParkingLot(id: number): void {
    if (!id || id === this.selectedLotId) return;
    this.selectedLotId = id;
    this.selectedVehicleId = 0;
    this.selectedCellId = 0;
    this.paymentVehicleId = 0;
    this.resetAdminSetupForms();
    this.loadAll();
  }

  /** Entra al parqueadero activo y abre su resumen operativo. */
  continueParkingLot(id: number): void {
    this.selectParkingLot(id);
    this.navigate('dashboard');
  }

  /**
   * Limpia los formularios de estructura (sede, zona y celda) al cambiar de
   * parqueadero: las sedes y zonas de un parqueadero no aplican a otro.
   */
  private resetAdminSetupForms(): void {
    this.lotSiteForm = { name: '', address: '' };
    this.lotZoneForm = { site_id: 0, name: '', code: '' };
    this.lotCellForm = { zone_id: 0, code: '', compatible_type_ids: [] };
  }

  createParkingLot(): void {
    this.api
      .createParkingLot({
        name: this.newParkingName.trim(),
        tax_id: this.newParkingTaxId.trim() || null,
        city: '',
        address: '',
      })
      .subscribe({
        next: (lot: ParkingLotSummary) => {
          this.newParkingName = '';
          this.newParkingTaxId = '';
          this.selectedLotId = lot.id;
          this.done('Parqueadero creado vacío. Configura sede, zonas y celdas desde Parqueaderos.');
          this.loadAll();
          this.loadParkingLots();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  refreshLists(): void {
    this.api.customers().subscribe({
      next: (data) => {
        this.customers = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.vehicles().subscribe({
      next: (data) => {
        this.vehicles = data;
        if (!this.noveltyForm.vehicle_id && data.length) this.noveltyForm.vehicle_id = data[0].id;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.cells().subscribe({
      next: (data) => {
        this.cells = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.movements().subscribe({
      next: (data) => {
        this.movements = data;
        this.busy = false;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => {
        this.fail(err);
        this.busy = false;
      },
    });
    this.api.payments().subscribe({
      next: (data) => {
        this.payments = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.contracts().subscribe({
      next: (data) => {
        this.contracts = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.tariffs().subscribe({
      next: (data) => {
        this.tariffs = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.novelties().subscribe({
      next: (data) => {
        this.novelties = data;
        if (!this.noveltyForm.vehicle_id && this.vehicles.length) this.noveltyForm.vehicle_id = this.vehicles[0].id;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.sites().subscribe({
      next: (data) => {
        this.sites = data;
        if (!this.zoneForm.site_id) this.zoneForm.site_id = data[0]?.id ?? 0;
        if (!this.lotZoneForm.site_id) this.lotZoneForm.site_id = data[0]?.id ?? 0;
        this.loadZones();
        this.loadAdminZones();
        this.loadMapZones();
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.loadParkingLots();
  }

  loadZones(): void {
    if (!this.zoneForm.site_id && this.siteId) this.zoneForm.site_id = this.siteId;
    this.cellForm.zone_id = 0;
    this.api.zones(this.zoneForm.site_id || this.siteId).subscribe({
      next: (data) => {
        this.zones = data;
        this.cellForm.zone_id = data[0]?.id ?? 0;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Zonas del parqueadero activo, usadas por los módulos de administración. */
  loadAdminZones(): void {
    this.api.zones().subscribe({
      next: (data) => {
        this.adminZones = data;
        if (!this.lotZoneForm.site_id) this.lotZoneForm.site_id = data[0]?.site_id ?? 0;
        if (!this.lotCellForm.zone_id) this.lotCellForm.zone_id = data[0]?.id ?? 0;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  navigate(page: Page): void {
    this.page = page;
    this.search = '';
    this.vehicleStatusFilter = 'TODAS';
    this.historyPage = 1;
    this.error = '';
    this.clearNotice();
    this.scrollWorkspaceToTop();
    if (page === 'entry') {
      this.entryPlate = this.selectedVehicle?.plate ?? '';
      this.entryZoneId = 0;
    }
    if (page === 'cells') {
      this.loadMapZones();
    }
    if (page === 'payments') {
      this.api.contracts().subscribe({
        next: (data) => {
          this.contracts = data;
          this.changeDetector.detectChanges();
        },
        error: (err: unknown) => this.fail(err),
      });
    }
    if (page === 'exit') {
      this.exitPlate = '';
      this.exitMovementId = 0;
    }
    if (page === 'parking-lots') {
      this.loadParkingLots();
      this.loadAdminZones();
    }
    if (page === 'employees') {
      this.loadAdminTeam();
    }
    if (page === 'reports') {
      this.loadAdminZones();
      this.loadReport();
    }
    if (page === 'tariffs') {
      this.loadTariffHistory();
    }
  }

  /** Devuelve el area de contenido al inicio al cambiar de modulo. */
  private scrollWorkspaceToTop(): void {
    const el = this.workspaceRef?.nativeElement;
    if (el) el.scrollTop = 0;
    setTimeout(() => {
      const ref = this.workspaceRef?.nativeElement;
      if (ref) ref.scrollTop = 0;
    });
  }

  startEntry(vehicle: Vehicle): void {
    this.navigate('entry');
    this.selectedVehicleId = vehicle.id;
    this.selectedCellId = 0;
    this.entryPlate = vehicle.plate;
    this.entrySiteId = this.sites[0]?.id ?? 0;
    this.entryZoneId = 0;
  }

  /** Abre el módulo de salida con el movimiento ya identificado. */
  openExit(movement: Movement): void {
    this.navigate('exit');
    this.exitMovementId = movement.id;
    this.exitPlate = movement.plate;
  }

  startPayment(vehicle: Vehicle): void {
    this.navigate('payments-register');
    this.paymentVehicleId = vehicle.id;
  }

  toggleCompatible(typeId: number, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.cellForm.compatible_type_ids = checked
      ? [...this.cellForm.compatible_type_ids, typeId]
      : this.cellForm.compatible_type_ids.filter((id) => id !== typeId);
  }
  exitVehicle(vehicle: Vehicle): void {
    const movement = this.movements.find(
      (item) => item.vehicle_id === vehicle.id && !item.exited_at,
    );
    if (movement) this.openExit(movement);
  }
  methodLabel(method: string): string {
    return (
      ({ CASH: 'Efectivo', TRANSFER: 'Transferencia', CARD: 'Tarjeta' } as Record<string, string>)[
        method
      ] ?? method
    );
  }
  monthlyPrice(vehicleId: number): number {
    const vehicle = this.vehicles.find((item) => item.id === Number(vehicleId));
    const tariff = this.tariffs.find((item) => item.vehicle_type_id === vehicle?.vehicle_type_id);
    if (tariff?.amount) return tariff.amount;
    const contract = this.contracts.find((item) => item.vehicle_id === Number(vehicleId));
    if (contract?.tariff) return contract.tariff;
    return 0;
  }

  registerCustomer(): void {
    if (!this.bootstrap) return;
    this.busy = true;
    const editando = this.customerEditingId;
    const payload = { ...this.customerForm, parking_lot_id: this.bootstrap.parking_lot.id };
    const operacion = editando
      ? this.api.updateCustomer(editando, payload)
      : this.api.createCustomer(payload);
    operacion.subscribe({
      next: () => {
        this.customerDialogOpen = false;
        this.customerEditingId = 0;
        this.customerForm = {
          document_type: 'CC',
          document_number: '',
          full_name: '',
          phone: '',
          email: '',
        };
        this.done(editando ? 'Cliente actualizado.' : 'Cliente registrado.');
        this.refreshLists();
        this.reloadDashboard();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  registerVehicle(): void {
    if (!this.bootstrap) return;
    this.busy = true;
    this.api
      .createVehicle({
        ...this.vehicleForm,
        parking_lot_id: this.bootstrap.parking_lot.id,
        plate: this.vehicleForm.plate.toUpperCase().trim(),
      })
      .subscribe({
        next: () => {
          this.vehicleForm = {
            customer_id: 0,
            vehicle_type_id: 0,
            plate: '',
            brand: '',
            color: '',
          };
          this.vehicleDialogOpen = false;
          this.done('Vehículo registrado. Registra su mensualidad para habilitar el ingreso.');
          this.refreshLists();
          this.reloadDashboard();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de operación · flujo de registro de ingreso                  */
  /* ------------------------------------------------------------------ */
  /** Busca el vehículo por placa exacta y prepara la asignación de celda. */
  lookupEntryVehicle(): void {
    const term = this.entryPlate.trim().toUpperCase();
    if (!term) {
      this.error = 'Escribe la placa del vehículo que ingresa.';
      return;
    }
    const vehicle = this.vehicles.find((item) => item.plate.toUpperCase() === term);
    if (!vehicle) {
      this.selectedVehicleId = 0;
      this.selectedCellId = 0;
      this.entryZoneId = 0;
      this.error = `No hay un vehículo registrado con la placa ${term}.`;
      return;
    }
    this.error = '';
    this.clearNotice();
    this.selectedVehicleId = vehicle.id;
    this.entryPlate = vehicle.plate;
    this.selectedCellId = 0;
    this.entrySiteId = this.sites[0]?.id ?? 0;
    this.entryZoneId = 0;
  }

  /** Al cambiar de sede se reinicia la zona y la celda elegidas. */
  onEntrySiteChange(): void {
    this.selectedCellId = 0;
    this.entryZoneId = 0;
  }

  /** Al cambiar de zona se reinicia la celda elegida. */
  onEntryZoneChange(): void {
    this.selectedCellId = 0;
  }

  /** Registra el ingreso solo cuando las cinco comprobaciones se cumplen. */
  confirmEntry(): void {
    if (!this.selectedVehicleId || !this.selectedCellId) {
      this.error = 'Consulta un vehículo y asigna una celda libre.';
      return;
    }
    if (this.entryBlocked) {
      this.error = 'El ingreso está bloqueado: revisa las comprobaciones del vehículo.';
      return;
    }
    this.busy = true;
    this.api.entry(Number(this.selectedVehicleId), Number(this.selectedCellId)).subscribe({
      next: (movement) => {
        this.done(`Ingreso de ${movement.plate} registrado en la celda ${movement.cell_code}.`);
        this.resetEntry();
        this.refreshLists();
        this.reloadDashboard();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  resetEntry(): void {
    this.selectedVehicleId = 0;
    this.selectedCellId = 0;
    this.entryPlate = '';
    this.entrySiteId = 0;
    this.entryZoneId = 0;
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de operación · flujo de registro de salida                   */
  /* ------------------------------------------------------------------ */
  /** Busca el movimiento activo asociado a la placa indicada. */
  lookupExitMovement(): void {
    const term = this.exitPlate.trim().toUpperCase();
    if (!term) {
      this.error = 'Escribe la placa del vehículo que registra salida.';
      return;
    }
    const movement = this.activeMovements.find((item) => item.plate.toUpperCase() === term);
    if (!movement) {
      this.exitMovementId = 0;
      this.error = `El vehículo ${term} no tiene un ingreso activo.`;
      return;
    }
    this.error = '';
    this.clearNotice();
    this.exitMovementId = movement.id;
    this.exitPlate = movement.plate;
  }

  /** Cierra el movimiento activo y libera la celda ocupada. */
  confirmExit(): void {
    const movement = this.exitMovement;
    if (!movement) {
      this.error = 'Busca un movimiento activo antes de confirmar la salida.';
      return;
    }
    this.busy = true;
    this.api.exit(movement.id).subscribe({
      next: () => {
        this.done(`Salida de ${movement.plate} registrada; ${movement.cell_code} queda libre.`);
        this.resetExit();
        this.refreshLists();
        this.reloadDashboard();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  resetExit(): void {
    this.exitMovementId = 0;
    this.exitPlate = '';
  }

  /** Descarta la operación en curso y deja el módulo listo para empezar. */
  cancelOperation(): void {
    this.error = '';
    this.clearNotice();
    if (this.page === 'entry') this.resetEntry();
    if (this.page === 'exit') this.resetExit();
    if (this.page === 'payments-register') this.navigate('payments');
  }

  /** Formatea una fecha ISO como "20 nov 2026". */
  formatDate(value: string | null): string {
    if (!value) return '';
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) return value;
    const months = [
      'ene',
      'feb',
      'mar',
      'abr',
      'may',
      'jun',
      'jul',
      'ago',
      'sep',
      'oct',
      'nov',
      'dic',
    ];
    return `${day} ${months[month - 1]} ${year}`;
  }

  /**
   * Formatea un monto en pesos como "$1.350.000", tal como aparece en el diseño.
   * Se arma a mano porque el pipe de moneda en es-CO separa el símbolo del
   * número ("$ 1.350.000") y el diseño los muestra pegados.
   */
  formatMoney(value: number | null | undefined): string {
    const monto = Math.round(Number(value) || 0);
    const cifras = monto.toLocaleString('es-CO', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    return `$${cifras}`;
  }

  /**
   * Formatea un porcentaje como "77,5 %", con la coma decimal que usa el diseño.
   */
  formatPercent(value: number | null | undefined): string {
    const porcentaje = Number(value) || 0;
    const cifras = porcentaje.toLocaleString('es-CO', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    });
    return `${cifras} %`;
  }

  /**
   * Fecha en formato largo: "Martes, 21 de octubre de 2026".
   * El día se capitaliza porque en español se escribe en minúscula
   * salvo al inicio de la frase, como en el diseño de referencia.
   */
  formatLongDate(value: Date): string {
    const capitalizar = (texto: string): string =>
      texto.charAt(0).toUpperCase() + texto.slice(1);
    const dia = capitalizar(
      value.toLocaleDateString('es-CO', { weekday: 'long' }),
    );
    const mes = value.toLocaleDateString('es-CO', { month: 'long' });
    return `${dia}, ${value.getDate()} de ${mes} de ${value.getFullYear()}`;
  }

  openPaymentDialog(): void {
    this.paymentDialogOpen = true;
    this.paymentVehicleId = 0;
    this.paymentMonths = 1;
    this.paymentMethod = 'TRANSFER';
  }

  closePaymentDialog(): void {
    this.paymentDialogOpen = false;
  }

  openPaymentHistory(vehicleId: number): void {
    this.paymentHistoryVehicleId = vehicleId;
  }

  closePaymentHistory(): void {
    this.paymentHistoryVehicleId = 0;
  }

  /** Documento del propietario de un vehículo. */
  customerDocument(customerId: number | undefined): string {
    if (!customerId) return 'Sin cliente';
    const customer = this.customers.find((item) => item.id === customerId);
    if (!customer) return 'Sin cliente';
    return `${customer.document_type ?? 'CC'} ${customer.document_number}`;
  }

  /** Ubicación legible de la celda de un movimiento: sede / zona / celda. */
  cellLocation(movement: Movement): string {
    const cell = this.cells.find((item) => item.id === movement.cell_id);
    if (!cell) return movement.cell_code;
    return `${cell.site_name} / ${cell.zone_name} / ${cell.code}`;
  }

  registerPayment(): void {
    if (!this.paymentVehicleId) {
      this.error = 'Selecciona el vehículo al que se aplicará el pago.';
      return;
    }
    this.busy = true;
    this.api
      .createPayment(Number(this.paymentVehicleId), Number(this.paymentMonths), this.paymentMethod)
      .subscribe({
        next: (payment) => {
          this.done(
            `Pago de ${this.formatMoney(payment.amount)} registrado hasta ${this.formatDate(payment.period_end)}.`,
          );
          this.paymentVehicleId = 0;
          this.paymentMonths = 1;
          this.paymentDialogOpen = false;
          this.busy = false;
          this.refreshLists();
          this.reloadDashboard();
        },
        error: (err: unknown) => {
          this.fail(err);
          this.busy = false;
        },
      });
  }

  addCell(): void {
    if (!this.cellForm.compatible_type_ids.length) {
      this.error = 'Selecciona al menos un tipo de vehículo compatible.';
      return;
    }
    this.api.createCell(this.cellForm).subscribe({
      next: () => {
        this.cellForm.code = '';
        this.cellForm.compatible_type_ids = [];
        this.cellDialogOpen = false;
        this.done('Celda agregada al inventario.');
        this.refreshLists();
        this.reloadDashboard();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  toggleCell(cell: Cell): void {
    const next = cell.operational_status === 'ACTIVE' ? 'MAINTENANCE' : 'ACTIVE';
    this.api.updateCellStatus(cell.id, next).subscribe({
      next: () => {
        this.done(`Celda ${cell.code}: ${next === 'ACTIVE' ? 'operativa' : 'en mantenimiento'}.`);
        this.refreshLists();
        this.reloadDashboard();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  addSite(): void {
    if (!this.bootstrap) return;
    this.api
      .createSite({ ...this.siteForm, parking_lot_id: this.bootstrap.parking_lot.id })
      .subscribe({
        next: (site) => {
          this.siteForm = { name: '', address: '' };
          this.done('Sede creada.');
          this.loadAll();
          this.zoneForm.site_id = site.id;
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  addZone(): void {
    this.api.createZone(this.zoneForm).subscribe({
      next: () => {
        this.zoneForm.name = '';
        this.done('Zona creada.');
        this.loadZones();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  saveParking(): void {
    this.api.saveParkingDetails(this.parkingName, this.parkingTaxId).subscribe({
      next: () => {
        this.done('Datos del parqueadero guardados.');
        this.loadAll();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  saveTariff(tariff: Tariff): void {
    this.api.updateTariff(tariff.vehicle_type_id, Number(tariff.amount)).subscribe({
      next: () => {
        this.done(`Tarifa de ${tariff.type_name} actualizada.`);
        this.api.tariffs().subscribe((items) => (this.tariffs = items));
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de administración · parqueaderos                              */
  /* ------------------------------------------------------------------ */
  /** Parqueadero activo según el selector superior. */
  get activeLot(): ParkingLotSummary | undefined {
    return this.parkingLots.find((lot) => lot.id === this.selectedLotId);
  }
  /** Paso del onboarding: 1 sede · 2 zona · 3 celdas · 0 listo para operar. */
  get lotSetupStep(): number {
    const lot = this.activeLot;
    if (!lot) return 0;
    if (!lot.sites_count) return 1;
    if (!lot.zones_count) return 2;
    if (!lot.cells_total) return 3;
    return 0;
  }
  /** Zonas del parqueadero activo, para la configuración de estructura. */
  get lotZones(): Zone[] {
    return this.adminZones;
  }

  /** Filas de inventario agrupadas por zona y tipo compatible. */
  get configInventoryRows(): { zone: string; typeLabel: string; total: number; occupied: number; available: number; maintenance: number }[] {
    const groups = new Map<string, { zone: string; typeLabel: string; total: number; occupied: number; available: number; maintenance: number }>();
    for (const cell of this.cells) {
      const typeNames = cell.compatible_types.map((t) => t.name).sort();
      const typeLabel = typeNames.join(' / ') || 'Sin tipo';
      const key = `${cell.zone_name}::${typeLabel}`;
      if (!groups.has(key)) {
        groups.set(key, { zone: cell.zone_name, typeLabel, total: 0, occupied: 0, available: 0, maintenance: 0 });
      }
      const row = groups.get(key)!;
      row.total++;
      if (cell.operational_status === 'MAINTENANCE') row.maintenance++;
      else if (cell.occupied) row.occupied++;
      else row.available++;
    }
    return Array.from(groups.values()).sort((a, b) => a.zone.localeCompare(b.zone));
  }

  /** Totales generales del inventario de celdas. */
  get configInventoryTotals(): { total: number; occupied: number; available: number; maintenance: number } {
    return this.configInventoryRows.reduce(
      (acc, row) => ({
        total: acc.total + row.total,
        occupied: acc.occupied + row.occupied,
        available: acc.available + row.available,
        maintenance: acc.maintenance + row.maintenance,
      }),
      { total: 0, occupied: 0, available: 0, maintenance: 0 },
    );
  }

  /** Celdas compatibles por tipo de vehículo, para la tabla de compatibilidad. */
  get configTypeRows(): { name: string; compatible: string; assignment: string }[] {
    return this.vehicleTypes.map((type) => {
      const count = this.cells.filter((c) => c.compatible_types.some((t) => t.id === type.id)).length;
      return { name: type.name, compatible: type.code === 'MOTO' ? 'Moto' : 'Carro / camioneta', assignment: count > 0 ? 'Libre operativa' : 'Sin celdas' };
    });
  }

  /** Resumen de zonas con conteo de celdas por tipo, para el panel de estructura. */
  get configZoneSummary(): { name: string; detail: string }[] {
    return this.adminZones.map((zone) => {
      const zoneCells = this.cells.filter((c) => c.zone_id === zone.id);
      const carCells = zoneCells.filter((c) => c.compatible_types.some((t) => t.code !== 'MOTO')).length;
      const motoCells = zoneCells.filter((c) => c.compatible_types.every((t) => t.code === 'MOTO')).length;
      let detail = '';
      if (carCells > 0) detail = `${carCells} carros / camionetas`;
      if (motoCells > 0) detail = detail ? `${detail} · ${motoCells} motos` : `${motoCells} motos`;
      if (!detail) detail = `${zoneCells.length} celdas`;
      return { name: zone.name, detail };
    });
  }

  loadParkingLots(): void {
    this.api.parkingLots().subscribe({
      next: (data) => {
        this.parkingLots = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  openParkingLotDialog(): void {
    this.parkingLotDialogOpen = true;
    this.error = '';
    this.clearNotice();
  }

  closeParkingLotDialog(): void {
    this.parkingLotDialogOpen = false;
  }

  submitParkingLot(): void {
    const name = this.parkingLotForm.name.trim();
    if (name.length < 2) {
      this.error = 'Escribe el nombre del parqueadero.';
      return;
    }
    this.busy = true;
    this.api
      .createParkingLot({
        name,
        tax_id: this.parkingLotForm.tax_id.trim() || null,
        city: this.parkingLotForm.city.trim(),
        address: this.parkingLotForm.address.trim(),
      })
      .subscribe({
        next: (lot) => {
          this.parkingLotForm = { name: '', city: '', address: '', tax_id: '' };
          this.parkingLotDialogOpen = false;
          this.done(`Parqueadero "${lot.name}" creado vacío. Configura sede, zonas y celdas.`);
          this.selectedLotId = lot.id;
          this.resetAdminSetupForms();
          this.loadAll();
          this.loadParkingLots();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  /** Crea la sede principal de un parqueadero recién creado. */
  addLotSite(): void {
    const lot = this.activeLot;
    if (!lot) return;
    if (this.lotSiteForm.name.trim().length < 2) {
      this.error = 'Escribe el nombre de la sede.';
      return;
    }
    this.api
      .createSite({
        parking_lot_id: lot.id,
        name: this.lotSiteForm.name.trim(),
        address: this.lotSiteForm.address.trim(),
      })
      .subscribe({
        next: () => {
          this.lotSiteForm = { name: '', address: '' };
          this.done('Sede creada. Continúa con las zonas y las celdas.');
          this.loadAll();
          this.loadParkingLots();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  /** Crea una zona dentro de la sede indicada. */
  addLotZone(): void {
    const siteId = Number(this.lotZoneForm.site_id) || this.sites[0]?.id;
    if (!siteId) {
      this.error = 'Crea primero la sede del parqueadero.';
      return;
    }
    if (this.lotZoneForm.name.trim().length < 2) {
      this.error = 'Escribe el nombre de la zona.';
      return;
    }
    this.api
      .createZone({
        site_id: siteId,
        name: this.lotZoneForm.name.trim(),
        code: this.lotZoneForm.code.trim(),
      })
      .subscribe({
        next: () => {
          this.lotZoneForm = { site_id: siteId, name: '', code: '' };
          this.done('Zona creada. Ahora agrega las celdas físicas.');
          this.loadAdminZones();
          this.loadParkingLots();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  /** Agrega una celda física con su código y compatibilidad. */
  addLotCell(): void {
    const zoneId = Number(this.lotCellForm.zone_id) || this.adminZones[0]?.id;
    if (!zoneId) {
      this.error = 'Crea primero una zona del parqueadero.';
      return;
    }
    if (this.lotCellForm.code.trim().length < 1) {
      this.error = 'Escribe el código de la celda.';
      return;
    }
    if (!this.lotCellForm.compatible_type_ids.length) {
      this.error = 'Selecciona al menos un tipo de vehículo compatible.';
      return;
    }
    this.api
      .createCell({
        zone_id: zoneId,
        code: this.lotCellForm.code.trim(),
        compatible_type_ids: this.lotCellForm.compatible_type_ids,
      })
      .subscribe({
        next: () => {
          this.lotCellForm = { zone_id: zoneId, code: '', compatible_type_ids: [] };
          this.done('Celda agregada al inventario del parqueadero.');
          this.loadAll();
          this.loadParkingLots();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  toggleLotCellType(typeId: number, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    const list = this.lotCellForm.compatible_type_ids;
    if (checked && !list.includes(typeId)) list.push(typeId);
    if (!checked) this.lotCellForm.compatible_type_ids = list.filter((id) => id !== typeId);
  }

  /** Activa o desactiva un parqueadero sin eliminar su histórico. */
  toggleParkingLot(lot: ParkingLotSummary): void {
    this.api.updateParkingLot(lot.id, { active: !lot.active }).subscribe({
      next: () => {
        this.done(`Parqueadero "${lot.name}" ${lot.active ? 'desactivado' : 'activado'}.`);
        this.loadParkingLots();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Ubicación legible de un parqueadero. */
  lotLocation(lot: ParkingLotSummary): string {
    const parts = [lot.city, lot.address].filter((item) => !!item.trim());
    return parts.length ? parts.join(' · ') : 'Sin dirección de referencia';
  }

  /** Estado visible de un parqueadero según su configuración. */
  lotStateLabel(lot: ParkingLotSummary): string {
    if (!lot.active) return 'Inactivo';
    if (!lot.cells_total) return 'Por configurar';
    return '✓ Activo';
  }

  /** Nombres de las sedes de un parqueadero. */
  lotSiteNames(lot: ParkingLotSummary): string {
    return lot.sites.length ? lot.sites.map((site) => site.name).join(' · ') : 'Sin sedes creadas';
  }

  /** Nombres de las zonas de un parqueadero. */
  lotZoneNames(lot: ParkingLotSummary): string {
    return lot.zones.length ? lot.zones.map((zone) => zone.name).join(' · ') : 'Sin zonas creadas';
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de administración · empleados y turnos                       */
  /* ------------------------------------------------------------------ */
  /** Empleados con acceso vigente. */
  get activeEmployees(): Employee[] {
    return this.employees.filter((item) => item.active);
  }
  /** Turnos configurados con su equipo asignado. */
  get shiftCoverage(): Shift[] {
    return this.shifts.filter((item) => item.active);
  }
  /** Turno que cubre la hora actual. */
  get currentShift(): Shift | undefined {
    const minutes = this.clockMinutes(new Date());
    return this.shifts.find((shift) => this.shiftCovers(shift, minutes));
  }
  /** Próximo turno por iniciar según su horario de referencia. */
  get nextShift(): Shift | undefined {
    const minutes = this.clockMinutes(new Date());
    return this.shifts
      .filter((shift) => !this.shiftCovers(shift, minutes))
      .sort((a, b) => this.clockMinutes(a.starts_at) - this.clockMinutes(b.starts_at))[0];
  }
  /** Alcance de cada rol dentro de la interfaz. */
  readonly rolePermissions: { role: string; label: string; description: string }[] = [
    { role: 'OPERATOR', label: 'Operador', description: 'Ingresos, salidas, pagos y novedades' },
    { role: 'ADMIN', label: 'Administradora', description: 'Operación y configuración' },
  ];

  loadAdminTeam(): void {
    this.api.employees().subscribe({
      next: (data) => {
        this.employees = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.shifts().subscribe({
      next: (data) => {
        this.shifts = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
    this.api.activity(10).subscribe({
      next: (data) => {
        this.activity = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Minutos desde medianoche de una hora "HH:MM". */
  private clockMinutes(value: string | Date): number {
    if (value instanceof Date) return value.getHours() * 60 + value.getMinutes();
    const [hour, minute] = value.split(':').map(Number);
    return (hour || 0) * 60 + (minute || 0);
  }

  /** True si el instante cae dentro del horario del turno (soporta cruce de medianoche). */
  private shiftCovers(shift: Shift, minutes: number): boolean {
    const start = this.clockMinutes(shift.starts_at);
    const end = this.clockMinutes(shift.ends_at);
    if (start === end) return true;
    return start < end
      ? minutes >= start && minutes < end
      : minutes >= start || minutes < end;
  }

  employeeRoleLabel(role: string): string {
    const found = this.rolePermissions.find((item) => item.role === role);
    return found ? found.label : role;
  }

  /** Abre el diálogo de empleado con los datos para edición, o vacío para crear. */
  openEmployeeDialog(employee?: Employee): void {
    if (employee) {
      this.editingEmployeeId = employee.id;
      this.editingEmployeeActive = employee.active;
      this.employeeForm = {
        full_name: employee.full_name,
        document_number: employee.document_number,
        username: employee.username,
        role: employee.role,
        shift_id: employee.shift_id ?? 0,
      };
    } else {
      this.editingEmployeeId = 0;
      this.editingEmployeeActive = false;
      this.employeeForm = { full_name: '', document_number: '', username: '', role: 'OPERATOR', shift_id: 0 };
    }
    this.employeeDialogOpen = true;
  }

  /** Cierra el diálogo de empleado. */
  closeEmployeeDialog(): void {
    this.employeeDialogOpen = false;
    this.cancelEmployeeEdit();
  }

  /** Desactiva o reactiva el acceso de un empleado por id. */
  toggleEmployeeById(id: number): void {
    const employee = this.employees.find((e) => e.id === id);
    if (!employee) return;
    this.toggleEmployee(employee);
  }

  /** Abre el formulario de edición con los datos del empleado. */
  editEmployee(employee: Employee): void {
    this.editingEmployeeId = employee.id;
    this.employeeForm = {
      full_name: employee.full_name,
      document_number: employee.document_number,
      username: employee.username,
      role: employee.role,
      shift_id: employee.shift_id ?? 0,
    };
  }

  cancelEmployeeEdit(): void {
    this.editingEmployeeId = 0;
    this.employeeForm = { full_name: '', document_number: '', username: '', role: 'OPERATOR', shift_id: 0 };
  }

  submitEmployee(): void {
    const fullName = this.employeeForm.full_name.trim();
    const username = this.employeeForm.username.trim();
    if (fullName.length < 2) {
      this.error = 'Escribe el nombre completo del empleado.';
      return;
    }
    if (username.length < 3) {
      this.error = 'El usuario debe tener al menos 3 caracteres.';
      return;
    }
    const payload = {
      full_name: fullName,
      username,
      role: this.employeeForm.role,
      shift_id: this.employeeForm.shift_id ? Number(this.employeeForm.shift_id) : null,
    };
    const request = this.editingEmployeeId
      ? this.api.updateEmployee(this.editingEmployeeId, payload)
      : this.api.createEmployee({
          ...payload,
          parking_lot_id: this.selectedLotId,
          document_number: this.employeeForm.document_number.trim(),
        });
    request.subscribe({
      next: () => {
        this.employeeDialogOpen = false;
        this.cancelEmployeeEdit();
        this.done('Empleado guardado.');
        this.loadAdminTeam();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Desactiva o reactiva el acceso de un empleado. */
  toggleEmployee(employee: Employee): void {
    this.api.updateEmployee(employee.id, { active: !employee.active }).subscribe({
      next: () => {
        this.editingEmployeeActive = !employee.active;
        this.done(`Acceso de ${employee.full_name} ${employee.active ? 'desactivado' : 'activado'}.`);
        this.loadAdminTeam();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  submitShift(): void {
    if (this.shiftForm.name.trim().length < 2) {
      this.error = 'Escribe el nombre del turno.';
      return;
    }
    this.api
      .createShift({
        parking_lot_id: this.selectedLotId,
        name: this.shiftForm.name.trim(),
        starts_at: this.shiftForm.starts_at,
        ends_at: this.shiftForm.ends_at,
        notes: this.shiftForm.notes.trim(),
      })
      .subscribe({
        next: () => {
          this.shiftForm = { name: '', starts_at: '06:00', ends_at: '18:00', notes: '' };
          this.done('Turno creado.');
          this.loadAdminTeam();
        },
        error: (err: unknown) => this.fail(err),
      });
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de administración · reportes operativos                       */
  /* ------------------------------------------------------------------ */
  /** Zonas disponibles para el filtro de reporte. */
  get reportZones(): Zone[] {
    return this.adminZones;
  }

  loadReport(): void {
    this.busy = true;
    this.api
      .report({
        report_date: this.reportFilters.report_date || undefined,
        site_id: this.reportFilters.site_id || undefined,
        zone_id: this.reportFilters.zone_id || undefined,
        vehicle_type_id: this.reportFilters.vehicle_type_id || undefined,
        page: this.reportPage,
        page_size: this.reportPageSize,
      })
      .subscribe({
        next: (data) => {
          this.report = data;
          this.busy = false;
          this.changeDetector.detectChanges();
        },
        error: (err: unknown) => {
          this.busy = false;
          this.fail(err);
        },
      });
  }

  onReportFilterChange(): void {
    this.reportPage = 1;
    this.loadReport();
  }

  get reportTotalPages(): number {
    return Math.max(1, Math.ceil((this.report?.movements_total ?? 0) / this.reportPageSize));
  }

  /** Páginas disponibles para la tabla de movimientos. */
  get reportPages(): number[] {
    return Array.from({ length: this.reportTotalPages }, (_, index) => index + 1);
  }

  /** Restablece los filtros del reporte al estado inicial. */
  resetReportFilters(): void {
    this.reportFilters = { site_id: 0, zone_id: 0, vehicle_type_id: 0, report_date: '' };
    this.reportPage = 1;
    this.loadReport();
  }

  /** Porcentaje que representa un grupo de mensualidades sobre el total. */
  monthlyShare(count: number): number {
    const total =
      (this.report?.monthly.active ?? 0) +
      (this.report?.monthly.expiring_soon ?? 0) +
      (this.report?.monthly.expired ?? 0);
    return total ? (count * 100) / total : 0;
  }

  /** Porcentaje de una barra de flujo frente a la mayor cifra del día. */
  flowShare(value: number): number {
    const flow = this.report?.flow;
    const max = flow ? Math.max(flow.entries, flow.exits, 1) : 1;
    return (value * 100) / max;
  }

  /** Altura en píxeles de la barra de flujo (máx 50px). */
  flowBarHeight(value: number): number {
    const flow = this.report?.flow;
    const max = flow ? Math.max(flow.entries, flow.exits, 1) : 1;
    return Math.max(4, Math.round((value / max) * 50));
  }

  /** Abre el diálogo de impresión del navegador para guardar el reporte en PDF. */
  printReport(): void {
    window.print();
  }

  get reportPaginationFrom(): number {
    const total = this.report?.movements_total ?? 0;
    return total ? (this.reportPage - 1) * this.reportPageSize + 1 : 0;
  }

  get reportPaginationTo(): number {
    return Math.min(this.reportPage * this.reportPageSize, this.report?.movements_total ?? 0);
  }

  goToReportPage(page: number): void {
    this.reportPage = Math.min(Math.max(1, page), this.reportTotalPages);
    this.loadReport();
  }

  /** Exporta el reporte a CSV con los datos consultados en pantalla. */
  exportReportCsv(): void {
    const report = this.report;
    if (!report) return;
    const rows: string[][] = [
      ['Reporte operativo', report.parking_lot.name],
      ['Fecha de corte', report.report_date],
      [],
      ['Indicador', 'Valor'],
      ['Clientes registrados', String(report.indicators.customers)],
      ['Vehículos registrados', String(report.indicators.vehicles)],
      ['Vehículos dentro', String(report.indicators.vehicles_inside)],
      ['Ocupación física', `${report.indicators.occupancy_rate} %`],
      ['Celdas operativas', String(report.indicators.cells_total)],
      ['Celdas ocupadas', String(report.indicators.cells_occupied)],
      ['Celdas disponibles', String(report.indicators.cells_available)],
      ['Pagos del día', String(report.indicators.payments_amount)],
      [],
      ['Tipo', 'Total', 'Ocupadas', 'Libres', 'Mantenimiento'],
      ...report.inventory.map((row) => [
        row.type_name,
        String(row.total),
        String(row.occupied),
        String(row.available),
        String(row.maintenance),
      ]),
      [],
      ['Cobertura de mensualidades', 'Vehículos'],
      ['Vigentes', String(report.monthly.active)],
      ['Próximas a vencer', String(report.monthly.expiring_soon)],
      ['Vencidas', String(report.monthly.expired)],
      [],
      ['Método de pago', 'Importe', 'Pagos'],
      ...report.payments_by_method.map((row) => [
        this.methodLabel(row.method),
        String(row.amount),
        String(row.count),
      ]),
      [],
      ['Vehículo', 'Tipo', 'Ingreso', 'Salida', 'Celda', 'Zona', 'Estado'],
      ...report.movements.map((row) => [
        row.plate,
        row.type_name,
        row.entered_at,
        row.exited_at ?? '',
        row.cell_code,
        row.zone_name,
        row.state,
      ]),
    ];
    const csv = rows
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(';'))
      .join('\r\n');
    const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `reporte-operativo-${report.report_date}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    this.done('Reporte exportado en CSV.');
  }

  /* ------------------------------------------------------------------ */
  /* Módulo de administración · tarifas y vigencias                       */
  /* ------------------------------------------------------------------ */
  /** Vigencias vigentes y programadas. */
  get activeTariffs(): TariffHistory[] {
    const filtered = this.tariffHistory.filter((item) => item.state !== 'CERRADA');
    return this.mergeCarTruckTariffs(filtered);
  }

  /** Combina tarifas de CAR y TRUCK en una sola fila "Carro / camioneta". */
  private mergeCarTruckTariffs(rows: TariffHistory[]): TariffHistory[] {
    const carIdx = rows.findIndex((r) => r.type_code === 'CAR');
    const truckIdx = rows.findIndex((r) => r.type_code === 'TRUCK');
    if (carIdx < 0 && truckIdx < 0) return rows;
    const representative = carIdx >= 0 ? rows[carIdx] : rows[truckIdx];
    const insertAt = carIdx >= 0 ? carIdx : truckIdx;
    const merged: TariffHistory = {
      ...representative,
      type_name: 'Carro / camioneta',
      type_code: 'CAR_TRUCK',
      vehicle_type_id: representative.vehicle_type_id,
    };
    const result = rows.filter((r) => r.type_code !== 'CAR' && r.type_code !== 'TRUCK');
    result.splice(insertAt, 0, merged);
    return result;
  }
  /** Vigencias ya cerradas: solo lectura. */
  get closedTariffs(): TariffHistory[] {
    return this.tariffHistory.filter((item) => item.state === 'CERRADA');
  }
  /** Cobertura de ejemplo del ciclo mensual. */
  get tariffCycle(): string {
    return 'Mensual · Día aniversario';
  }

  /** Ejemplo de cobertura de una vigencia mensual, calculada sobre la tarifa vigente. */
  get tariffCoverageExample(): string {
    const first = this.activeTariffs
      .filter((item) => item.state === 'VIGENTE')
      .sort((a, b) => a.effective_from.localeCompare(b.effective_from))[0];
    if (!first) return 'Sin vigencias vigentes';
    return `${this.formatDate(first.effective_from)} → ${this.formatDate(this.addMonthToIso(first.effective_from))}`;
  }

  /** Suma un mes a una fecha ISO (YYYY-MM-DD) sin alterar el día. */
  private addMonthToIso(iso: string): string {
    const [year, month, day] = iso.split('-').map(Number);
    if (!year || !month || !day) return iso;
    const next = new Date(year, month - 1, 1);
    next.setMonth(next.getMonth() + 1);
    const lastDay = new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate();
    const safeDay = Math.min(day, lastDay);
    const pad = (value: number) => String(value).padStart(2, '0');
    return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(safeDay)}`;
  }

  loadTariffHistory(): void {
    this.api.tariffHistory().subscribe({
      next: (data) => {
        this.tariffHistory = data;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  tariffStateLabel(state: string): string {
    if (state === 'VIGENTE') return 'Activa · Vigente';
    if (state === 'PROGRAMADA') return 'Programada';
    return 'Cerrada · Solo lectura';
  }

  submitTariff(): void {
    const typeId = Number(this.tariffForm.vehicle_type_id);
    if (!typeId) {
      this.error = 'Selecciona el tipo de vehículo de la tarifa.';
      return;
    }
    if (!this.tariffForm.amount || Number(this.tariffForm.amount) <= 0) {
      this.error = 'Escribe un importe mensual mayor que cero.';
      return;
    }
    if (!this.tariffForm.effective_from) {
      this.error = 'Indica la fecha de inicio de la vigencia.';
      return;
    }
    if (this.tariffForm.effective_until && this.tariffForm.effective_until < this.tariffForm.effective_from) {
      this.error = 'El fin de vigencia no puede ser anterior al inicio.';
      return;
    }
    this.busy = true;
    this.api
      .createTariff({
        vehicle_type_id: typeId,
        amount: Number(this.tariffForm.amount),
        effective_from: this.tariffForm.effective_from,
        effective_until: this.tariffForm.effective_until || null,
        note: this.tariffForm.note.trim(),
      })
      .subscribe({
        next: () => {
          this.tariffForm = {
            vehicle_type_id: typeId,
            amount: 0,
            effective_from: '',
            effective_until: '',
            note: '',
          };
          this.busy = false;
          this.done('Vigencia de tarifa registrada.');
          this.loadTariffHistory();
          this.refreshLists();
        },
        error: (err: unknown) => {
          this.busy = false;
          this.fail(err);
        },
      });
  }

  /** Filas visibles de la tabla de novedades según la búsqueda activa. */
  get filteredNovelties(): Novelty[] {
    const query = this.noveltyQuery.trim().toLowerCase();
    if (!query) return this.novelties;
    return this.novelties.filter(
      (item) =>
        item.plate.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query) ||
        item.description.toLowerCase().includes(query),
    );
  }

  get noveltyTotalPages(): number {
    return Math.max(1, Math.ceil(this.filteredNovelties.length / 5));
  }

  get noveltyPages(): number[] {
    return Array.from({ length: this.noveltyTotalPages }, (_, index) => index + 1);
  }

  get pagedNovelties(): Novelty[] {
    const start = (this.noveltyPage - 1) * 5;
    return this.filteredNovelties.slice(start, start + 5);
  }

  goToNoveltyPage(page: number): void {
    this.noveltyPage = Math.min(Math.max(1, page), this.noveltyTotalPages);
  }

  /** Etiqueta en español del estado de una novedad. */
  noveltyStatusLabel(status: string): string {
    const labels: Record<string, string> = { OPEN: 'Abierta', RESOLVED: 'Resuelta', IN_PROGRESS: 'En seguimiento' };
    return labels[status] ?? status;
  }

  /** Última novedad registrada sobre el vehículo que se está consultando. */
  get vehicleLastNovelty(): Novelty | undefined {
    const plate = this.movements[0]?.plate;
    if (!plate) return undefined;
    return this.novelties.find((item) => item.plate === plate);
  }

  registerNovelty(): void {
    this.api.createNovelty(this.noveltyForm).subscribe({
      next: () => {
        this.noveltyForm = {
          vehicle_id: this.vehicles[0]?.id ?? 0,
          category: 'Observación de vehículo',
          description: '',
        };
        this.done('Novedad registrada.');
        this.refreshLists();
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  typeCapacity(code: string): { total: number; occupied: number; available: number } {
    return this.dashboard?.occupancy_by_type[code] ?? { total: 0, occupied: 0, available: 0 };
  }

  /** Una celda sirve para el ingreso si está operativa, libre y es compatible. */
  private entryCellFits(cell: Cell): boolean {
    const vehicle = this.selectedVehicle;
    if (!vehicle) return false;
    return (
      cell.operational_status === 'ACTIVE' &&
      !cell.occupied &&
      cell.compatible_types.some((type) => type.id === vehicle.vehicle_type_id)
    );
  }

  private reloadDashboard(): void {
    this.api.dashboard().subscribe({
      next: (value) => {
        this.dashboard = value;
        this.changeDetector.detectChanges();
      },
      error: (err: unknown) => this.fail(err),
    });
  }
  /** Limpia el aviso en pantalla y cancela el temporizador que lo retira. */
  private clearNotice(): void {
    if (this.noticeTimer) {
      clearTimeout(this.noticeTimer);
      this.noticeTimer = null;
    }
    this.notice = '';
  }

  private done(message: string): void {
    this.busy = false;
    this.error = '';
    this.notice = message;
    this.changeDetector.detectChanges();
    if (this.noticeTimer) clearTimeout(this.noticeTimer);
    this.noticeTimer = setTimeout(() => {
      this.clearNotice();
      this.changeDetector.detectChanges();
    }, 5000);
  }

  private fail(error: unknown): void {
    this.busy = false;
    const response = error as HttpErrorResponse;
    const detail = response?.error?.detail;
    this.error =
      typeof detail === 'string'
        ? detail
        : response?.message ||
          'No fue posible completar la operación. Revisa que el backend esté activo.';
    this.changeDetector.detectChanges();
  }
}
