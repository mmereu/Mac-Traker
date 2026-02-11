import axios from 'axios';

const API_BASE_URL = '/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// User-friendly error messages map
const getErrorMessage = (error: any): string => {
  // Network/connection errors (no response)
  if (!error.response) {
    if (error.code === 'ECONNABORTED') {
      return 'La richiesta ha impiegato troppo tempo. Riprova più tardi.';
    }
    if (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error')) {
      return 'Impossibile connettersi al server. Verifica la connessione di rete.';
    }
    return 'Errore di connessione. Verifica che il server sia raggiungibile.';
  }

  // HTTP error responses
  const status = error.response.status;
  const detail = error.response?.data?.detail;

  // Handle FastAPI validation errors (array format)
  if (Array.isArray(detail)) {
    return detail.map((e: any) => {
      // Translate common validation messages to Italian
      if (e.msg?.includes('field required')) return 'Campo obbligatorio mancante';
      if (e.msg?.includes('value is not a valid')) return 'Formato non valido';
      return e.msg || 'Errore di validazione';
    }).join('. ');
  }

  // Handle string detail messages (translate if needed)
  if (typeof detail === 'string') {
    // Return Italian messages directly, translate common English ones
    if (detail.includes('not found')) return 'Elemento non trovato';
    if (detail.includes('already exists')) return 'Elemento già esistente';
    if (detail.includes('permission') || detail.includes('unauthorized')) return 'Accesso non autorizzato';
    return detail;
  }

  // Generic messages based on HTTP status
  switch (status) {
    case 400:
      return 'Richiesta non valida. Verifica i dati inseriti.';
    case 401:
      return 'Sessione scaduta. Effettua nuovamente il login.';
    case 403:
      return 'Accesso non autorizzato a questa risorsa.';
    case 404:
      return 'Elemento non trovato.';
    case 409:
      return 'Conflitto: l\'elemento esiste già o è in uso.';
    case 422:
      return 'I dati inseriti non sono validi.';
    case 500:
      return 'Errore del server. Riprova più tardi.';
    case 502:
    case 503:
    case 504:
      return 'Servizio temporaneamente non disponibile. Riprova tra qualche minuto.';
    default:
      return 'Si è verificato un errore. Riprova più tardi.';
  }
};

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Create user-friendly error message
    const userMessage = getErrorMessage(error);

    // Log technical details to console for debugging (but don't expose to user)
    console.error('API Error:', {
      status: error.response?.status,
      url: error.config?.url,
      method: error.config?.method,
    });

    // Attach user-friendly message to the error object
    error.userMessage = userMessage;

    return Promise.reject(error);
  }
);

// Types
export interface Switch {
  id: number;
  hostname: string;
  ip_address: string;
  device_type: string;
  snmp_community?: string;
  group_id?: number;
  location?: string;
  model?: string;
  serial_number?: string;
  is_active: boolean;
  use_ssh_fallback: boolean;
  last_seen?: string;
  last_discovery?: string;
  created_at: string;
  group?: { id: number; name: string };
  mac_count: number;
  // SNMP-discovered system information
  sys_name?: string;
  ports_up_count?: number;
  ports_down_count?: number;
  vlan_count?: number;
  // Site code extracted from hostname prefix (e.g., "01", "02")
  site_code?: string;
}

export interface SwitchCreate {
  hostname: string;
  ip_address: string;
  device_type?: string;
  snmp_community?: string;
  group_id?: number;
  location?: string;
  model?: string;
  serial_number?: string;
  use_ssh_fallback?: boolean;
}

export interface SwitchGroup {
  id: number;
  name: string;
  description?: string;
  ssh_username?: string;
  ssh_port: number;
  created_at: string;
  updated_at: string;
  switch_count: number;
}

export interface SwitchGroupCreate {
  name: string;
  description?: string;
  ssh_username?: string;
  ssh_password?: string;
  ssh_port?: number;
}

export interface DashboardStats {
  mac_count: number;
  switch_count: number;
  alert_count: number;
  last_discovery?: string;
}

export interface Alert {
  id: number;
  alert_type: string;
  message: string;
  severity: string;
  is_read: boolean;
  created_at: string;
}

export interface MacSearchResult {
  id: number;
  mac_address: string;
  vendor_name?: string;
  device_type?: string;
  ip_address?: string;
  hostname?: string;
  switch_hostname?: string;
  switch_ip?: string;
  port_name?: string;
  vlan_id?: number;
  first_seen: string;
  last_seen: string;
  is_active: boolean;
}

export interface MacLocation {
  switch_hostname: string;
  switch_ip: string;
  port_name: string;
  vlan_id?: number;
  ip_address?: string;
  hostname?: string;
  seen_at: string;
  is_current: boolean;
}

export interface Port {
  id: number;
  switch_id: number;
  port_name: string;
  port_index?: number;
  port_description?: string;
  port_type: string;  // access, trunk, uplink
  vlan_id?: number;
  admin_status: string;
  oper_status: string;
  speed?: string;
  is_uplink: boolean;
  last_mac_count: number;
  updated_at: string;
}

export interface SwitchMac {
  mac_address: string;
  ip_address?: string;
  port_name: string;
  vlan_id?: number;
  vendor_name?: string;
  last_seen: string;
}

export interface DeleteResult {
  deleted_count: number;
  success: boolean;
}

export interface MacHistoryItem {
  event_type: string;
  event_at: string;
  switch_id: number;
  port_id: number;
  vlan_id?: number;
  ip_address?: string;
  previous_switch_id?: number;
  previous_port_id?: number;
}

export interface MacDetail {
  id: number;
  mac_address: string;
  vendor_oui?: string;
  vendor_name?: string;
  device_type?: string;
  first_seen: string;
  last_seen: string;
  is_active: boolean;
  current_location?: MacLocation;
  history: MacHistoryItem[];
}

// Endpoint Tracing Types
export interface EndpointTraceResponse {
  mac_address: string;
  endpoint_switch_hostname: string;
  endpoint_switch_ip: string;
  endpoint_port_name: string;
  vlan_id?: number;
  lldp_device_name?: string;
  is_endpoint: boolean;
  trace_path: string[];
  vendor_name?: string;
}

export interface EndpointInfo {
  switch_hostname: string;
  switch_ip: string;
  port_name: string;
  vlan_id?: number;
  lldp_device_name?: string;
  is_endpoint: boolean;
  trace_path: string[];
}

export interface AllEndpointsResponse {
  mac_address: string;
  vendor_name?: string;
  total: number;
  endpoints: EndpointInfo[];
}

// Site Code Types
export interface SiteCodeInfo {
  code: string;
  count: number;
}

export interface SiteStatsBySite {
  sites: Array<{
    site_code: string;
    site_name: string;
    switch_count: number;
    mac_count: number;
  }>;
  total_sites: number;
  switches_without_site: number;
  macs_without_site: number;
}

// Switch API
export const switchesApi = {
  list: (params?: { search?: string; device_type?: string; group_id?: number; site_code?: string; is_active?: boolean; skip?: number; limit?: number }) =>
    api.get<{ items: Switch[]; total: number }>('/switches', { params }),

  getSiteCodes: () =>
    api.get<SiteCodeInfo[]>('/switches/site-codes'),

  getSiteCodesDetailed: () =>
    api.get<{ site_codes: Array<{ code: string; count: number; switches: Array<{ id: number; hostname: string; ip_address: string }> }>; total_sites: number }>('/switches/site-codes'),

  autoAssignSiteCodes: () =>
    api.post<{ updated: number; message: string }>('/switches/auto-assign-site-codes'),

  autoCreateGroups: () =>
    api.post<{ groups_created: number; switches_assigned: number; message: string }>('/switches/auto-create-groups'),

  get: (id: number) =>
    api.get<Switch>(`/switches/${id}`),

  create: (data: SwitchCreate) =>
    api.post<Switch>('/switches', data),

  update: (id: number, data: Partial<SwitchCreate>) =>
    api.put<Switch>(`/switches/${id}`, data),

  delete: (id: number) =>
    api.delete(`/switches/${id}`),

  deleteSwitchesBulk: (ids: number[]) =>
    api.post<DeleteResult>('/switches/bulk-delete', { switch_ids: ids }),

  deleteAllSwitches: () =>
    api.post<DeleteResult>('/switches/delete-all', {}, {
      headers: { 'X-Confirm-Delete-All': 'true' }
    }),

  getPorts: (id: number) =>
    api.get<{ items: Port[]; total: number }>(`/switches/${id}/ports`),

  getMacs: (id: number) =>
    api.get<{ switch_id: number; switch_hostname: string; mac_count: number; macs: SwitchMac[] }>(`/topology/switch/${id}/macs`),
};

// Groups API
export const groupsApi = {
  list: (params?: { search?: string }) =>
    api.get<{ items: SwitchGroup[]; total: number }>('/groups', { params }),

  get: (id: number) =>
    api.get<SwitchGroup>(`/groups/${id}`),

  create: (data: SwitchGroupCreate) =>
    api.post<SwitchGroup>('/groups', data),

  update: (id: number, data: Partial<SwitchGroupCreate>) =>
    api.put<SwitchGroup>(`/groups/${id}`, data),

  delete: (id: number) =>
    api.delete(`/groups/${id}`),
};

// Dashboard API
export const dashboardApi = {
  getStats: () =>
    api.get<DashboardStats>('/dashboard/stats'),

  getTopSwitches: (limit = 10) =>
    api.get<{ id: number; hostname: string; mac_count: number }[]>('/dashboard/top-switches', { params: { limit } }),

  getTrends: (days = 7) =>
    api.get<{ date: string; count: number }[]>('/dashboard/trends', { params: { days } }),

  getStatsBySite: () =>
    api.get<SiteStatsBySite>('/dashboard/stats-by-site'),

  getMacBreakdown: () =>
    api.get<{ total: number; real: number; random: number; multicast: number }>('/dashboard/mac-breakdown'),
};

// Alerts API
export const alertsApi = {
  list: (params?: { alert_type?: string; is_read?: boolean; date_from?: string; date_to?: string }) =>
    api.get<{ items: Alert[]; total: number; unread_count: number }>('/alerts', { params }),

  getUnread: () =>
    api.get<{ items: Alert[]; total: number; unread_count: number }>('/alerts/unread'),

  markRead: (id: number) =>
    api.put(`/alerts/${id}/read`),

  markAllRead: () =>
    api.put('/alerts/read-all'),
};

// MAC Addresses API
export const macsApi = {
  search: (params?: { q?: string; switch_id?: number; vlan_id?: number; is_active?: boolean; use_regex?: boolean; skip?: number; limit?: number }) =>
    api.get<{ items: MacSearchResult[]; total: number }>('/macs', { params }),

  get: (id: number) =>
    api.get<MacDetail>(`/macs/${id}`),

  // Endpoint Tracing - find actual physical connection point
  traceEndpoint: (macAddress: string, site?: string) =>
    api.get<EndpointTraceResponse>(`/macs/trace/${encodeURIComponent(macAddress)}`, { params: site ? { site } : undefined }),

  // Get all endpoints for multi-homed devices
  getAllEndpoints: (macAddress: string) =>
    api.get<AllEndpointsResponse>(`/macs/endpoints/${encodeURIComponent(macAddress)}`),

  exportCsv: (params?: { q?: string; switch_id?: number; vlan_id?: number; is_active?: boolean }) => {
    // Build query string for export URL
    const queryParams = new URLSearchParams();
    if (params?.q) queryParams.append('q', params.q);
    if (params?.switch_id) queryParams.append('switch_id', params.switch_id.toString());
    if (params?.vlan_id) queryParams.append('vlan_id', params.vlan_id.toString());
    if (params?.is_active !== undefined) queryParams.append('is_active', params.is_active.toString());

    const queryString = queryParams.toString();
    const exportUrl = `/api/macs/export${queryString ? `?${queryString}` : ''}`;

    // Trigger file download by opening URL in new window/tab
    window.open(exportUrl, '_blank');
  },

  exportHistoryCsv: (macId: number) => {
    // Trigger history CSV download by opening URL in new window/tab
    const exportUrl = `/api/macs/${macId}/history/export`;
    window.open(exportUrl, '_blank');
  },
};

// Discovery API
export interface DiscoveryStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  message: string;
  started_at?: string;
  completed_at?: string;
  switches_processed: number;
  macs_found: number;
}

export interface DiscoveryLog {
  id: number;
  switch_hostname?: string;
  discovery_type: string;
  status: string;
  mac_count: number;
  error_message?: string;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
}

export interface SeedDiscoveryRequest {
  seed_ip?: string;
  seed_switch_id?: number;
  snmp_community?: string;
  device_type?: string;
  max_depth?: number;
  group_id?: number;
}

export interface SeedDiscoveryResult {
  status: string;
  message: string;
  seed_switch?: string;
  switches_discovered: number;
  switches_added: number;
  switches_already_exist: number;
  discovered_switches: Array<{
    hostname?: string;
    ip?: string;
    local_port?: string;
    remote_port?: string;
    added: boolean;
    exists?: boolean;
    new_switch_id?: number;
  }>;
  errors: string[];
}

export const discoveryApi = {
  start: () =>
    api.post<{ message: string; status: string }>('/discovery/start'),

  getStatus: () =>
    api.get<DiscoveryStatus>('/discovery/status'),

  getLogs: (limit = 50) =>
    api.get<DiscoveryLog[]>('/discovery/logs', { params: { limit } }),

  seedDiscovery: (request: SeedDiscoveryRequest) =>
    api.post<SeedDiscoveryResult>('/discovery/seed', request),
};

// Settings API
export interface TelegramTestResponse {
  success: boolean;
  message: string;
  details?: string;
}

export interface Settings {
  discovery_interval: number;
  history_retention_days: number;
  telegram_bot_token: string;
  telegram_chat_id: string;
  alert_new_mac: boolean;
  alert_mac_move: boolean;
  alert_mac_disappear: boolean;
  alert_disappear_hours: number;
  alert_port_threshold: number;
}

export const settingsApi = {
  get: () =>
    api.get<Settings>('/settings'),

  update: (settings: Settings) =>
    api.put<Settings>('/settings', settings),

  testTelegram: (bot_token: string, chat_id: string) =>
    api.post<TelegramTestResponse>('/settings/telegram/test', { bot_token, chat_id }),
};

// Backup API
export interface BackupInfo {
  filename: string;
  path: string;
  size: number;
  size_formatted: string;
  created_at: string;
}

export interface BackupResult {
  success: boolean;
  filename?: string;
  path?: string;
  size?: number;
  size_formatted?: string;
  timestamp?: string;
  error?: string;
  message?: string;
}

export interface BackupVerification {
  success: boolean;
  integrity?: string;
  tables?: Record<string, number>;
  total_records?: number;
  error?: string;
}

export interface ScheduleConfig {
  enabled: boolean;
  interval_hours: number;
  time: string;
}

export interface SchedulerStatus {
  is_running: boolean;
  config: ScheduleConfig;
  next_scheduled_backup?: string;
  last_backup_result?: BackupResult;
}

export const backupApi = {
  list: () =>
    api.get<BackupInfo[]>('/backup/'),

  create: (label?: string) =>
    api.post<BackupResult>('/backup/create', null, { params: { label } }),

  manual: () =>
    api.post<BackupResult>('/backup/manual'),

  delete: (filename: string) =>
    api.delete(`/backup/${filename}`),

  verify: (filename: string) =>
    api.get<BackupVerification>(`/backup/${filename}/verify`),

  restore: (filename: string) =>
    api.post(`/backup/${filename}/restore`),

  getSchedulerStatus: () =>
    api.get<SchedulerStatus>('/backup/scheduler/status'),

  configureScheduler: (config: ScheduleConfig) =>
    api.post('/backup/scheduler/configure', config),

  startScheduler: () =>
    api.post('/backup/scheduler/start'),

  stopScheduler: () =>
    api.post('/backup/scheduler/stop'),
};

// NeDi Integration Types
export interface NeDiConnectionStatus {
  connected: boolean;
  host: string;
  device_count: number;
  node_count: number;
  tables: string[];
  error?: string;
}

export interface NeDiImportStats {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
}

export interface NeDiImportResponse {
  success: boolean;
  devices: NeDiImportStats;
  nodes: NeDiImportStats;
  links: NeDiImportStats;
  error?: string;
}

export interface NeDiSchedulerStatus {
  enabled: boolean;
  interval_minutes: number;
  node_limit: number;
  is_running: boolean;
  last_run?: string;
  next_run?: string;
  last_result?: {
    success: boolean;
    devices?: NeDiImportStats;
    nodes?: NeDiImportStats;
    links?: NeDiImportStats;
    error?: string;
    timestamp?: string;
  };
}

export interface NeDiSchedulerConfig {
  enabled?: boolean;
  interval_minutes?: number;
  node_limit?: number;
}

export const nediApi = {
  getStatus: () =>
    api.get<NeDiConnectionStatus>('/nedi/status'),

  getTables: () =>
    api.get<{ tables: string[]; count: number }>('/nedi/tables'),

  getDevices: () =>
    api.get<{ devices: any[]; count: number }>('/nedi/devices'),

  getNodes: (limit: number = 1000) =>
    api.get<{ nodes: any[]; count: number; total: number }>('/nedi/nodes', { params: { limit } }),

  getLinks: () =>
    api.get<{ links: any[]; count: number }>('/nedi/links'),

  importAll: (nodeLimit: number = 100000) =>
    api.post<NeDiImportResponse>('/nedi/import', { node_limit: nodeLimit }),

  importDevicesOnly: () =>
    api.post<{ success: boolean; stats: NeDiImportStats }>('/nedi/import/devices'),

  importNodesOnly: (limit: number = 100000) =>
    api.post<{ success: boolean; stats: NeDiImportStats }>('/nedi/import/nodes', null, { params: { limit } }),

  importLinksOnly: () =>
    api.post<{ success: boolean; stats: NeDiImportStats }>('/nedi/import/links'),

  // NeDi Sync Scheduler
  getSchedulerStatus: () =>
    api.get<NeDiSchedulerStatus>('/nedi/scheduler/status'),

  configureScheduler: (config: NeDiSchedulerConfig) =>
    api.post<{ success: boolean; message: string; status: NeDiSchedulerStatus }>('/nedi/scheduler/configure', config),

  runSyncNow: () =>
    api.post<{ success: boolean; message: string; result: any }>('/nedi/scheduler/run-now'),

  enableScheduler: (intervalMinutes: number = 15) =>
    api.post<{ success: boolean; message: string; status: NeDiSchedulerStatus }>(`/nedi/scheduler/enable?interval_minutes=${intervalMinutes}`),

  disableScheduler: () =>
    api.post<{ success: boolean; message: string; status: NeDiSchedulerStatus }>('/nedi/scheduler/disable'),
};

export default api;
