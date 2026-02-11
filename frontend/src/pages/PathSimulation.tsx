import { useState } from 'react'
import { Route, Play, ArrowRight, MapPin, Server, CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react'

interface PathHop {
  hop_number: number
  switch_id: number
  switch_hostname: string
  switch_ip: string
  ingress_port: string | null
  egress_port: string | null
  vlan_id: number | null
  latency_estimate_ms: number
}

interface PathResult {
  source: string
  source_mac: string | null
  source_switch_id: number | null
  source_switch: string | null
  source_port: string | null
  destination: string
  destination_mac: string | null
  destination_switch_id: number | null
  destination_switch: string | null
  destination_port: string | null
  path_found: boolean
  hops: PathHop[]
  total_hops: number
  estimated_latency_ms: number
  status: string
  notes: string[]
}

export default function PathSimulation() {
  const [source, setSource] = useState('')
  const [destination, setDestination] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PathResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const simulatePath = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!source.trim() || !destination.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch('/api/graph/simulate-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source.trim(), destination: destination.trim() })
      })

      if (!response.ok) {
        throw new Error('Errore nella simulazione')
      }

      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError('Errore durante la simulazione del percorso')
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success': return 'text-green-600 dark:text-green-400'
      case 'no_path': return 'text-red-600 dark:text-red-400'
      case 'source_not_found':
      case 'destination_not_found': return 'text-orange-600 dark:text-orange-400'
      default: return 'text-gray-600 dark:text-gray-400'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle className="h-6 w-6 text-green-600" />
      case 'no_path': return <XCircle className="h-6 w-6 text-red-600" />
      default: return <AlertTriangle className="h-6 w-6 text-orange-600" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Route className="h-7 w-7 text-purple-600" />
          Path Simulation
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Simula il percorso di un pacchetto tra due endpoint (MAC o IP)
        </p>
      </div>

      {/* Input Form */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow">
        <form onSubmit={simulatePath} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Sorgente (MAC o IP)
              </label>
              <input
                type="text"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="es. 00:0C:29:XX:XX:XX o 10.1.1.100"
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
            <div className="flex items-center justify-center">
              <ArrowRight className="h-6 w-6 text-gray-400" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Destinazione (MAC o IP)
              </label>
              <input
                type="text"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="es. 00:0C:29:YY:YY:YY o 10.1.2.50"
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
            </div>
          </div>
          <div className="flex justify-center">
            <button
              type="submit"
              disabled={loading || !source.trim() || !destination.trim()}
              className="flex items-center gap-2 px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <RefreshCw className="h-5 w-5 animate-spin" />
              ) : (
                <Play className="h-5 w-5" />
              )}
              {loading ? 'Simulazione...' : 'Simula Percorso'}
            </button>
          </div>
        </form>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Status Card */}
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow">
            <div className="flex items-center gap-4">
              {getStatusIcon(result.status)}
              <div>
                <h2 className={`text-xl font-semibold ${getStatusColor(result.status)}`}>
                  {result.status === 'success' ? 'Percorso Trovato' :
                   result.status === 'no_path' ? 'Nessun Percorso' :
                   result.status === 'source_not_found' ? 'Sorgente Non Trovata' :
                   result.status === 'destination_not_found' ? 'Destinazione Non Trovata' :
                   'Errore'}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {result.notes.join(' | ')}
                </p>
              </div>
              {result.path_found && (
                <div className="ml-auto text-right">
                  <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                    {result.total_hops}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">hop</div>
                </div>
              )}
            </div>
          </div>

          {/* Endpoints */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Source */}
            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow border-l-4 border-green-500">
              <div className="flex items-center gap-2 mb-2">
                <MapPin className="h-5 w-5 text-green-600" />
                <span className="font-semibold text-gray-900 dark:text-white">Sorgente</span>
              </div>
              {result.source_switch ? (
                <div className="space-y-1 text-sm">
                  <div className="font-mono text-gray-600 dark:text-gray-400">{result.source_mac || result.source}</div>
                  <div className="flex items-center gap-2">
                    <Server className="h-4 w-4 text-gray-400" />
                    <span className="text-gray-900 dark:text-white">{result.source_switch}</span>
                    <span className="text-gray-500">porta {result.source_port}</span>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-gray-500">Non trovato nel network</div>
              )}
            </div>

            {/* Destination */}
            <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow border-l-4 border-blue-500">
              <div className="flex items-center gap-2 mb-2">
                <MapPin className="h-5 w-5 text-blue-600" />
                <span className="font-semibold text-gray-900 dark:text-white">Destinazione</span>
              </div>
              {result.destination_switch ? (
                <div className="space-y-1 text-sm">
                  <div className="font-mono text-gray-600 dark:text-gray-400">{result.destination_mac || result.destination}</div>
                  <div className="flex items-center gap-2">
                    <Server className="h-4 w-4 text-gray-400" />
                    <span className="text-gray-900 dark:text-white">{result.destination_switch}</span>
                    <span className="text-gray-500">porta {result.destination_port}</span>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-gray-500">Non trovato nel network</div>
              )}
            </div>
          </div>

          {/* Path Visualization */}
          {result.path_found && result.hops.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Percorso L2
              </h3>
              <div className="flex items-center overflow-x-auto pb-4">
                {result.hops.map((hop, idx) => (
                  <div key={hop.switch_id} className="flex items-center">
                    <div className="flex flex-col items-center min-w-[120px]">
                      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                        idx === 0 ? 'bg-green-100 dark:bg-green-900/30 text-green-600' :
                        idx === result.hops.length - 1 ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600' :
                        'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                      }`}>
                        <Server className="h-6 w-6" />
                      </div>
                      <div className="mt-2 text-center">
                        <div className="text-sm font-medium text-gray-900 dark:text-white truncate max-w-[100px]">
                          {hop.switch_hostname}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          {hop.switch_ip}
                        </div>
                        {(hop.ingress_port || hop.egress_port) && (
                          <div className="text-xs text-purple-600 dark:text-purple-400 mt-1">
                            {hop.ingress_port && <span>in: {hop.ingress_port}</span>}
                            {hop.ingress_port && hop.egress_port && ' | '}
                            {hop.egress_port && <span>out: {hop.egress_port}</span>}
                          </div>
                        )}
                      </div>
                    </div>
                    {idx < result.hops.length - 1 && (
                      <div className="flex-shrink-0 w-16 h-1 bg-gray-300 dark:bg-gray-600 mx-2" />
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-4 border-t dark:border-gray-700 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                <span>Latenza stimata: <strong>{result.estimated_latency_ms.toFixed(2)}ms</strong></span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
