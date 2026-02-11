import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Network, Search, RefreshCw, Server, Download, Filter, ArrowUpDown } from 'lucide-react'

interface ArpEntry {
  id: number
  mac_address: string
  ip_address: string | null
  hostname: string | null
  vendor_name: string | null
  device_type: string | null
  edge_switch_id: number | null
  edge_switch_hostname?: string
  edge_port_name?: string
  vlan_id: number | null
  first_seen: string
  last_seen: string
}

interface ArpStats {
  total_entries: number
  entries_with_ip: number
  unique_vlans: number
  unique_switches: number
  top_vendors: { name: string; count: number }[]
}

export default function ArpTable() {
  const [entries, setEntries] = useState<ArpEntry[]>([])
  const [stats, setStats] = useState<ArpStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [vlanFilter, setVlanFilter] = useState('')
  const [vendorFilter, setVendorFilter] = useState('')
  const [sortBy, setSortBy] = useState<'mac' | 'ip' | 'last_seen'>('last_seen')
  const [sortDesc, setSortDesc] = useState(true)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const pageSize = 100

  const fetchStats = async () => {
    try {
      const response = await fetch('/api/hosts/stats')
      if (response.ok) {
        const data = await response.json()
        // Convert by_vendor object to sorted array
        const vendorArray = Object.entries(data.by_vendor || {})
          .map(([name, count]) => ({ name, count: count as number }))
          .filter(v => v.name !== '?' && v.name !== 'unknown')
          .sort((a, b) => b.count - a.count)
          .slice(0, 5)

        const uniqueSites = Object.keys(data.by_site || {}).length

        setStats({
          total_entries: data.total_hosts || 0,
          entries_with_ip: data.active_hosts || 0,
          unique_vlans: Object.keys(data.by_device_type || {}).length,
          unique_switches: uniqueSites,
          top_vendors: vendorArray
        })
      }
    } catch (error) {
      console.error('Error fetching stats:', error)
    }
  }

  const fetchEntries = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('skip', String(page * pageSize))
      params.append('limit', String(pageSize))
      if (search) params.append('search', search)
      if (vlanFilter) params.append('vlan_id', vlanFilter)
      if (vendorFilter) params.append('vendor', vendorFilter)

      const response = await fetch(`/api/hosts?${params}`)
      if (response.ok) {
        const data = await response.json()
        setEntries(data.items)
        setTotal(data.total)
      }
    } catch (error) {
      console.error('Error fetching ARP entries:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  useEffect(() => {
    fetchEntries()
  }, [page, search, vlanFilter, vendorFilter])

  // Sort entries
  const sortedEntries = [...entries].sort((a, b) => {
    let cmp = 0
    if (sortBy === 'mac') {
      cmp = a.mac_address.localeCompare(b.mac_address)
    } else if (sortBy === 'ip') {
      const ipA = a.ip_address || ''
      const ipB = b.ip_address || ''
      cmp = ipA.localeCompare(ipB)
    } else if (sortBy === 'last_seen') {
      cmp = (a.last_seen || '').localeCompare(b.last_seen || '')
    }
    return sortDesc ? -cmp : cmp
  })

  const handleSort = (field: 'mac' | 'ip' | 'last_seen') => {
    if (sortBy === field) {
      setSortDesc(!sortDesc)
    } else {
      setSortBy(field)
      setSortDesc(true)
    }
  }

  const exportCSV = () => {
    const headers = ['MAC Address', 'IP Address', 'Hostname', 'Vendor', 'Device Type', 'VLAN', 'Switch', 'Port', 'Last Seen']
    const rows = entries.map(e => [
      e.mac_address,
      e.ip_address || '',
      e.hostname || '',
      e.vendor_name || '',
      e.device_type || '',
      e.vlan_id || '',
      e.edge_switch_hostname || '',
      e.edge_port_name || '',
      e.last_seen || ''
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `arp-table-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">ARP Table</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Technology Table - MAC to IP Address Mappings
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchEntries}
            className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            <Download className="h-4 w-4" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-blue-600">{stats.total_entries.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">ARP Entries</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-green-600">{stats.entries_with_ip.toLocaleString()}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Con IP</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-purple-600">{stats.unique_vlans}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">VLAN</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-2xl font-bold text-orange-600">{stats.unique_switches}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Switch</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
            <div className="text-lg font-medium text-cyan-600 truncate">
              {stats.top_vendors[0]?.name || '-'}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400">Top Vendor</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Cerca MAC, IP, hostname..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0) }}
            className="w-full pl-10 pr-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
          />
        </div>
        <input
          type="text"
          placeholder="VLAN ID"
          value={vlanFilter}
          onChange={(e) => { setVlanFilter(e.target.value); setPage(0) }}
          className="w-24 px-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
        />
        <input
          type="text"
          placeholder="Vendor..."
          value={vendorFilter}
          onChange={(e) => { setVendorFilter(e.target.value); setPage(0) }}
          className="w-40 px-4 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
        />
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                  onClick={() => handleSort('mac')}
                >
                  <div className="flex items-center gap-1">
                    MAC Address
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                  onClick={() => handleSort('ip')}
                >
                  <div className="flex items-center gap-1">
                    IP Address
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Hostname</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Vendor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">VLAN</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Switch</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Port</th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                  onClick={() => handleSort('last_seen')}
                >
                  <div className="flex items-center gap-1">
                    Last Seen
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                    Caricamento...
                  </td>
                </tr>
              ) : sortedEntries.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    Nessuna entry trovata
                  </td>
                </tr>
              ) : sortedEntries.map(entry => (
                <tr key={entry.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-4 py-3">
                    <Link
                      to={`/macs/search?q=${entry.mac_address}`}
                      className="font-mono text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      {entry.mac_address}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm text-gray-900 dark:text-white">
                      {entry.ip_address || '-'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300 truncate max-w-[150px]">
                    {entry.hostname || '-'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300 truncate max-w-[150px]">
                    {entry.vendor_name || '-'}
                  </td>
                  <td className="px-4 py-3">
                    {entry.vlan_id ? (
                      <Link
                        to={`/vlans/${entry.vlan_id}`}
                        className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 hover:bg-purple-200 dark:hover:bg-purple-800"
                      >
                        {entry.vlan_id}
                      </Link>
                    ) : '-'}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {entry.edge_switch_id ? (
                      <Link
                        to={`/switches/${entry.edge_switch_id}`}
                        className="text-blue-600 dark:text-blue-400 hover:underline truncate block max-w-[120px]"
                      >
                        {entry.edge_switch_hostname || `Switch #${entry.edge_switch_id}`}
                      </Link>
                    ) : '-'}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-600 dark:text-gray-300">
                    {entry.edge_port_name || '-'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                    {entry.last_seen ? new Date(entry.last_seen).toLocaleString('it-IT') : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t dark:border-gray-700">
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Showing {page * pageSize + 1} - {Math.min((page + 1) * pageSize, total)} of {total.toLocaleString()}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-3 py-1 rounded border dark:border-gray-600 disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Prev
              </button>
              <span className="px-3 py-1 text-gray-600 dark:text-gray-400">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 rounded border dark:border-gray-600 disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
