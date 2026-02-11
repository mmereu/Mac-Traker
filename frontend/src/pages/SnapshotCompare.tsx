import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Calendar, ArrowRight, Plus, Minus, Move, RefreshCw, Download, Camera, GitCompare } from 'lucide-react'
import api from '../api/client'

interface SnapshotInfo {
  id: number
  name: string | null
  completed_at: string
  total_macs: number
}

interface SnapshotCompareResult {
  snapshot1_id: number
  snapshot1_name: string
  snapshot1_date: string
  snapshot2_id: number
  snapshot2_name: string
  snapshot2_date: string
  added_macs: MacSnapshot[]
  removed_macs: MacSnapshot[]
  moved_macs: MovedMac[]
  stats: {
    snapshot1_total: number
    snapshot2_total: number
    added_count: number
    removed_count: number
    moved_count: number
    unchanged_count: number
  }
}

interface DateCompareResult {
  date1: string
  date2: string
  added: MacSnapshot[]
  removed: MacSnapshot[]
  moved: MovedMac[]
  stats: {
    total_at_date1: number
    total_at_date2: number
    added_count: number
    removed_count: number
    moved_count: number
    unchanged_count: number
  }
}

interface MacSnapshot {
  mac_address: string
  switch_hostname: string | null
  switch_ip: string | null
  port_name: string | null
  vlan_id: number | null
  vendor_name: string | null
  device_type: string | null
}

interface MovedMac {
  mac_address: string
  vendor_name: string | null
  device_type: string | null
  from_switch: string | null
  from_port: string | null
  to_switch: string | null
  to_port: string | null
  from_vlan: number | null
  to_vlan: number | null
}

export default function SnapshotCompare() {
  const { id1, id2 } = useParams<{ id1?: string; id2?: string }>()

  // Mode: 'snapshot' if URL params, 'date' for manual selection
  const [mode, setMode] = useState<'snapshot' | 'date'>(id1 && id2 ? 'snapshot' : 'date')

  // Snapshot mode state
  const [snapshots, setSnapshots] = useState<SnapshotInfo[]>([])
  const [selectedSnapshot1, setSelectedSnapshot1] = useState<string>(id1 || '')
  const [selectedSnapshot2, setSelectedSnapshot2] = useState<string>(id2 || '')

  // Date mode state
  const [date1, setDate1] = useState('')
  const [date2, setDate2] = useState('')

  // Common state
  const [loading, setLoading] = useState(false)
  const [snapshotResult, setSnapshotResult] = useState<SnapshotCompareResult | null>(null)
  const [dateResult, setDateResult] = useState<DateCompareResult | null>(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'added' | 'removed' | 'moved'>('added')

  // Fetch snapshots list
  useEffect(() => {
    const fetchSnapshots = async () => {
      try {
        const response = await api.get('/snapshots')
        setSnapshots(response.data.items)
      } catch (err) {
        console.error('Error fetching snapshots:', err)
      }
    }
    fetchSnapshots()
  }, [])

  // Auto-compare if URL params provided
  useEffect(() => {
    if (id1 && id2) {
      setSelectedSnapshot1(id1)
      setSelectedSnapshot2(id2)
      setMode('snapshot')
      handleSnapshotCompare(id1, id2)
    }
  }, [id1, id2])

  const handleSnapshotCompare = async (snap1?: string, snap2?: string) => {
    const s1 = snap1 || selectedSnapshot1
    const s2 = snap2 || selectedSnapshot2

    if (!s1 || !s2) {
      setError('Seleziona entrambi gli snapshot')
      return
    }

    setLoading(true)
    setError('')
    setSnapshotResult(null)
    setDateResult(null)

    try {
      const response = await api.get(`/snapshots/compare/${s1}/${s2}`)
      setSnapshotResult(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Errore durante il confronto')
    } finally {
      setLoading(false)
    }
  }

  const handleDateCompare = async () => {
    if (!date1 || !date2) {
      setError('Seleziona entrambe le date')
      return
    }

    setLoading(true)
    setError('')
    setSnapshotResult(null)
    setDateResult(null)

    try {
      const params = new URLSearchParams({
        date1: new Date(date1).toISOString(),
        date2: new Date(date2).toISOString()
      })
      const response = await api.get(`/macs/compare-snapshots?${params}`)
      setDateResult(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Errore durante il confronto')
    } finally {
      setLoading(false)
    }
  }

  const exportCSV = () => {
    const result = snapshotResult || dateResult
    if (!result) return

    const rows: string[] = []
    rows.push('Tipo;MAC Address;Vendor;Switch Da;Porta Da;Switch A;Porta A;VLAN')

    const added = snapshotResult?.added_macs || dateResult?.added || []
    const removed = snapshotResult?.removed_macs || dateResult?.removed || []
    const moved = snapshotResult?.moved_macs || dateResult?.moved || []

    added.forEach(m => {
      rows.push(`Aggiunto;${m.mac_address};${m.vendor_name || ''};-;-;${m.switch_hostname || ''};${m.port_name || ''};${m.vlan_id || ''}`)
    })
    removed.forEach(m => {
      rows.push(`Rimosso;${m.mac_address};${m.vendor_name || ''};${m.switch_hostname || ''};${m.port_name || ''};-;-;${m.vlan_id || ''}`)
    })
    moved.forEach(m => {
      rows.push(`Spostato;${m.mac_address};${m.vendor_name || ''};${m.from_switch || ''};${m.from_port || ''};${m.to_switch || ''};${m.to_port || ''};${m.to_vlan || ''}`)
    })

    const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    const filename = snapshotResult
      ? `snapshot_compare_${snapshotResult.snapshot1_id}_${snapshotResult.snapshot2_id}.csv`
      : `snapshot_compare_${date1}_${date2}.csv`
    link.download = filename
    link.click()
  }

  // Get unified data
  const getStats = () => {
    if (snapshotResult) {
      return {
        total1: snapshotResult.stats.snapshot1_total,
        total2: snapshotResult.stats.snapshot2_total,
        added: snapshotResult.stats.added_count,
        removed: snapshotResult.stats.removed_count,
        moved: snapshotResult.stats.moved_count,
        label1: snapshotResult.snapshot1_name || `Snapshot #${snapshotResult.snapshot1_id}`,
        label2: snapshotResult.snapshot2_name || `Snapshot #${snapshotResult.snapshot2_id}`
      }
    }
    if (dateResult) {
      return {
        total1: dateResult.stats.total_at_date1,
        total2: dateResult.stats.total_at_date2,
        added: dateResult.stats.added_count,
        removed: dateResult.stats.removed_count,
        moved: dateResult.stats.moved_count,
        label1: new Date(dateResult.date1).toLocaleDateString(),
        label2: new Date(dateResult.date2).toLocaleDateString()
      }
    }
    return null
  }

  const getMacs = () => {
    return {
      added: snapshotResult?.added_macs || dateResult?.added || [],
      removed: snapshotResult?.removed_macs || dateResult?.removed || [],
      moved: snapshotResult?.moved_macs || dateResult?.moved || []
    }
  }

  const stats = getStats()
  const macs = getMacs()
  const hasResult = snapshotResult || dateResult

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Confronto Snapshot MAC
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Confronta due snapshot o due date per vedere le differenze
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/snapshots"
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            <Camera className="h-4 w-4" />
            Gestisci Snapshot
          </Link>
          {hasResult && (
            <button
              onClick={exportCSV}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
            >
              <Download className="h-4 w-4" />
              Esporta CSV
            </button>
          )}
        </div>
      </div>

      {/* Mode Selector */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div className="flex gap-4 mb-6">
          <button
            onClick={() => setMode('snapshot')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              mode === 'snapshot'
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            <Camera className="h-4 w-4" />
            Per Snapshot
          </button>
          <button
            onClick={() => setMode('date')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              mode === 'date'
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            <Calendar className="h-4 w-4" />
            Per Data
          </button>
        </div>

        {mode === 'snapshot' ? (
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Snapshot 1 (Prima)
              </label>
              <select
                value={selectedSnapshot1}
                onChange={(e) => setSelectedSnapshot1(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              >
                <option value="">Seleziona snapshot...</option>
                {snapshots.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name || `Snapshot #${s.id}`} - {new Date(s.completed_at).toLocaleDateString()} ({s.total_macs.toLocaleString()} MAC)
                  </option>
                ))}
              </select>
            </div>

            <ArrowRight className="h-6 w-6 text-gray-400 mb-2" />

            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Snapshot 2 (Dopo)
              </label>
              <select
                value={selectedSnapshot2}
                onChange={(e) => setSelectedSnapshot2(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              >
                <option value="">Seleziona snapshot...</option>
                {snapshots.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name || `Snapshot #${s.id}`} - {new Date(s.completed_at).toLocaleDateString()} ({s.total_macs.toLocaleString()} MAC)
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={() => handleSnapshotCompare()}
              disabled={loading || !selectedSnapshot1 || !selectedSnapshot2}
              className="flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <GitCompare className="h-4 w-4" />}
              Confronta
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Data Iniziale
              </label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="datetime-local"
                  value={date1}
                  onChange={(e) => setDate1(e.target.value)}
                  className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <ArrowRight className="h-6 w-6 text-gray-400 mb-2" />

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Data Finale
              </label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="datetime-local"
                  value={date2}
                  onChange={(e) => setDate2(e.target.value)}
                  className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <button
              onClick={handleDateCompare}
              disabled={loading || !date1 || !date2}
              className="flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Confronta
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 p-3 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg">
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {stats && (
        <>
          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-500 dark:text-gray-400 truncate" title={stats.label1}>MAC in "{stats.label1}"</div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total1.toLocaleString()}</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
              <div className="text-sm text-gray-500 dark:text-gray-400 truncate" title={stats.label2}>MAC in "{stats.label2}"</div>
              <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total2.toLocaleString()}</div>
            </div>
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg shadow p-4">
              <div className="text-sm text-green-600 dark:text-green-400">Nuovi MAC</div>
              <div className="text-2xl font-bold text-green-700 dark:text-green-400">+{stats.added.toLocaleString()}</div>
            </div>
            <div className="bg-red-50 dark:bg-red-900/20 rounded-lg shadow p-4">
              <div className="text-sm text-red-600 dark:text-red-400">MAC Rimossi</div>
              <div className="text-2xl font-bold text-red-700 dark:text-red-400">-{stats.removed.toLocaleString()}</div>
            </div>
            <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg shadow p-4">
              <div className="text-sm text-orange-600 dark:text-orange-400">MAC Spostati</div>
              <div className="text-2xl font-bold text-orange-700 dark:text-orange-400">{stats.moved.toLocaleString()}</div>
            </div>
          </div>

          {/* Tabs */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
            <div className="border-b border-gray-200 dark:border-gray-700">
              <nav className="flex -mb-px">
                <button
                  onClick={() => setActiveTab('added')}
                  className={`px-6 py-3 text-sm font-medium border-b-2 ${
                    activeTab === 'added'
                      ? 'border-green-500 text-green-600 dark:text-green-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
                  }`}
                >
                  <Plus className="h-4 w-4 inline mr-2" />
                  Aggiunti ({macs.added.length.toLocaleString()})
                </button>
                <button
                  onClick={() => setActiveTab('removed')}
                  className={`px-6 py-3 text-sm font-medium border-b-2 ${
                    activeTab === 'removed'
                      ? 'border-red-500 text-red-600 dark:text-red-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
                  }`}
                >
                  <Minus className="h-4 w-4 inline mr-2" />
                  Rimossi ({macs.removed.length.toLocaleString()})
                </button>
                <button
                  onClick={() => setActiveTab('moved')}
                  className={`px-6 py-3 text-sm font-medium border-b-2 ${
                    activeTab === 'moved'
                      ? 'border-orange-500 text-orange-600 dark:text-orange-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
                  }`}
                >
                  <Move className="h-4 w-4 inline mr-2" />
                  Spostati ({macs.moved.length.toLocaleString()})
                </button>
              </nav>
            </div>

            <div className="p-4 overflow-x-auto max-h-[500px] overflow-y-auto">
              {activeTab === 'added' && (
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="sticky top-0 bg-white dark:bg-gray-800">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">MAC Address</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Vendor</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Switch</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Porta</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">VLAN</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {macs.added.slice(0, 500).map((mac, i) => (
                      <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                        <td className="px-4 py-3">
                          <Link to={`/mac/${mac.mac_address}`} className="font-mono text-sm text-blue-600 dark:text-blue-400 hover:underline">
                            {mac.mac_address}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.vendor_name || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.switch_hostname || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.port_name || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.vlan_id || '-'}</td>
                      </tr>
                    ))}
                    {macs.added.length === 0 && (
                      <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Nessun MAC aggiunto</td></tr>
                    )}
                    {macs.added.length > 500 && (
                      <tr><td colSpan={5} className="px-4 py-2 text-center text-gray-400 text-sm">... e altri {macs.added.length - 500} MAC (esporta CSV per lista completa)</td></tr>
                    )}
                  </tbody>
                </table>
              )}

              {activeTab === 'removed' && (
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="sticky top-0 bg-white dark:bg-gray-800">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">MAC Address</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Vendor</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Ultimo Switch</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Ultima Porta</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">VLAN</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {macs.removed.slice(0, 500).map((mac, i) => (
                      <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                        <td className="px-4 py-3">
                          <Link to={`/mac/${mac.mac_address}`} className="font-mono text-sm text-blue-600 dark:text-blue-400 hover:underline">
                            {mac.mac_address}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.vendor_name || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.switch_hostname || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.port_name || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.vlan_id || '-'}</td>
                      </tr>
                    ))}
                    {macs.removed.length === 0 && (
                      <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Nessun MAC rimosso</td></tr>
                    )}
                    {macs.removed.length > 500 && (
                      <tr><td colSpan={5} className="px-4 py-2 text-center text-gray-400 text-sm">... e altri {macs.removed.length - 500} MAC (esporta CSV per lista completa)</td></tr>
                    )}
                  </tbody>
                </table>
              )}

              {activeTab === 'moved' && (
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="sticky top-0 bg-white dark:bg-gray-800">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">MAC Address</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Vendor</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Da (Switch/Porta)</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">A (Switch/Porta)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {macs.moved.slice(0, 500).map((mac, i) => (
                      <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                        <td className="px-4 py-3">
                          <Link to={`/mac/${mac.mac_address}`} className="font-mono text-sm text-blue-600 dark:text-blue-400 hover:underline">
                            {mac.mac_address}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">{mac.vendor_name || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          <span className="font-medium">{mac.from_switch}</span> / {mac.from_port}
                          {mac.from_vlan && <span className="text-xs text-gray-400 ml-1">(VLAN {mac.from_vlan})</span>}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          <span className="font-medium">{mac.to_switch}</span> / {mac.to_port}
                          {mac.to_vlan && <span className="text-xs text-gray-400 ml-1">(VLAN {mac.to_vlan})</span>}
                        </td>
                      </tr>
                    ))}
                    {macs.moved.length === 0 && (
                      <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Nessun MAC spostato</td></tr>
                    )}
                    {macs.moved.length > 500 && (
                      <tr><td colSpan={4} className="px-4 py-2 text-center text-gray-400 text-sm">... e altri {macs.moved.length - 500} MAC (esporta CSV per lista completa)</td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {/* Empty state */}
      {!hasResult && !loading && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-12 text-center">
          <GitCompare className="h-16 w-16 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Confronta Snapshot MAC
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Seleziona due snapshot o due date per vedere quali MAC sono stati aggiunti, rimossi o spostati.
          </p>
          <Link
            to="/snapshots"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Camera className="h-4 w-4" />
            Vai a Snapshots
          </Link>
        </div>
      )}
    </div>
  )
}
