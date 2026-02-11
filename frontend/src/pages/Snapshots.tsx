import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Camera, Lock, Unlock, Trash2, RefreshCw, Plus, GitCompare, Star, Clock, Database, Settings, Play, Timer } from 'lucide-react'

interface SchedulerStatus {
  is_running: boolean
  config: {
    enabled: boolean
    interval_hours: number
  }
  next_scheduled_snapshot: string | null
  last_snapshot_result: {
    success: boolean
    timestamp: string
    snapshot_id?: number
    total_macs?: number
    error?: string
  } | null
}

interface Snapshot {
  id: number
  name: string | null
  description: string | null
  status: string
  total_switches: number
  total_ports: number
  total_macs: number
  total_hosts: number
  total_links: number
  switches_discovered: number
  switches_failed: number
  discovery_duration_ms: number | null
  started_at: string
  completed_at: string | null
  is_locked: boolean
  is_baseline: boolean
}

export default function Snapshots() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [selectedSnapshots, setSelectedSnapshots] = useState<number[]>([])
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null)
  const [showSchedulerModal, setShowSchedulerModal] = useState(false)
  const [schedulerEnabled, setSchedulerEnabled] = useState(false)
  const [intervalHours, setIntervalHours] = useState(6)
  const [savingScheduler, setSavingScheduler] = useState(false)
  const [runningManual, setRunningManual] = useState(false)

  const fetchSchedulerStatus = async () => {
    try {
      const response = await fetch('/api/snapshots/scheduler/status')
      if (response.ok) {
        const data = await response.json()
        setSchedulerStatus(data)
        setSchedulerEnabled(data.config.enabled)
        setIntervalHours(data.config.interval_hours)
      }
    } catch (error) {
      console.error('Error fetching scheduler status:', error)
    }
  }

  const saveSchedulerConfig = async () => {
    setSavingScheduler(true)
    try {
      const response = await fetch('/api/snapshots/scheduler/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: schedulerEnabled,
          interval_hours: intervalHours
        })
      })
      if (response.ok) {
        await fetchSchedulerStatus()
        setShowSchedulerModal(false)
      }
    } catch (error) {
      console.error('Error saving scheduler config:', error)
    } finally {
      setSavingScheduler(false)
    }
  }

  const runManualSnapshot = async () => {
    setRunningManual(true)
    try {
      const response = await fetch('/api/snapshots/scheduler/run-now', { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          alert(`Snapshot creato! ID: ${data.snapshot_id}, MAC: ${data.total_macs}`)
          fetchSnapshots()
        } else {
          alert(`Errore: ${data.error}`)
        }
        await fetchSchedulerStatus()
      }
    } catch (error) {
      console.error('Error running manual snapshot:', error)
    } finally {
      setRunningManual(false)
    }
  }

  const fetchSnapshots = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/snapshots')
      const data = await response.json()
      setSnapshots(data.items)
    } catch (error) {
      console.error('Error fetching snapshots:', error)
    } finally {
      setLoading(false)
    }
  }

  const createSnapshot = async () => {
    setCreating(true)
    try {
      const response = await fetch('/api/snapshots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName || undefined,
          description: newDescription || undefined
        })
      })
      const data = await response.json()
      if (response.ok) {
        alert(`Snapshot creato: ${data.total_macs.toLocaleString()} MAC catturati in ${(data.discovery_duration_ms / 1000).toFixed(1)}s`)
        setShowCreateModal(false)
        setNewName('')
        setNewDescription('')
        fetchSnapshots()
      } else {
        alert(`Errore: ${data.detail}`)
      }
    } catch (error) {
      console.error('Error creating snapshot:', error)
      alert('Errore durante la creazione dello snapshot')
    } finally {
      setCreating(false)
    }
  }

  const deleteSnapshot = async (id: number) => {
    if (!confirm('Sei sicuro di voler eliminare questo snapshot?')) return
    try {
      const response = await fetch(`/api/snapshots/${id}`, { method: 'DELETE' })
      if (response.ok) {
        fetchSnapshots()
      } else {
        const data = await response.json()
        alert(`Errore: ${data.detail}`)
      }
    } catch (error) {
      console.error('Error deleting snapshot:', error)
    }
  }

  const toggleLock = async (snapshot: Snapshot) => {
    try {
      await fetch(`/api/snapshots/${snapshot.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_locked: !snapshot.is_locked })
      })
      fetchSnapshots()
    } catch (error) {
      console.error('Error toggling lock:', error)
    }
  }

  const toggleBaseline = async (snapshot: Snapshot) => {
    try {
      await fetch(`/api/snapshots/${snapshot.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_baseline: !snapshot.is_baseline })
      })
      fetchSnapshots()
    } catch (error) {
      console.error('Error toggling baseline:', error)
    }
  }

  const toggleSelect = (id: number) => {
    setSelectedSnapshots(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id].slice(-2)
    )
  }

  useEffect(() => {
    fetchSnapshots()
    fetchSchedulerStatus()
  }, [])

  const formatDuration = (ms: number | null) => {
    if (!ms) return '-'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Network Snapshots</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Catture immutabili dello stato di rete (IP Fabric-like)
          </p>
        </div>
        <div className="flex gap-2">
          {selectedSnapshots.length === 2 && (
            <Link
              to={`/snapshots/compare/${selectedSnapshots[0]}/${selectedSnapshots[1]}`}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
            >
              <GitCompare className="h-4 w-4" />
              Confronta Selezionati
            </Link>
          )}
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Nuovo Snapshot
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Camera className="h-5 w-5 text-blue-500 mt-0.5" />
          <div>
            <h3 className="font-medium text-blue-900 dark:text-blue-100">Cos'è uno Snapshot?</h3>
            <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
              Uno snapshot cattura lo stato completo della rete in un momento specifico.
              Puoi confrontare due snapshot per vedere MAC aggiunti, rimossi o spostati.
              Seleziona 2 snapshot per abilitare il confronto.
            </p>
          </div>
        </div>
      </div>

      {/* Scheduler Panel */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${schedulerStatus?.config.enabled ? 'bg-green-100 dark:bg-green-900/30' : 'bg-gray-100 dark:bg-gray-700'}`}>
              <Timer className={`h-5 w-5 ${schedulerStatus?.config.enabled ? 'text-green-600 dark:text-green-400' : 'text-gray-500'}`} />
            </div>
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white">Snapshot Automatici</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {schedulerStatus?.config.enabled
                  ? `Attivo - ogni ${schedulerStatus.config.interval_hours} ore`
                  : 'Disabilitato'
                }
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {schedulerStatus?.next_scheduled_snapshot && (
              <span className="text-sm text-gray-500 dark:text-gray-400 mr-4">
                Prossimo: {new Date(schedulerStatus.next_scheduled_snapshot).toLocaleString('it-IT')}
              </span>
            )}
            <button
              onClick={runManualSnapshot}
              disabled={runningManual}
              className="flex items-center gap-2 px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              title="Esegui snapshot ora"
            >
              {runningManual ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Esegui Ora
            </button>
            <button
              onClick={() => setShowSchedulerModal(true)}
              className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
            >
              <Settings className="h-4 w-4" />
              Configura
            </button>
          </div>
        </div>
        {schedulerStatus?.last_snapshot_result && (
          <div className={`mt-3 pt-3 border-t dark:border-gray-700 text-sm ${
            schedulerStatus.last_snapshot_result.success
              ? 'text-green-600 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'
          }`}>
            Ultimo snapshot automatico: {new Date(schedulerStatus.last_snapshot_result.timestamp).toLocaleString('it-IT')}
            {schedulerStatus.last_snapshot_result.success
              ? ` - ${schedulerStatus.last_snapshot_result.total_macs} MAC`
              : ` - Errore: ${schedulerStatus.last_snapshot_result.error}`
            }
          </div>
        )}
      </div>

      {/* Snapshots Grid */}
      {loading ? (
        <div className="text-center py-12">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-blue-500 mb-4" />
          <p className="text-gray-500 dark:text-gray-400">Caricamento snapshots...</p>
        </div>
      ) : snapshots.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg shadow">
          <Camera className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Nessuno Snapshot</h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Crea il primo snapshot per catturare lo stato attuale della rete.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Crea Snapshot
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {snapshots.map((snapshot) => (
            <div
              key={snapshot.id}
              className={`bg-white dark:bg-gray-800 rounded-lg shadow p-4 border-2 transition-colors ${
                selectedSnapshots.includes(snapshot.id)
                  ? 'border-purple-500 dark:border-purple-400'
                  : 'border-transparent'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  {/* Select Checkbox */}
                  <input
                    type="checkbox"
                    checked={selectedSnapshots.includes(snapshot.id)}
                    onChange={() => toggleSelect(snapshot.id)}
                    className="mt-1 h-4 w-4 text-purple-600 rounded"
                  />

                  {/* Icon */}
                  <div className={`p-3 rounded-lg ${
                    snapshot.is_baseline
                      ? 'bg-yellow-100 dark:bg-yellow-900/30'
                      : 'bg-gray-100 dark:bg-gray-700'
                  }`}>
                    <Camera className={`h-6 w-6 ${
                      snapshot.is_baseline
                        ? 'text-yellow-600 dark:text-yellow-400'
                        : 'text-gray-600 dark:text-gray-400'
                    }`} />
                  </div>

                  {/* Info */}
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-white">
                        {snapshot.name || `Snapshot #${snapshot.id}`}
                      </h3>
                      {snapshot.is_locked && (
                        <Lock className="h-4 w-4 text-orange-500" title="Bloccato" />
                      )}
                      {snapshot.is_baseline && (
                        <Star className="h-4 w-4 text-yellow-500" title="Baseline" />
                      )}
                      <span className={`px-2 py-0.5 text-xs rounded-full ${
                        snapshot.status === 'completed'
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          : snapshot.status === 'running'
                          ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                          : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                      }`}>
                        {snapshot.status}
                      </span>
                    </div>
                    {snapshot.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {snapshot.description}
                      </p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        {new Date(snapshot.started_at).toLocaleString('it-IT')}
                      </span>
                      <span className="flex items-center gap-1">
                        <Database className="h-3.5 w-3.5" />
                        {formatDuration(snapshot.discovery_duration_ms)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleLock(snapshot)}
                    className="p-2 text-gray-400 hover:text-orange-500 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                    title={snapshot.is_locked ? 'Sblocca' : 'Blocca'}
                  >
                    {snapshot.is_locked ? <Lock className="h-4 w-4" /> : <Unlock className="h-4 w-4" />}
                  </button>
                  <button
                    onClick={() => toggleBaseline(snapshot)}
                    className="p-2 text-gray-400 hover:text-yellow-500 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                    title={snapshot.is_baseline ? 'Rimuovi Baseline' : 'Imposta come Baseline'}
                  >
                    <Star className={`h-4 w-4 ${snapshot.is_baseline ? 'fill-yellow-500 text-yellow-500' : ''}`} />
                  </button>
                  <button
                    onClick={() => deleteSnapshot(snapshot.id)}
                    disabled={snapshot.is_locked}
                    className="p-2 text-gray-400 hover:text-red-500 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Elimina"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-5 gap-4 mt-4 pt-4 border-t dark:border-gray-700">
                <div className="text-center">
                  <div className="text-xl font-bold text-blue-600">{snapshot.total_switches.toLocaleString()}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Switch</div>
                </div>
                <div className="text-center">
                  <div className="text-xl font-bold text-green-600">{snapshot.total_ports.toLocaleString()}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Porte</div>
                </div>
                <div className="text-center">
                  <div className="text-xl font-bold text-purple-600">{snapshot.total_macs.toLocaleString()}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">MAC</div>
                </div>
                <div className="text-center">
                  <div className="text-xl font-bold text-orange-600">{snapshot.total_hosts}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Hosts</div>
                </div>
                <div className="text-center">
                  <div className="text-xl font-bold text-cyan-600">{snapshot.total_links.toLocaleString()}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">Links</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              Crea Nuovo Snapshot
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Nome (opzionale)
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Es: Snapshot pre-migrazione"
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Descrizione (opzionale)
                </label>
                <textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Es: Cattura stato rete prima della migrazione VLAN"
                  rows={3}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                Annulla
              </button>
              <button
                onClick={createSnapshot}
                disabled={creating}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {creating ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Creazione...
                  </>
                ) : (
                  <>
                    <Camera className="h-4 w-4" />
                    Crea Snapshot
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Scheduler Config Modal */}
      {showSchedulerModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              Configura Snapshot Automatici
            </h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Abilita snapshot automatici
                </label>
                <button
                  onClick={() => setSchedulerEnabled(!schedulerEnabled)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    schedulerEnabled ? 'bg-green-600' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      schedulerEnabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Intervallo (ore)
                </label>
                <select
                  value={intervalHours}
                  onChange={(e) => setIntervalHours(Number(e.target.value))}
                  disabled={!schedulerEnabled}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white disabled:opacity-50"
                >
                  <option value={1}>Ogni ora</option>
                  <option value={2}>Ogni 2 ore</option>
                  <option value={4}>Ogni 4 ore</option>
                  <option value={6}>Ogni 6 ore</option>
                  <option value={8}>Ogni 8 ore</option>
                  <option value={12}>Ogni 12 ore</option>
                  <option value={24}>Ogni 24 ore</option>
                </select>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-sm text-gray-600 dark:text-gray-400">
                <p>Gli snapshot automatici catturano lo stato della rete a intervalli regolari.</p>
                <p className="mt-1">Utile per tracciare cambiamenti nel tempo e analisi storiche.</p>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowSchedulerModal(false)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                Annulla
              </button>
              <button
                onClick={saveSchedulerConfig}
                disabled={savingScheduler}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {savingScheduler ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Salvataggio...
                  </>
                ) : (
                  <>
                    <Settings className="h-4 w-4" />
                    Salva Configurazione
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
