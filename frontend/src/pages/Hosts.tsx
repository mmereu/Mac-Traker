import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Search, Download, RefreshCw, Server, Wifi, Monitor, Smartphone, HelpCircle, Star, Building2, Filter, Activity, Radar } from 'lucide-react'

interface Host {
  id: number
  mac_address: string
  ip_address: string | null
  hostname: string | null
  vendor_oui: string | null
  vendor_name: string | null
  device_type: string | null
  device_model: string | null
  os_type: string | null
  edge_switch_id: number | null
  edge_switch_hostname: string | null
  edge_switch_ip: string | null
  edge_port_id: number | null
  edge_port_name: string | null
  vlan_id: number | null
  vrf: string | null
  site_code: string | null
  is_infrastructure: boolean
  is_virtual: boolean
  is_critical: boolean
  discovery_attempted: boolean
  discovery_result: string | null
  first_seen: string
  last_seen: string
  is_active: boolean
  notes: string | null
}

interface HostStats {
  total_hosts: number
  active_hosts: number
  infrastructure_devices: number
  virtual_devices: number
  critical_devices: number
  by_device_type: Record<string, number>
  by_vendor: Record<string, number>
  by_site: Record<string, number>
}

// Device type icon component
const DeviceTypeIcon = ({ deviceType, isInfrastructure, isVirtual }: { deviceType?: string | null, isInfrastructure?: boolean, isVirtual?: boolean }) => {
  if (isInfrastructure) return <Server className="h-4 w-4 text-blue-500" />
  if (isVirtual) return <Monitor className="h-4 w-4 text-purple-500" />
  if (deviceType === 'handheld') return <Smartphone className="h-4 w-4 text-orange-500" />
  if (deviceType === 'network') return <Wifi className="h-4 w-4 text-cyan-500" />
  if (deviceType === 'workstation') return <Monitor className="h-4 w-4 text-green-500" />
  return <HelpCircle className="h-4 w-4 text-gray-400" />
}

export default function Hosts() {
  const [hosts, setHosts] = useState<Host[]>([])
  const [stats, setStats] = useState<HostStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [search, setSearch] = useState('')
  const [deviceTypeFilter, setDeviceTypeFilter] = useState('')
  const [siteFilter, setSiteFilter] = useState('')
  const [infraFilter, setInfraFilter] = useState<boolean | null>(null)
  const [virtualFilter, setVirtualFilter] = useState<boolean | null>(null)
  const [criticalFilter, setCriticalFilter] = useState<boolean | null>(null)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const limit = 100

  // Ping sweep state
  const [showPingSweep, setShowPingSweep] = useState(false)
  const [pingSweepSubnet, setPingSweepSubnet] = useState('')
  const [pingSweeping, setPingSweeping] = useState(false)
  const [pingSweepResult, setPingSweepResult] = useState<{
    subnet: string
    total_scanned: number
    hosts_up: number
    hosts_down: number
    new_hosts: number
    updated_hosts: number
  } | null>(null)
  const [discoveryStats, setDiscoveryStats] = useState<{
    total_hosts: number
    discovery_attempted: number
    reachable: number
    unreachable: number
    not_tested: number
  } | null>(null)

  const fetchHosts = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.append('search', search)
      if (deviceTypeFilter) params.append('device_type', deviceTypeFilter)
      if (siteFilter) params.append('site_code', siteFilter)
      if (infraFilter !== null) params.append('is_infrastructure', String(infraFilter))
      if (virtualFilter !== null) params.append('is_virtual', String(virtualFilter))
      if (criticalFilter !== null) params.append('is_critical', String(criticalFilter))
      params.append('skip', String(page * limit))
      params.append('limit', String(limit))

      const response = await fetch(`/api/hosts?${params}`)
      const data = await response.json()
      setHosts(data.items)
      setTotal(data.total)
    } catch (error) {
      console.error('Error fetching hosts:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const response = await fetch('/api/hosts/stats')
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Error fetching stats:', error)
    }
  }

  const syncHosts = async () => {
    setSyncing(true)
    try {
      const response = await fetch('/api/hosts/sync')
      const data = await response.json()
      alert(`Sincronizzazione completata: ${data.message}`)
      fetchHosts()
      fetchStats()
      fetchDiscoveryStats()
    } catch (error) {
      console.error('Error syncing hosts:', error)
      alert('Errore durante la sincronizzazione')
    } finally {
      setSyncing(false)
    }
  }

  const fetchDiscoveryStats = async () => {
    try {
      const response = await fetch('/api/hosts/discovery/status')
      const data = await response.json()
      setDiscoveryStats(data)
    } catch (error) {
      console.error('Error fetching discovery stats:', error)
    }
  }

  const runPingSweep = async () => {
    if (!pingSweepSubnet.trim()) {
      alert('Inserisci una subnet (es. 10.1.1.0/24)')
      return
    }
    setPingSweeping(true)
    setPingSweepResult(null)
    try {
      const response = await fetch('/api/hosts/discovery/ping-sweep', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subnet: pingSweepSubnet.trim(),
          timeout: 1,
          concurrent: 50
        })
      })
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Errore ping sweep')
      }
      const data = await response.json()
      setPingSweepResult(data)
      fetchHosts()
      fetchStats()
      fetchDiscoveryStats()
    } catch (error: any) {
      console.error('Error running ping sweep:', error)
      alert(`Errore: ${error.message}`)
    } finally {
      setPingSweeping(false)
    }
  }

  const exportCSV = () => {
    const csvContent = [
      ['MAC', 'IP', 'Hostname', 'Vendor', 'Tipo', 'Switch', 'Porta', 'VLAN', 'Sito', 'Infrastruttura', 'Virtuale', 'Critico', 'Ultimo Avvistamento'].join(','),
      ...hosts.map(h => [
        h.mac_address,
        h.ip_address || '',
        h.hostname || '',
        h.vendor_name || '',
        h.device_type || '',
        h.edge_switch_hostname || '',
        h.edge_port_name || '',
        h.vlan_id || '',
        h.site_code || '',
        h.is_infrastructure ? 'Si' : 'No',
        h.is_virtual ? 'Si' : 'No',
        h.is_critical ? 'Si' : 'No',
        new Date(h.last_seen).toLocaleString('it-IT')
      ].join(','))
    ].join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `hosts-export-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
  }

  useEffect(() => {
    fetchHosts()
    fetchStats()
    fetchDiscoveryStats()
  }, [page, search, deviceTypeFilter, siteFilter, infraFilter, virtualFilter, criticalFilter])

  const totalPages = Math.ceil(total / limit)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Host Table</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Gestione endpoint di rete (IP Fabric-like)
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={syncHosts}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Sincronizzazione...' : 'Sync da MAC'}
          </button>
          <button
            onClick={() => setShowPingSweep(!showPingSweep)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg ${showPingSweep ? 'bg-green-600 text-white' : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'} hover:bg-green-700 hover:text-white`}
          >
            <Radar className="h-4 w-4" />
            Ping Sweep
          </button>
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            <Download className="h-4 w-4" />
            Esporta CSV
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-blue-600">{stats.total_hosts.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Hosts Totali</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-green-600">{stats.active_hosts.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Hosts Attivi</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-orange-600">{stats.infrastructure_devices.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Infrastruttura</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-purple-600">{stats.virtual_devices.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Virtuali (VMware)</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-red-600">{stats.critical_devices}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Critici</div>
          </div>
        </div>
      )}

      {/* Discovery Stats */}
      {discoveryStats && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Active Discovery Status
          </h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Testati:</span>
              <span className="font-medium">{discoveryStats.discovery_attempted.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              <span className="text-gray-500">Raggiungibili:</span>
              <span className="font-medium text-green-600">{discoveryStats.reachable.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-red-500"></span>
              <span className="text-gray-500">Non raggiungibili:</span>
              <span className="font-medium text-red-600">{discoveryStats.unreachable.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-gray-400"></span>
              <span className="text-gray-500">Non testati:</span>
              <span className="font-medium text-gray-600">{discoveryStats.not_tested.toLocaleString()}</span>
            </div>
          </div>
        </div>
      )}

      {/* Ping Sweep Panel */}
      {showPingSweep && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
          <h3 className="text-sm font-medium text-green-800 dark:text-green-300 mb-3 flex items-center gap-2">
            <Radar className="h-4 w-4" />
            Active Host Discovery - Ping Sweep
          </h3>
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                Subnet (CIDR)
              </label>
              <input
                type="text"
                value={pingSweepSubnet}
                onChange={(e) => setPingSweepSubnet(e.target.value)}
                placeholder="es. 10.1.1.0/24"
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              />
            </div>
            <button
              onClick={runPingSweep}
              disabled={pingSweeping}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              <Radar className={`h-4 w-4 ${pingSweeping ? 'animate-pulse' : ''}`} />
              {pingSweeping ? 'Scansione...' : 'Avvia Ping Sweep'}
            </button>
          </div>

          {/* Ping Sweep Result */}
          {pingSweepResult && (
            <div className="mt-4 p-3 bg-white dark:bg-gray-800 rounded-lg">
              <h4 className="text-sm font-medium mb-2">Risultato scansione: {pingSweepResult.subnet}</h4>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                <div>
                  <span className="text-gray-500">Scansionati:</span>
                  <span className="ml-1 font-medium">{pingSweepResult.total_scanned}</span>
                </div>
                <div>
                  <span className="text-green-600">Attivi:</span>
                  <span className="ml-1 font-medium text-green-600">{pingSweepResult.hosts_up}</span>
                </div>
                <div>
                  <span className="text-red-600">Non risponde:</span>
                  <span className="ml-1 font-medium text-red-600">{pingSweepResult.hosts_down}</span>
                </div>
                <div>
                  <span className="text-blue-600">Nuovi:</span>
                  <span className="ml-1 font-medium text-blue-600">{pingSweepResult.new_hosts}</span>
                </div>
                <div>
                  <span className="text-orange-600">Aggiornati:</span>
                  <span className="ml-1 font-medium text-orange-600">{pingSweepResult.updated_hosts}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          <Filter className="h-4 w-4" />
          Filtri
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Cerca MAC, IP, hostname..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0) }}
              className="w-full pl-10 pr-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            />
          </div>

          {/* Device Type */}
          <select
            value={deviceTypeFilter}
            onChange={(e) => { setDeviceTypeFilter(e.target.value); setPage(0) }}
            className="px-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
          >
            <option value="">Tutti i tipi</option>
            {stats && Object.keys(stats.by_device_type).map(type => (
              <option key={type} value={type}>{type} ({stats.by_device_type[type]})</option>
            ))}
          </select>

          {/* Site */}
          <select
            value={siteFilter}
            onChange={(e) => { setSiteFilter(e.target.value); setPage(0) }}
            className="px-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
          >
            <option value="">Tutti i siti</option>
            {stats && Object.entries(stats.by_site)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([site, count]) => (
              <option key={site} value={site}>Sito {site} ({count})</option>
            ))}
          </select>

          {/* Quick Filters */}
          <div className="flex gap-2">
            <button
              onClick={() => { setInfraFilter(infraFilter === true ? null : true); setPage(0) }}
              className={`px-3 py-2 rounded-lg text-sm ${infraFilter === true ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
            >
              <Server className="h-4 w-4 inline mr-1" />
              Infra
            </button>
            <button
              onClick={() => { setVirtualFilter(virtualFilter === true ? null : true); setPage(0) }}
              className={`px-3 py-2 rounded-lg text-sm ${virtualFilter === true ? 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
            >
              <Monitor className="h-4 w-4 inline mr-1" />
              Virtual
            </button>
            <button
              onClick={() => { setCriticalFilter(criticalFilter === true ? null : true); setPage(0) }}
              className={`px-3 py-2 rounded-lg text-sm ${criticalFilter === true ? 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
            >
              <Star className="h-4 w-4 inline mr-1" />
              Critici
            </button>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Tipo</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">MAC Address</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">IP / Hostname</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Vendor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Edge Switch</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Porta</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">VLAN</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Sito</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Ultimo Avvist.</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                    <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                    Caricamento...
                  </td>
                </tr>
              ) : hosts.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                    Nessun host trovato
                  </td>
                </tr>
              ) : hosts.map((host) => (
                <tr key={host.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <DeviceTypeIcon
                      deviceType={host.device_type}
                      isInfrastructure={host.is_infrastructure}
                      isVirtual={host.is_virtual}
                    />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <Link
                      to={`/mac/${host.mac_address}`}
                      className="font-mono text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      {host.mac_address}
                    </Link>
                    {host.is_critical && (
                      <Star className="h-3 w-3 text-yellow-500 inline ml-1" />
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-sm text-gray-900 dark:text-white">{host.ip_address || '-'}</div>
                    {host.hostname && (
                      <div className="text-xs text-gray-500 dark:text-gray-400">{host.hostname}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-sm text-gray-900 dark:text-white truncate max-w-[200px]" title={host.vendor_name || ''}>
                      {host.vendor_name || '-'}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {host.edge_switch_id ? (
                      <Link
                        to={`/switches/${host.edge_switch_id}`}
                        className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        {host.edge_switch_hostname || host.edge_switch_ip}
                      </Link>
                    ) : (
                      <span className="text-sm text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-sm text-gray-900 dark:text-white font-mono">
                      {host.edge_port_name || '-'}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-sm text-gray-900 dark:text-white">
                      {host.vlan_id || '-'}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {host.site_code ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                        <Building2 className="h-3 w-3 mr-1" />
                        {host.site_code}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {new Date(host.last_seen).toLocaleString('it-IT', {
                      day: '2-digit',
                      month: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-t dark:border-gray-700 flex items-center justify-between">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Mostrando {page * limit + 1} - {Math.min((page + 1) * limit, total)} di {total.toLocaleString()} hosts
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-3 py-1 border rounded disabled:opacity-50 dark:border-gray-600 dark:text-gray-300"
              >
                Precedente
              </button>
              <span className="px-3 py-1 text-gray-700 dark:text-gray-300">
                Pagina {page + 1} di {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 border rounded disabled:opacity-50 dark:border-gray-600 dark:text-gray-300"
              >
                Successiva
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
