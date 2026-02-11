import { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { Network, Search, RefreshCw, Server, Building2, ChevronRight, ArrowLeft } from 'lucide-react'

interface VlanSummary {
  vlan_id: number
  mac_count: number
  switch_count: number
  port_count: number
  sites: string[]
  top_vendors: { vendor: string; count: number }[]
}

interface VlanDetail {
  vlan_id: number
  total_macs: number
  total_switches: number
  total_ports: number
  sites: string[]
  switches: {
    id: number
    hostname: string
    ip_address: string
    site_code: string | null
    mac_count: number
  }[]
  vendors: { name: string; count: number }[]
  device_types: { type: string; count: number }[]
}

interface TechnologyStats {
  total_vlans: number
  total_switchports: number
  uplink_ports: number
  access_ports: number
  ports_with_macs: number
  top_vlans: { vlan_id: number; mac_count: number }[]
}

export default function VlanTable() {
  const { vlanId } = useParams<{ vlanId?: string }>()
  const navigate = useNavigate()

  const [vlans, setVlans] = useState<VlanSummary[]>([])
  const [vlanDetail, setVlanDetail] = useState<VlanDetail | null>(null)
  const [stats, setStats] = useState<TechnologyStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [siteFilter, setSiteFilter] = useState('')
  const [minMacs, setMinMacs] = useState<number | ''>('')

  const fetchStats = async () => {
    try {
      const response = await fetch('/api/technology/stats')
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Error fetching stats:', error)
    }
  }

  const fetchVlans = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (siteFilter) params.append('site_code', siteFilter)
      if (minMacs) params.append('min_macs', String(minMacs))

      const response = await fetch(`/api/technology/vlans?${params}`)
      const data = await response.json()
      setVlans(data.items)
    } catch (error) {
      console.error('Error fetching VLANs:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchVlanDetail = async (id: string) => {
    setLoading(true)
    try {
      const response = await fetch(`/api/technology/vlans/${id}`)
      const data = await response.json()
      setVlanDetail(data)
    } catch (error) {
      console.error('Error fetching VLAN detail:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  useEffect(() => {
    if (vlanId) {
      fetchVlanDetail(vlanId)
    } else {
      fetchVlans()
      setVlanDetail(null)
    }
  }, [vlanId, siteFilter, minMacs])

  // Get unique sites from VLANs
  const allSites = [...new Set(vlans.flatMap(v => v.sites))].sort()

  // Filter VLANs by search
  const filteredVlans = vlans.filter(v =>
    search === '' || String(v.vlan_id).includes(search)
  )

  // Detail view
  if (vlanId && vlanDetail) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/vlans')}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <ArrowLeft className="h-5 w-5 text-gray-500" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              VLAN {vlanDetail.vlan_id}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Dettaglio VLAN - {vlanDetail.total_macs.toLocaleString()} MAC address
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-blue-600">{vlanDetail.total_macs.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">MAC Address</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-green-600">{vlanDetail.total_switches}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Switch</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-purple-600">{vlanDetail.total_ports}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Porte</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-orange-600">{vlanDetail.sites.length}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Siti</div>
          </div>
        </div>

        {/* Sites */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <h3 className="font-medium text-gray-900 dark:text-white mb-3">Siti con VLAN {vlanDetail.vlan_id}</h3>
          <div className="flex flex-wrap gap-2">
            {vlanDetail.sites.map(site => (
              <span key={site} className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
                <Building2 className="h-3 w-3 mr-1" />
                Sito {site}
              </span>
            ))}
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Switches */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
            <div className="p-4 border-b dark:border-gray-700">
              <h3 className="font-medium text-gray-900 dark:text-white">Switch con più MAC</h3>
            </div>
            <div className="divide-y dark:divide-gray-700">
              {vlanDetail.switches.map(sw => (
                <Link
                  key={sw.id}
                  to={`/switches/${sw.id}`}
                  className="flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">{sw.hostname}</div>
                    <div className="text-sm text-gray-500">{sw.ip_address} • Sito {sw.site_code || '-'}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-blue-600">{sw.mac_count}</div>
                    <div className="text-xs text-gray-400">MAC</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Vendors & Device Types */}
          <div className="space-y-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
              <div className="p-4 border-b dark:border-gray-700">
                <h3 className="font-medium text-gray-900 dark:text-white">Vendor</h3>
              </div>
              <div className="p-4 space-y-2">
                {vlanDetail.vendors.map((v, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm text-gray-700 dark:text-gray-300 truncate">{v.name}</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">{v.count}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
              <div className="p-4 border-b dark:border-gray-700">
                <h3 className="font-medium text-gray-900 dark:text-white">Tipi Dispositivo</h3>
              </div>
              <div className="p-4 space-y-2">
                {vlanDetail.device_types.map((d, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm text-gray-700 dark:text-gray-300 capitalize">{d.type}</span>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">{d.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // List view
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">VLAN Table</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Technology Table - Distribuzione MAC per VLAN
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-blue-600">{stats.total_vlans}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">VLAN Totali</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-green-600">{stats.total_switchports.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Switchport</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-purple-600">{stats.ports_with_macs.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Porte con MAC</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-orange-600">{stats.uplink_ports.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Uplink</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-cyan-600">{stats.access_ports.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Access Port</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Cerca VLAN ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
          />
        </div>
        <select
          value={siteFilter}
          onChange={(e) => setSiteFilter(e.target.value)}
          className="px-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
        >
          <option value="">Tutti i siti</option>
          {allSites.map(site => (
            <option key={site} value={site}>Sito {site}</option>
          ))}
        </select>
        <input
          type="number"
          placeholder="Min MAC..."
          value={minMacs}
          onChange={(e) => setMinMacs(e.target.value ? Number(e.target.value) : '')}
          className="w-32 px-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
        />
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">VLAN ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">MAC Count</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Switch</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Porte</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Siti</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Top Vendor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                    <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                    Caricamento...
                  </td>
                </tr>
              ) : filteredVlans.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                    Nessuna VLAN trovata
                  </td>
                </tr>
              ) : filteredVlans.map(vlan => (
                <tr key={vlan.vlan_id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3">
                    <span className="font-mono font-bold text-blue-600 dark:text-blue-400">
                      {vlan.vlan_id}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-bold text-gray-900 dark:text-white">
                      {vlan.mac_count.toLocaleString()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {vlan.switch_count}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {vlan.port_count}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {vlan.sites.slice(0, 5).map(site => (
                        <span key={site} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                          {site}
                        </span>
                      ))}
                      {vlan.sites.length > 5 && (
                        <span className="text-xs text-gray-400">+{vlan.sites.length - 5}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300 truncate max-w-[200px]">
                    {vlan.top_vendors[0]?.vendor || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/vlans/${vlan.vlan_id}`}
                      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 inline-flex"
                    >
                      <ChevronRight className="h-4 w-4 text-gray-400" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
