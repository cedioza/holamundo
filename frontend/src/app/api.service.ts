import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';

export interface VehicleType { id: number; code: string; name: string; }
export interface ParkingLot { id: number; name: string; tax_id: string | null; }
export interface ParkingLotSummary {
  id: number; name: string; tax_id: string | null; city: string; address: string; active: boolean;
  sites_count: number; sites: { id: number; name: string; address: string }[];
  zones_count: number; zones: { id: number; name: string; code: string; site_id: number }[];
  cells_total: number; cells_active: number; cells_maintenance: number;
  cells_occupied: number; cells_available: number;
  customers: number; vehicles: number; vehicles_inside: number;
}
export interface Site { id: number; name: string; address: string; }
export interface Zone { id: number; site_id: number; name: string; code: string; }
export interface Bootstrap { parking_lot: ParkingLot; parking_lots: ParkingLot[]; sites: Site[]; vehicle_types: VehicleType[]; }
export interface Customer { id: number; document_type?: string; document_number: string; full_name: string; phone: string; email: string; vehicles_count: number; }
export interface Vehicle {
  id: number; customer_id: number; customer_name: string; vehicle_type_id: number; type_code: string;
  type_name: string; plate: string; brand: string; color: string; monthly_status: string;
  expires_on: string | null; inside: boolean; movement_id: number | null; cell_code: string | null;
  customer_document_type?: string; customer_document_number?: string;
}
export interface Cell {
  id: number; zone_id: number; zone_name: string; site_id: number; site_name: string; code: string;
  operational_status: string; occupied: boolean; vehicle_id: number | null; vehicle_plate: string | null;
  compatible_types: VehicleType[];
}
export interface Movement { id: number; vehicle_id: number; plate: string; brand: string; color: string; type_name: string; customer_name: string; cell_id: number; cell_code: string; zone_name?: string; site_name?: string; entered_at: string; exited_at: string | null; entry_employee: string | null; exit_employee: string | null; }
export interface OccupancyGroup { total: number; occupied: number; maintenance: number; available: number; }
export interface Dashboard {
  parking_lot_id: number; customers_registered: number; vehicles_registered: number; vehicles_inside: number;
  cells_total: number; cells_occupied: number; cells_available: number; cells_maintenance: number;
  occupancy_by_type: Record<string, { total: number; occupied: number; available: number }>;
  occupancy_by_group: Record<string, OccupancyGroup>;
  monthly_active: number; monthly_expired: number; monthly_expiring_soon: number;
  payments_this_month: number;
  payments_today: number; payments_today_count: number;
}
export interface Payment { id: number; vehicle_id?: number; plate: string; amount: number; paid_at: string; period_start: string; period_end: string; method: string; received_by?: string | null; }
export interface ContractRow {
  vehicle_id: number; plate: string; type_name: string; customer_name: string;
  customer_document: string; customer_document_type: string;
  contract_id: number | null; contract_code: string | null; contract_state: string;
  monthly_status: 'VIGENTE' | 'ANTICIPADA' | 'VENCIDA'; expiring_soon: boolean;
  coverage_start: string | null; coverage_end: string | null;
  period_start: string | null; period_end: string | null;
  tariff: number; paid_amount: number; last_paid_at: string | null; payments_count: number;
}
export interface Tariff { id: number; vehicle_type_id: number; type_name: string; amount: number; effective_from: string; effective_until: string | null; }
export type TariffState = 'VIGENTE' | 'PROGRAMADA' | 'CERRADA';
export interface TariffHistory extends Tariff {
  parking_lot_id: number; type_code: string; note: string; state: TariffState;
}
export interface Novelty { id: number; vehicle_id: number; plate: string; category: string; description: string; created_at: string; status: string; employee_name?: string | null; }
export interface Shift {
  id: number; parking_lot_id: number; name: string; starts_at: string; ends_at: string;
  active: boolean; notes: string; employees: { id: number; full_name: string; role: string }[];
}
export interface Employee {
  id: number; parking_lot_id: number; full_name: string; document_number: string;
  username: string; role: string; active: boolean; shift_id: number | null; shift: Shift | null;
}
export interface ActivityItem {
  id: string; occurred_at: string; employee: string | null; operation: string;
  kind: 'ENTRY' | 'EXIT' | 'PAYMENT';
}
export interface ReportInventoryRow {
  vehicle_type_id: number; type_name: string; total: number; occupied: number; available: number; maintenance: number;
}
export interface ReportMovement {
  id: number; plate: string; type_name: string; entered_at: string; exited_at: string | null;
  cell_code: string; zone_name: string; entry_employee: string | null; exit_employee: string | null;
  state: 'ACTIVO' | 'CERRADO';
}
export interface Report {
  parking_lot: { id: number; name: string };
  report_date: string;
  cutoff: string;
  indicators: {
    customers: number; vehicles: number; vehicles_inside: number; vehicles_outside: number;
    cells_total: number; cells_occupied: number; cells_available: number; cells_maintenance: number;
    occupancy_rate: number; payments_amount: number; payments_count: number;
  };
  inventory: ReportInventoryRow[];
  monthly: { active: number; expiring_soon: number; expired: number; };
  payments_by_method: { method: string; amount: number; count: number }[];
  flow: { entries: number; exits: number; inside_at_start: number; inside_now: number; };
  movements: ReportMovement[];
  movements_total: number;
  movements_page: number;
  movements_page_size: number;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = 'http://127.0.0.1:8000/api';
  private activeLotId = 1;

  setParkingLot(id: number): void { this.activeLotId = id; }
  private scopedParams(values: Record<string, string | number | boolean> = {}): HttpParams {
    let params = new HttpParams().set('parking_lot_id', this.activeLotId);
    for (const [key, value] of Object.entries(values)) params = params.set(key, value);
    return params;
  }

  bootstrap(id = this.activeLotId): Observable<Bootstrap> {
    this.activeLotId = id;
    return this.http.get<Bootstrap>(`${this.base}/bootstrap`, { params: this.scopedParams() });
  }
  parkingLots(): Observable<ParkingLotSummary[]> { return this.http.get<ParkingLotSummary[]>(`${this.base}/parking-lots`); }
  createParkingLot(payload: { name: string; tax_id: string | null; city: string; address: string }): Observable<ParkingLotSummary> {
    return this.http.post<ParkingLotSummary>(`${this.base}/parking-lots`, payload);
  }
  updateParkingLot(id: number, payload: Partial<ParkingLotSummary>): Observable<ParkingLotSummary> {
    return this.http.patch<ParkingLotSummary>(`${this.base}/parking-lots/${id}`, payload);
  }
  saveParkingDetails(name: string, tax_id: string): Observable<unknown> {
    return this.http.patch(`${this.base}/parking-lot`, { name, tax_id: tax_id || null }, { params: this.scopedParams() });
  }
  dashboard(): Observable<Dashboard> { return this.http.get<Dashboard>(`${this.base}/dashboard`, { params: this.scopedParams() }); }
  customers(search = ''): Observable<Customer[]> { return this.http.get<Customer[]>(`${this.base}/customers`, { params: this.scopedParams(search ? { search } : {}) }); }
  createCustomer(payload: Partial<Customer> & { parking_lot_id: number; document_type: string }): Observable<Customer> { return this.http.post<Customer>(`${this.base}/customers`, payload); }
  updateCustomer(id: number, payload: Partial<Customer> & { parking_lot_id: number; document_type: string }): Observable<Customer> {
    return this.http.put<Customer>(`${this.base}/customers/${id}`, payload);
  }
  vehicles(search = ''): Observable<Vehicle[]> { return this.http.get<Vehicle[]>(`${this.base}/vehicles`, { params: this.scopedParams(search ? { search } : {}) }); }
  createVehicle(payload: { parking_lot_id: number; customer_id: number; vehicle_type_id: number; plate: string; brand: string; color: string }): Observable<Vehicle> { return this.http.post<Vehicle>(`${this.base}/vehicles`, payload); }
  cells(): Observable<Cell[]> { return this.http.get<Cell[]>(`${this.base}/cells`, { params: this.scopedParams() }); }
  createCell(payload: { zone_id: number; code: string; compatible_type_ids: number[] }): Observable<Cell> { return this.http.post<Cell>(`${this.base}/cells`, payload, { params: this.scopedParams() }); }
  updateCellStatus(id: number, operational_status: string): Observable<Cell> { return this.http.patch<Cell>(`${this.base}/cells/${id}/status`, { operational_status }); }
  sites(): Observable<Site[]> { return this.http.get<Site[]>(`${this.base}/sites`, { params: this.scopedParams() }); }
  createSite(payload: { parking_lot_id: number; name: string; address: string }): Observable<Site> { return this.http.post<Site>(`${this.base}/sites`, payload); }
  zones(siteId?: number): Observable<Zone[]> { return this.http.get<Zone[]>(`${this.base}/zones`, { params: this.scopedParams(siteId ? { site_id: siteId } : {}) }); }
  createZone(payload: { site_id: number; name: string; code?: string }): Observable<Zone> { return this.http.post<Zone>(`${this.base}/zones`, payload, { params: this.scopedParams() });}
  movements(active = false): Observable<Movement[]> { return this.http.get<Movement[]>(`${this.base}/movements`, { params: this.scopedParams({ active }) }); }
  entry(vehicle_id: number, cell_id: number): Observable<Movement> { return this.http.post<Movement>(`${this.base}/movements/entry`, { vehicle_id, cell_id }); }
  exit(movementId: number): Observable<unknown> { return this.http.post(`${this.base}/movements/${movementId}/exit`, {}, { params: this.scopedParams() }); }
  payments(): Observable<Payment[]> { return this.http.get<Payment[]>(`${this.base}/payments`, { params: this.scopedParams() }); }
  contracts(): Observable<ContractRow[]> { return this.http.get<ContractRow[]>(`${this.base}/contracts`, { params: this.scopedParams() }); }
  createPayment(vehicle_id: number, months: number, method: string): Observable<Payment> { return this.http.post<Payment>(`${this.base}/payments`, { vehicle_id, months, method }); }
  tariffs(): Observable<Tariff[]> { return this.http.get<Tariff[]>(`${this.base}/tariffs`, { params: this.scopedParams() }); }
  tariffHistory(): Observable<TariffHistory[]> { return this.http.get<TariffHistory[]>(`${this.base}/tariffs/history`, { params: this.scopedParams() }); }
  createTariff(payload: { vehicle_type_id: number; amount: number; effective_from: string; effective_until: string | null; note: string }): Observable<TariffHistory> {
    return this.http.post<TariffHistory>(`${this.base}/tariffs`, payload, { params: this.scopedParams() });
  }
  updateTariff(typeId: number, amount: number): Observable<unknown> { return this.http.put(`${this.base}/tariffs/${typeId}`, null, { params: this.scopedParams({ amount }) }); }
  employees(): Observable<Employee[]> { return this.http.get<Employee[]>(`${this.base}/employees`, { params: this.scopedParams() }); }
  createEmployee(payload: { parking_lot_id: number; full_name: string; document_number: string; username: string; role: string; shift_id: number | null }): Observable<Employee> {
    return this.http.post<Employee>(`${this.base}/employees`, payload);
  }
  updateEmployee(id: number, payload: Partial<{ full_name: string; username: string; role: string; shift_id: number | null; active: boolean }>): Observable<Employee> {
    return this.http.patch<Employee>(`${this.base}/employees/${id}`, payload);
  }
  shifts(): Observable<Shift[]> { return this.http.get<Shift[]>(`${this.base}/shifts`, { params: this.scopedParams() }); }
  createShift(payload: { parking_lot_id: number; name: string; starts_at: string; ends_at: string; notes: string }): Observable<Shift> {
    return this.http.post<Shift>(`${this.base}/shifts`, payload);
  }
  updateShift(id: number, payload: Partial<{ name: string; starts_at: string; ends_at: string; notes: string; active: boolean }>): Observable<Shift> {
    return this.http.patch<Shift>(`${this.base}/shifts/${id}`, payload);
  }
  activity(limit = 10): Observable<ActivityItem[]> { return this.http.get<ActivityItem[]>(`${this.base}/activity`, { params: this.scopedParams({ limit }) }); }
  report(filters: { report_date?: string; site_id?: number; zone_id?: number; vehicle_type_id?: number; page?: number; page_size?: number } = {}): Observable<Report> {
    const values: Record<string, string | number> = {};
    if (filters.report_date) values['report_date'] = filters.report_date;
    if (filters.site_id) values['site_id'] = filters.site_id;
    if (filters.zone_id) values['zone_id'] = filters.zone_id;
    if (filters.vehicle_type_id) values['vehicle_type_id'] = filters.vehicle_type_id;
    if (filters.page) values['page'] = filters.page;
    if (filters.page_size) values['page_size'] = filters.page_size;
    return this.http.get<Report>(`${this.base}/reports`, { params: this.scopedParams(values) });
  }
  novelties(): Observable<Novelty[]> { return this.http.get<Novelty[]>(`${this.base}/novelties`, { params: this.scopedParams() }); }
  createNovelty(payload: { vehicle_id: number; category: string; description: string }): Observable<Novelty> { return this.http.post<Novelty>(`${this.base}/novelties`, payload); }
}
