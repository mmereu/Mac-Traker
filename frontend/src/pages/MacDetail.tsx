import { useState, useEffect } from 'react'
import { useParams, Link, useLocation } from 'react-router-dom'
import { ArrowLeft, MapPin, Clock, History, Server, Network, Download, Route, CheckCircle, AlertTriangle } from 'lucide-react'
import { macsApi, MacDetail as MacDetailType, EndpointTraceResponse } from '../api/client'

export default function MacDetail() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const [mac, setMac] = useState<MacDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [endpointTrace, setEndpointTrace] = useState<EndpointTraceResponse | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [traceFailed, setTraceFailed] = useState(false)
  const [selectedSite, setSelectedSite] = useState('')

  // Preserve the search query from the referrer URL
  const searchQuery = (location.state as { searchQuery?: string })?.searchQuery || ''
  const backUrl = searchQuery ? `/mac-search?q=${encodeURIComponent(searchQuery)}` : '/mac-search'

  useEffect(() => {
    if (id) {
      loadMacDetail(parseInt(id))
    }
  }, [id])

  const loadMacDetail = async (macId: number) => {
    setLoading(true)
    try {
      const response = await macsApi.get(macId)
      setMac(response.data)

      // Load endpoint trace in background
      setTraceLoading(true)
      setTraceFailed(false)
      try {
        const traceResponse = await macsApi.traceEndpoint(response.data.mac_address)
        setEndpointTrace(traceResponse.data)
      } catch {
        // Trace failed - show retry with site selector
        setTraceFailed(true)
      } finally {
        setTraceLoading(false)
      }
    } catch (err: any) {
      setError(err.userMessage || 'Errore nel caricamento dei dettagli')
    } finally {
      setLoading(false)
    }
  }

  const retryTraceWithSite = async () => {
    if (!mac || !selectedSite) return
    setTraceLoading(true)
    setTraceFailed(false)
    try {
      const traceResponse = await macsApi.traceEndpoint(mac.mac_address, selectedSite)
      setEndpointTrace(traceResponse.data)
    } catch {
      setTraceFailed(true)
    } finally {
      setTraceLoading(false)
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  const getEventTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      new: 'Nuovo MAC',
      move: 'Spostamento',
      disappear: 'Scomparsa'
    }
    return labels[type] || type
  }

  const getEventTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      new: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
      move: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
      disappear: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
    }
    return colors[type] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error || !mac) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 dark:text-red-400">{error || 'MAC non trovato'}</p>
        <Link to={backUrl} className="text-blue-600 hover:underline mt-4 inline-block">
          Torna alla ricerca
        </Link>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <Link
          to={backUrl}
          className="inline-flex items-center text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 mb-4"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Torna alla ricerca
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-white font-mono">
              {mac.mac_address}
            </h1>
            <p className="text-gray-500 dark:text-gray-400">
              {mac.vendor_name || 'Vendor sconosciuto'}
            </p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            mac.is_active
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400'
          }`}>
            {mac.is_active ? 'Attivo' : 'Inattivo'}
          </span>
        </div>
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Clock className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Prima apparizione</p>
              <p className="font-medium text-gray-900 dark:text-white text-sm">
                {formatDate(mac.first_seen)}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <Clock className="h-5 w-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Ultimo avvistamento</p>
              <p className="font-medium text-gray-900 dark:text-white text-sm">
                {formatDate(mac.last_seen)}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
              <Network className="h-5 w-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">OUI Prefix</p>
              <p className="font-medium text-gray-900 dark:text-white font-mono">
                {mac.vendor_oui || '-'}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-lg">
              <Server className="h-5 w-5 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Tipo dispositivo</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {mac.device_type || 'Sconosciuto'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Current Location */}
      {mac.current_location && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Posizione Attuale
            </h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Switch</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {mac.current_location.switch_hostname}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                {mac.current_location.switch_ip}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Porta</p>
              <p className="font-medium text-gray-900 dark:text-white font-mono">
                {mac.current_location.port_name}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">VLAN</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {mac.current_location.vlan_id || '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">IP Address</p>
              <p className="font-medium text-gray-900 dark:text-white font-mono">
                {mac.current_location.ip_address || '-'}
              </p>
            </div>
          </div>
          {mac.current_location.hostname && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <p className="text-sm text-gray-500 dark:text-gray-400">Hostname</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {mac.current_location.hostname}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Endpoint Trace Section */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Route className="h-5 w-5 text-purple-600 dark:text-purple-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Endpoint Fisico (Trace)
          </h2>
          {traceLoading && (
            <span className="ml-2 text-sm text-gray-400 italic">Tracing...</span>
          )}
        </div>

        {traceLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
          </div>
        ) : endpointTrace ? (
          <div>
            {/* Endpoint Status Badge */}
            <div className="mb-4">
              {endpointTrace.is_endpoint ? (
                <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                  <CheckCircle className="h-5 w-5" />
                  <span className="font-medium">Connesso direttamente all'endpoint</span>
                </div>
              ) : (
                <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="font-medium">Visibile su uplink - Endpoint reale tracciato</span>
                </div>
              )}
            </div>

            {/* Endpoint Details */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Switch Endpoint</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {endpointTrace.endpoint_switch_hostname}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                  {endpointTrace.endpoint_switch_ip}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Porta Fisica</p>
                <p className="font-medium text-gray-900 dark:text-white font-mono">
                  {endpointTrace.endpoint_port_name}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">VLAN</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {endpointTrace.vlan_id || '-'}
                </p>
              </div>
              {endpointTrace.lldp_device_name && (
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">LLDP Device</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {endpointTrace.lldp_device_name}
                  </p>
                </div>
              )}
            </div>

            {/* Trace Path */}
            {endpointTrace.trace_path && endpointTrace.trace_path.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Percorso di rete</p>
                <div className="flex flex-wrap items-center gap-2">
                  {endpointTrace.trace_path.map((hop, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-sm font-mono text-gray-900 dark:text-white">
                        {hop}
                      </span>
                      {index < endpointTrace.trace_path.length - 1 && (
                        <span className="text-gray-400">→</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : traceFailed ? (
          <div className="text-center py-6">
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              Impossibile determinare il sito automaticamente. Seleziona il sito per tracciare l'endpoint.
            </p>
            <div className="flex items-center justify-center gap-3">
              <select
                value={selectedSite}
                onChange={(e) => setSelectedSite(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              >
                <option value="">Seleziona sito...</option>
                {Array.from({ length: 50 }, (_, i) => String(i + 1).padStart(2, '0')).map(site => (
                  <option key={site} value={site}>Sito {site}</option>
                ))}
              </select>
              <button
                onClick={retryTraceWithSite}
                disabled={!selectedSite || traceLoading}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {traceLoading ? 'Tracing...' : 'Traccia Endpoint'}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400 text-center py-8">
            Impossibile tracciare l'endpoint fisico
          </p>
        )}
      </div>

      {/* History */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Cronologia
            </h2>
          </div>
          {mac.history.length > 0 && (
            <button
              onClick={() => macsApi.exportHistoryCsv(mac.id)}
              className="flex items-center gap-2 px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition-colors"
              title="Esporta cronologia in CSV"
            >
              <Download className="h-4 w-4" />
              Esporta CSV
            </button>
          )}
        </div>

        {mac.history.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 text-center py-8">
            Nessun evento nella cronologia
          </p>
        ) : (
          <div className="space-y-4">
            {mac.history.map((event, index) => (
              <div
                key={index}
                className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
              >
                <span className={`px-2 py-1 rounded text-xs font-medium ${getEventTypeColor(event.event_type)}`}>
                  {getEventTypeLabel(event.event_type)}
                </span>
                <div className="flex-1">
                  <p className="text-sm text-gray-900 dark:text-white">
                    Switch ID: {event.switch_id}, Porta ID: {event.port_id}
                    {event.vlan_id && `, VLAN: ${event.vlan_id}`}
                    {event.ip_address && `, IP: ${event.ip_address}`}
                  </p>
                  {event.previous_switch_id && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Da: Switch {event.previous_switch_id}, Porta {event.previous_port_id}
                    </p>
                  )}
                </div>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {formatDate(event.event_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
