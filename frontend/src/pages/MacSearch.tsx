import { useState, useEffect, useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, Download, RefreshCw, X, MapPin, ArrowRight, Smartphone, Wifi, Phone, Monitor, Server, Printer, HelpCircle, Bookmark, ChevronDown, Trash2, Save, Building2 } from 'lucide-react'
import { macsApi, MacSearchResult, EndpointTraceResponse, switchesApi, SiteCodeInfo } from '../api/client'

// Filter preset type
interface FilterPreset {
  id: string;
  name: string;
  query: string;
  useRegex: boolean;
}

// Default presets
const DEFAULT_PRESETS: FilterPreset[] = [
  { id: 'vlan13', name: 'Solo VLAN 13 (Palmari)', query: 'vlan:13', useRegex: false },
  { id: 'handheld', name: 'Solo Palmari', query: 'handheld', useRegex: false },
  { id: 'extreme', name: 'Access Point Extreme', query: '00:E6:0E', useRegex: false },
]

// Load presets from localStorage
const loadPresets = (): FilterPreset[] => {
  try {
    const saved = localStorage.getItem('macSearchPresets')
    if (saved) {
      return [...DEFAULT_PRESETS, ...JSON.parse(saved)]
    }
  } catch {}
  return DEFAULT_PRESETS
}

// Save custom presets to localStorage
const savePresetsToStorage = (presets: FilterPreset[]) => {
  const customPresets = presets.filter(p => !DEFAULT_PRESETS.find(d => d.id === p.id))
  localStorage.setItem('macSearchPresets', JSON.stringify(customPresets))
}

// Device type badge component with colored icons
const DeviceTypeBadge = ({ deviceType }: { deviceType?: string }) => {
  const config: Record<string, { icon: React.ReactNode; label: string; bgColor: string; textColor: string }> = {
    handheld: {
      icon: <Smartphone className="h-3.5 w-3.5" />,
      label: 'Palmare',
      bgColor: 'bg-purple-100 dark:bg-purple-900/30',
      textColor: 'text-purple-700 dark:text-purple-400'
    },
    access_point: {
      icon: <Wifi className="h-3.5 w-3.5" />,
      label: 'AP WiFi',
      bgColor: 'bg-cyan-100 dark:bg-cyan-900/30',
      textColor: 'text-cyan-700 dark:text-cyan-400'
    },
    ip_phone: {
      icon: <Phone className="h-3.5 w-3.5" />,
      label: 'Telefono IP',
      bgColor: 'bg-orange-100 dark:bg-orange-900/30',
      textColor: 'text-orange-700 dark:text-orange-400'
    },
    workstation: {
      icon: <Monitor className="h-3.5 w-3.5" />,
      label: 'Workstation',
      bgColor: 'bg-blue-100 dark:bg-blue-900/30',
      textColor: 'text-blue-700 dark:text-blue-400'
    },
    server: {
      icon: <Server className="h-3.5 w-3.5" />,
      label: 'Server',
      bgColor: 'bg-indigo-100 dark:bg-indigo-900/30',
      textColor: 'text-indigo-700 dark:text-indigo-400'
    },
    printer: {
      icon: <Printer className="h-3.5 w-3.5" />,
      label: 'Stampante',
      bgColor: 'bg-pink-100 dark:bg-pink-900/30',
      textColor: 'text-pink-700 dark:text-pink-400'
    },
    mobile: {
      icon: <Smartphone className="h-3.5 w-3.5" />,
      label: 'Mobile',
      bgColor: 'bg-emerald-100 dark:bg-emerald-900/30',
      textColor: 'text-emerald-700 dark:text-emerald-400'
    },
    scale: {
      icon: <Server className="h-3.5 w-3.5" />,
      label: 'Bilancia',
      bgColor: 'bg-amber-100 dark:bg-amber-900/30',
      textColor: 'text-amber-700 dark:text-amber-400'
    },
    pos: {
      icon: <Monitor className="h-3.5 w-3.5" />,
      label: 'POS',
      bgColor: 'bg-rose-100 dark:bg-rose-900/30',
      textColor: 'text-rose-700 dark:text-rose-400'
    },
    unknown: {
      icon: <HelpCircle className="h-3.5 w-3.5" />,
      label: 'Sconosciuto',
      bgColor: 'bg-gray-100 dark:bg-gray-700',
      textColor: 'text-gray-600 dark:text-gray-400'
    }
  }

  const type = deviceType?.toLowerCase() || 'unknown'
  const { icon, label, bgColor, textColor } = config[type] || config.unknown

  if (!deviceType || deviceType === 'unknown') {
    return <span className="text-gray-400">-</span>
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${bgColor} ${textColor}`}>
      {icon}
      {label}
    </span>
  )
}

// Extended result with endpoint trace info
interface MacResultWithEndpoint extends MacSearchResult {
  endpointTrace?: EndpointTraceResponse;
  traceLoading?: boolean;
}

/**
 * Normalize MAC address from any format to standard format (XX:XX:XX:XX:XX:XX)
 * Supports:
 * - Huawei: 00e6-0e65-5900
 * - Cisco: 00e6.0e65.5900
 * - Dash: 00-E6-0E-65-59-00
 * - Colon: 00:E6:0E:65:59:00
 * - No separator: 00E60E655900
 */
function normalizeMacAddress(input: string): string {
  // Remove all separators and convert to uppercase
  const cleaned = input.replace(/[:\-\.]/g, '').toUpperCase()

  // Check if it looks like a MAC address (12 hex characters)
  if (/^[0-9A-F]{12}$/.test(cleaned)) {
    // Convert to standard format XX:XX:XX:XX:XX:XX
    return cleaned.match(/.{2}/g)!.join(':')
  }

  // If partial MAC (less than 12 chars but valid hex), return as-is for partial search
  if (/^[0-9A-F]+$/.test(cleaned) && cleaned.length < 12) {
    return cleaned
  }

  // Not a MAC address format, return original for hostname/IP search
  return input
}

export default function MacSearch() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(() => searchParams.get('q') || '')
  const [results, setResults] = useState<MacResultWithEndpoint[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState('')
  const [useRegex, setUseRegex] = useState(false)

  // Live search state (SSH trace for MACs not in DB)
  const [liveSearchLoading, setLiveSearchLoading] = useState(false)
  const [liveSearchResult, setLiveSearchResult] = useState<EndpointTraceResponse | null>(null)
  const [liveSearchError, setLiveSearchError] = useState('')

  // Site selection for live search
  const [sites, setSites] = useState<SiteCodeInfo[]>([])
  const [selectedSite, setSelectedSite] = useState<string>('')

  // Filter presets state
  const [presets, setPresets] = useState<FilterPreset[]>(loadPresets)
  const [showPresetMenu, setShowPresetMenu] = useState(false)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [newPresetName, setNewPresetName] = useState('')

  // Fetch endpoint trace for a single MAC
  const fetchEndpointTrace = async (mac: MacResultWithEndpoint): Promise<MacResultWithEndpoint> => {
    try {
      const traceResponse = await macsApi.traceEndpoint(mac.mac_address)
      return { ...mac, endpointTrace: traceResponse.data, traceLoading: false }
    } catch {
      return { ...mac, traceLoading: false }
    }
  }

  // Execute search based on a query string
  const executeSearch = useCallback(async (searchQuery: string, regexMode: boolean = false) => {
    setLoading(true)
    setError('')
    setSearched(true)

    try {
      const response = await macsApi.search({ q: searchQuery, use_regex: regexMode })
      const initialResults: MacResultWithEndpoint[] = response.data.items.map(item => ({
        ...item,
        traceLoading: true
      }))
      setResults(initialResults)
      setTotal(response.data.total)

      // Fetch endpoint traces in background (parallel, max 5 at a time)
      const batchSize = 5
      for (let i = 0; i < initialResults.length; i += batchSize) {
        const batch = initialResults.slice(i, i + batchSize)
        const tracedBatch = await Promise.all(batch.map(fetchEndpointTrace))

        setResults(prev => {
          const updated = [...prev]
          tracedBatch.forEach((traced, idx) => {
            updated[i + idx] = traced
          })
          return updated
        })
      }
    } catch (err: any) {
      setError(err.userMessage || 'Errore durante la ricerca')
      setResults([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [])

  // Load available sites on mount
  useEffect(() => {
    const loadSites = async () => {
      try {
        const response = await switchesApi.getSiteCodes()
        setSites(response.data)
      } catch (err) {
        console.error('Failed to load sites:', err)
      }
    }
    loadSites()
  }, [])

  // Close preset menu on outside click
  useEffect(() => {
    if (showPresetMenu) {
      const handleClick = () => setShowPresetMenu(false)
      document.addEventListener('click', handleClick)
      return () => document.removeEventListener('click', handleClick)
    }
  }, [showPresetMenu])

  // When URL query changes (including browser back/forward), sync state and execute search
  useEffect(() => {
    const urlQuery = searchParams.get('q')
    const urlRegex = searchParams.get('regex') === 'true'
    if (urlQuery) {
      // Normalize MAC address format from URL (skip normalization if regex mode)
      const normalizedQuery = urlRegex ? urlQuery : normalizeMacAddress(urlQuery)
      setQuery(normalizedQuery)
      setUseRegex(urlRegex)
      executeSearch(normalizedQuery, urlRegex)
    } else if (searched) {
      // If URL has no query but we had searched before, clear results
      setSearched(false)
      setResults([])
      setTotal(0)
    }
  }, [searchParams]) // React to URL changes

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()

    // Normalize MAC address format before searching (skip if regex mode)
    const normalizedQuery = useRegex ? query.trim() : normalizeMacAddress(query.trim())

    // Update URL with normalized query and regex flag
    if (normalizedQuery) {
      const params: Record<string, string> = { q: normalizedQuery }
      if (useRegex) params.regex = 'true'
      setSearchParams(params)
      setQuery(normalizedQuery) // Update input field with normalized format
    } else {
      setSearchParams({})
    }

    executeSearch(normalizedQuery, useRegex)
  }

  const handleClear = () => {
    setQuery('')
    setSearchParams({})
    setResults([])
    setTotal(0)
    setSearched(false)
    setError('')
    setLiveSearchResult(null)
    setLiveSearchError('')
  }

  // Live search via SSH trace - for MACs not found in database
  const handleLiveSearch = async () => {
    if (!query.trim()) return

    // Check if site is selected
    if (!selectedSite) {
      setLiveSearchError('Seleziona un sito prima di effettuare la ricerca live')
      return
    }

    // Normalize the MAC address
    const normalizedMac = normalizeMacAddress(query.trim())

    // Check if it looks like a valid MAC
    if (!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(normalizedMac)) {
      setLiveSearchError('Inserisci un MAC address completo (es. 00:E6:0E:59:E7:C0)')
      return
    }

    setLiveSearchLoading(true)
    setLiveSearchResult(null)
    setLiveSearchError('')

    try {
      // Pass the selected site to the trace API
      const response = await macsApi.traceEndpoint(normalizedMac, selectedSite)
      if (response.data && response.data.endpoint_switch_hostname) {
        setLiveSearchResult(response.data)
      } else {
        setLiveSearchError('MAC non trovato sulla rete')
      }
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Errore durante la ricerca live'
      setLiveSearchError(errorMessage)
    } finally {
      setLiveSearchLoading(false)
    }
  }

  // Apply a preset filter
  const applyPreset = (preset: FilterPreset) => {
    setQuery(preset.query)
    setUseRegex(preset.useRegex)
    setShowPresetMenu(false)
    // Trigger search
    const params: Record<string, string> = { q: preset.query }
    if (preset.useRegex) params.regex = 'true'
    setSearchParams(params)
    executeSearch(preset.query, preset.useRegex)
  }

  // Save current search as preset
  const saveAsPreset = () => {
    if (!newPresetName.trim() || !query.trim()) return
    const newPreset: FilterPreset = {
      id: `custom-${Date.now()}`,
      name: newPresetName.trim(),
      query: query.trim(),
      useRegex
    }
    const updatedPresets = [...presets, newPreset]
    setPresets(updatedPresets)
    savePresetsToStorage(updatedPresets)
    setShowSaveDialog(false)
    setNewPresetName('')
  }

  // Delete a custom preset
  const deletePreset = (presetId: string) => {
    const updatedPresets = presets.filter(p => p.id !== presetId)
    setPresets(updatedPresets)
    savePresetsToStorage(updatedPresets)
  }

  // REMOVED: handleSeedData function (Feature #127 - removed demo data functionality)

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Ricerca MAC Address
        </h1>
        <div className="flex gap-2">
          {/* REMOVED: "Carica Dati Demo" button (Feature #127 - use real data only from discovery) */}
          <button
            onClick={() => macsApi.exportCsv({ q: query || undefined })}
            disabled={!searched || results.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={!searched || results.length === 0 ? 'Effettua prima una ricerca con risultati' : 'Esporta risultati in CSV'}
          >
            <Download className="h-4 w-4" />
            Esporta CSV
          </button>
        </div>
      </div>

      {/* Filter Presets Bar */}
      <div className="mb-4 flex items-center gap-3">
        {/* Preset dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowPresetMenu(!showPresetMenu) }}
            className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <Bookmark className="h-4 w-4" />
            Filtri Salvati
            <ChevronDown className="h-4 w-4" />
          </button>
          {showPresetMenu && (
            <div
              className="absolute top-full left-0 mt-1 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-2 border-b border-gray-200 dark:border-gray-700">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Filtri predefiniti</span>
              </div>
              {presets.map(preset => (
                <div
                  key={preset.id}
                  className="flex items-center justify-between px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer group"
                >
                  <button
                    type="button"
                    onClick={() => applyPreset(preset)}
                    className="flex-1 text-left text-sm text-gray-700 dark:text-gray-200"
                  >
                    {preset.name}
                    {preset.useRegex && <span className="ml-1 text-xs text-purple-500">(RegEx)</span>}
                  </button>
                  {preset.id.startsWith('custom-') && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); deletePreset(preset.id) }}
                      className="p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Elimina filtro"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
              {presets.length === DEFAULT_PRESETS.length && (
                <div className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500 italic">
                  Nessun filtro personalizzato
                </div>
              )}
            </div>
          )}
        </div>

        {/* Save current filter button */}
        {query && (
          <button
            type="button"
            onClick={() => setShowSaveDialog(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50"
          >
            <Save className="h-4 w-4" />
            Salva filtro
          </button>
        )}

        {/* Save dialog */}
        {showSaveDialog && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-96">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Salva Filtro</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                Query: <span className="font-mono text-blue-600 dark:text-blue-400">{query}</span>
                {useRegex && <span className="ml-2 text-purple-500">(RegEx)</span>}
              </p>
              <input
                type="text"
                value={newPresetName}
                onChange={(e) => setNewPresetName(e.target.value)}
                placeholder="Nome del filtro (es. Solo palmari PDV)"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white mb-4"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => { setShowSaveDialog(false); setNewPresetName('') }}
                  className="px-4 py-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                >
                  Annulla
                </button>
                <button
                  type="button"
                  onClick={saveAsPreset}
                  disabled={!newPresetName.trim()}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  Salva
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="mb-6">
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <label htmlFor="mac-search-input" className="sr-only">
              Cerca per MAC, IP o hostname
            </label>
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              id="mac-search-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={useRegex ? "Pattern regex: ^00:18:6E.*, .*:AB:CD$" : "Cerca per MAC, IP, hostname..."}
              className="w-full pl-10 pr-4 py-3 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          {/* Regex Toggle */}
          <div className="flex items-center">
            <label className="relative inline-flex items-center cursor-pointer" title="Attiva ricerca con espressioni regolari (^inizio, $fine, .* qualsiasi)">
              <input
                type="checkbox"
                checked={useRegex}
                onChange={(e) => setUseRegex(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
              <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">RegEx</span>
            </label>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Ricerca...
              </>
            ) : (
              'Cerca'
            )}
          </button>
          {(query || searched) && (
            <button
              type="button"
              onClick={handleClear}
              className="px-4 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors flex items-center gap-2"
              aria-label="Pulisci ricerca"
            >
              <X className="h-4 w-4" />
              Pulisci
            </button>
          )}
        </div>
      </form>

      {error && (
        <div className="mb-4 p-4 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg">
          {error}
        </div>
      )}

      {/* Results */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-x-auto">
        {!searched ? (
          <div className="p-12 text-center text-gray-500 dark:text-gray-400">
            <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Inserisci un MAC address, IP o hostname per iniziare la ricerca</p>
          </div>
        ) : results.length === 0 ? (
          <div className="p-12 text-center text-gray-500 dark:text-gray-400">
            <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Nessun risultato trovato per "{query}" nel database locale</p>
            <p className="text-sm mt-2 mb-4">Prova la ricerca live via SSH sugli switch</p>

            {/* Site Selector for Live Search */}
            <div className="flex items-center justify-center gap-3 mb-4">
              <Building2 className="h-5 w-5 text-gray-500" />
              <select
                value={selectedSite}
                onChange={(e) => setSelectedSite(e.target.value)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">-- Seleziona Sito --</option>
                {sites.map((site) => (
                  <option key={site.code} value={site.code}>
                    Sito {site.code} ({site.count} switch)
                  </option>
                ))}
              </select>
            </div>

            {/* Live Search Button */}
            <button
              onClick={handleLiveSearch}
              disabled={liveSearchLoading || !selectedSite}
              className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 mx-auto"
            >
              {liveSearchLoading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Ricerca Live in corso...
                </>
              ) : (
                <>
                  <MapPin className="h-4 w-4" />
                  Cerca Live via SSH
                </>
              )}
            </button>

            {/* Live Search Error */}
            {liveSearchError && (
              <div className="mt-4 p-4 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg max-w-md mx-auto">
                {liveSearchError}
              </div>
            )}

            {/* Live Search Result */}
            {liveSearchResult && (
              <div className="mt-6 p-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg max-w-2xl mx-auto text-left">
                <h3 className="text-lg font-semibold text-green-800 dark:text-green-300 mb-4 flex items-center gap-2">
                  <MapPin className="h-5 w-5" />
                  MAC Trovato via SSH!
                </h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">MAC Address:</span>
                    <p className="font-mono font-semibold text-gray-900 dark:text-white">{liveSearchResult.mac_address}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Vendor:</span>
                    <p className="text-gray-900 dark:text-white">{liveSearchResult.vendor_name || '-'}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Switch Endpoint:</span>
                    <p className="font-semibold text-gray-900 dark:text-white">{liveSearchResult.endpoint_switch_hostname}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">IP Switch:</span>
                    <p className="text-gray-900 dark:text-white">{liveSearchResult.endpoint_switch_ip}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Porta:</span>
                    <p className="font-semibold text-green-700 dark:text-green-400">{liveSearchResult.endpoint_port_name}</p>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">VLAN:</span>
                    <p className="text-gray-900 dark:text-white">{liveSearchResult.vlan_id || '-'}</p>
                  </div>
                </div>
                {liveSearchResult.trace_path && liveSearchResult.trace_path.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-green-200 dark:border-green-800">
                    <span className="text-gray-500 dark:text-gray-400 text-sm">Percorso:</span>
                    <div className="flex flex-wrap items-center gap-2 mt-1">
                      {liveSearchResult.trace_path.map((hop, idx) => (
                        <span key={idx} className="flex items-center gap-1">
                          <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-mono">
                            {hop}
                          </span>
                          {idx < liveSearchResult.trace_path!.length - 1 && (
                            <ArrowRight className="h-3 w-3 text-gray-400" />
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="px-6 py-3 bg-gray-50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Trovati <strong>{total}</strong> risultati
              </span>
            </div>
            <table className="w-full min-w-[800px]">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    MAC Address
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    IP
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Switch
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Porta
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Endpoint Reale
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    VLAN
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Vendor
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Tipo
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Ultimo Avvistamento
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {results.map((mac) => (
                  <tr key={mac.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Link
                        to={`/mac/${mac.id}`}
                        state={{ searchQuery: query }}
                        className="text-blue-600 dark:text-blue-400 hover:underline font-mono"
                      >
                        {mac.mac_address}
                      </Link>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white font-mono">
                      {mac.ip_address || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                      {mac.switch_hostname || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white font-mono">
                      {mac.port_name || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {mac.traceLoading ? (
                        <span className="text-gray-400 italic">Tracing...</span>
                      ) : mac.endpointTrace ? (
                        // Compare current row's switch with the traced endpoint switch
                        mac.switch_hostname === mac.endpointTrace.endpoint_switch_hostname &&
                        mac.port_name === mac.endpointTrace.endpoint_port_name ? (
                          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                            <MapPin className="h-3 w-3" />
                            Endpoint
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 cursor-pointer"
                            title={`Endpoint reale: ${mac.endpointTrace.endpoint_switch_hostname}:${mac.endpointTrace.endpoint_port_name}`}
                          >
                            <ArrowRight className="h-3 w-3" />
                            {mac.endpointTrace.endpoint_switch_hostname}
                          </span>
                        )
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                      {mac.vlan_id || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {mac.vendor_name || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <DeviceTypeBadge deviceType={mac.device_type} />
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatDate(mac.last_seen)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  )
}
