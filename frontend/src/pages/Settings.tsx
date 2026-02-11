import { useState, useEffect } from 'react'
import { Save, Play, Database, Bell as BellIcon, Clock, CheckCircle, AlertCircle, Loader2, Send, HardDrive, Trash2, RefreshCw, FileText, XCircle, ChevronDown, ChevronUp, Network, Server } from 'lucide-react'
import { discoveryApi, DiscoveryStatus, DiscoveryLog, settingsApi, TelegramTestResponse, backupApi, BackupInfo, SchedulerStatus, Settings as SettingsType, SeedDiscoveryResult, nediApi, NeDiConnectionStatus, NeDiImportResponse, NeDiSchedulerStatus } from '../api/client'

export default function Settings() {
  const [settings, setSettings] = useState<SettingsType>({
    discovery_interval: 15,
    history_retention_days: 90,
    telegram_bot_token: '',
    telegram_chat_id: '',
    alert_new_mac: true,
    alert_mac_move: true,
    alert_mac_disappear: true,
    alert_disappear_hours: 24,
    alert_port_threshold: 10,
  })

  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [saveLoading, setSaveLoading] = useState(false)
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatus | null>(null)
  const [discoveryLoading, setDiscoveryLoading] = useState(false)
  const [discoveryLogs, setDiscoveryLogs] = useState<DiscoveryLog[]>([])
  const [discoveryLogsLoading, setDiscoveryLogsLoading] = useState(false)
  const [discoveryLogsExpanded, setDiscoveryLogsExpanded] = useState(false)
  const [telegramLoading, setTelegramLoading] = useState(false)
  const [telegramResult, setTelegramResult] = useState<TelegramTestResponse | null>(null)

  // Backup state
  const [backups, setBackups] = useState<BackupInfo[]>([])
  const [backupLoading, setBackupLoading] = useState(false)
  const [backupScheduler, setBackupScheduler] = useState<SchedulerStatus | null>(null)
  const [backupMessage, setBackupMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [backupConfig, setBackupConfig] = useState({
    enabled: true,
    interval_hours: 24,
    time: '02:00'
  })

  // Seed Discovery state
  const [seedDiscoveryLoading, setSeedDiscoveryLoading] = useState(false)
  const [seedDiscoveryResult, setSeedDiscoveryResult] = useState<SeedDiscoveryResult | null>(null)
  const [seedConfig, setSeedConfig] = useState({
    seed_ip: '',
    snmp_community: 'public',
    device_type: 'huawei',
    max_depth: 3
  })

  // NeDi Integration state
  const [nediStatus, setNediStatus] = useState<NeDiConnectionStatus | null>(null)
  const [nediStatusLoading, setNediStatusLoading] = useState(false)
  const [nediImportLoading, setNediImportLoading] = useState(false)
  const [nediImportResult, setNediImportResult] = useState<NeDiImportResponse | null>(null)

  // NeDi Sync Scheduler state
  const [nediSchedulerStatus, setNediSchedulerStatus] = useState<NeDiSchedulerStatus | null>(null)
  const [nediSchedulerLoading, setNediSchedulerLoading] = useState(false)
  const [nediSyncNowLoading, setNediSyncNowLoading] = useState(false)
  const [nediSchedulerConfig, setNediSchedulerConfig] = useState({
    enabled: true,
    interval_minutes: 15,
    node_limit: 200000
  })

  // Load settings, backup data, and discovery logs on mount
  useEffect(() => {
    loadSettings()
    loadBackupData()
    loadDiscoveryLogs()
    loadNediSchedulerStatus()
  }, [])

  const loadDiscoveryLogs = async () => {
    setDiscoveryLogsLoading(true)
    try {
      const response = await discoveryApi.getLogs(20)
      setDiscoveryLogs(response.data)
    } catch (err) {
      console.error('Error loading discovery logs:', err)
    } finally {
      setDiscoveryLogsLoading(false)
    }
  }

  const loadSettings = async () => {
    setSettingsLoading(true)
    setSettingsError(null)
    try {
      const response = await settingsApi.get()
      setSettings(response.data)
    } catch (err: any) {
      setSettingsError(err.userMessage || 'Errore durante il caricamento delle impostazioni')
      console.error('Error loading settings:', err)
    } finally {
      setSettingsLoading(false)
    }
  }

  // Poll discovery status when running
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null

    if (discoveryStatus?.status === 'running') {
      interval = setInterval(async () => {
        try {
          const response = await discoveryApi.getStatus()
          setDiscoveryStatus(response.data)
          if (response.data.status !== 'running') {
            if (interval) clearInterval(interval)
          }
        } catch (err) {
          console.error('Error polling discovery status:', err)
        }
      }, 1000)
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [discoveryStatus?.status])

  // Backup functions
  const loadBackupData = async () => {
    try {
      const [backupsRes, schedulerRes] = await Promise.all([
        backupApi.list(),
        backupApi.getSchedulerStatus()
      ])
      setBackups(backupsRes.data)
      setBackupScheduler(schedulerRes.data)
      if (schedulerRes.data.config) {
        setBackupConfig(schedulerRes.data.config)
      }
    } catch (err) {
      console.error('Error loading backup data:', err)
    }
  }

  const createBackup = async () => {
    setBackupLoading(true)
    setBackupMessage(null)
    try {
      const response = await backupApi.manual()
      setBackupMessage({ type: 'success', text: `Backup creato: ${response.data.filename}` })
      loadBackupData()
    } catch (err: any) {
      setBackupMessage({ type: 'error', text: err.userMessage || 'Errore durante il backup' })
    } finally {
      setBackupLoading(false)
    }
  }

  const deleteBackup = async (filename: string) => {
    if (!confirm(`Eliminare il backup ${filename}?`)) return
    try {
      await backupApi.delete(filename)
      setBackupMessage({ type: 'success', text: 'Backup eliminato' })
      loadBackupData()
    } catch (err: any) {
      setBackupMessage({ type: 'error', text: err.userMessage || 'Errore durante eliminazione' })
    }
  }

  const saveBackupConfig = async () => {
    try {
      await backupApi.configureScheduler(backupConfig)
      setBackupMessage({ type: 'success', text: 'Configurazione backup salvata' })
      loadBackupData()
    } catch (err: any) {
      setBackupMessage({ type: 'error', text: err.userMessage || 'Errore durante salvataggio' })
    }
  }

  const formatDateTime = (isoString: string) => {
    return new Date(isoString).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const handleSave = async () => {
    setSaveLoading(true)
    setSaveMessage(null)
    try {
      await settingsApi.update(settings)
      setSaveMessage({ type: 'success', text: 'Impostazioni salvate con successo!' })
      // Auto-dismiss success message after 3 seconds
      setTimeout(() => setSaveMessage(null), 3000)
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.userMessage || 'Errore durante il salvataggio delle impostazioni' })
    } finally {
      setSaveLoading(false)
    }
  }

  const testTelegram = async () => {
    setTelegramLoading(true)
    setTelegramResult(null)
    try {
      const response = await settingsApi.testTelegram(
        settings.telegram_bot_token,
        settings.telegram_chat_id
      )
      setTelegramResult(response.data)
    } catch (err: any) {
      setTelegramResult({
        success: false,
        message: err.userMessage || 'Errore durante il test',
        details: err.message
      })
    } finally {
      setTelegramLoading(false)
    }
  }

  const startDiscovery = async () => {
    setDiscoveryLoading(true)
    try {
      const response = await discoveryApi.start()
      setDiscoveryStatus({
        status: 'running',
        message: response.data.message,
        switches_processed: 0,
        macs_found: 0,
      })
    } catch (err: any) {
      setDiscoveryStatus({
        status: 'error',
        message: err.userMessage || 'Errore avvio discovery',
        switches_processed: 0,
        macs_found: 0,
      })
    } finally {
      setDiscoveryLoading(false)
    }
  }

  const startSeedDiscovery = async () => {
    if (!seedConfig.seed_ip.trim()) {
      setSeedDiscoveryResult({
        status: 'error',
        message: 'Inserisci un indirizzo IP valido',
        switches_discovered: 0,
        switches_added: 0,
        switches_already_exist: 0,
        discovered_switches: [],
        errors: ['IP address richiesto']
      })
      return
    }

    setSeedDiscoveryLoading(true)
    setSeedDiscoveryResult(null)
    try {
      const response = await discoveryApi.seedDiscovery({
        seed_ip: seedConfig.seed_ip.trim(),
        snmp_community: seedConfig.snmp_community,
        device_type: seedConfig.device_type,
        max_depth: seedConfig.max_depth
      })
      setSeedDiscoveryResult(response.data)
    } catch (err: any) {
      setSeedDiscoveryResult({
        status: 'error',
        message: err.userMessage || 'Errore durante seed discovery',
        switches_discovered: 0,
        switches_added: 0,
        switches_already_exist: 0,
        discovered_switches: [],
        errors: [err.message || 'Errore sconosciuto']
      })
    } finally {
      setSeedDiscoveryLoading(false)
    }
  }

  // NeDi Integration functions
  const loadNediStatus = async () => {
    setNediStatusLoading(true)
    try {
      const response = await nediApi.getStatus()
      setNediStatus(response.data)
    } catch (err: any) {
      setNediStatus({
        connected: false,
        host: 'unknown',
        device_count: 0,
        node_count: 0,
        tables: [],
        error: err.userMessage || 'Errore connessione NeDi'
      })
    } finally {
      setNediStatusLoading(false)
    }
  }

  const importFromNedi = async () => {
    setNediImportLoading(true)
    setNediImportResult(null)
    try {
      const response = await nediApi.importAll(100000)
      setNediImportResult(response.data)
    } catch (err: any) {
      setNediImportResult({
        success: false,
        devices: { created: 0, updated: 0, skipped: 0, errors: 0 },
        nodes: { created: 0, updated: 0, skipped: 0, errors: 0 },
        links: { created: 0, updated: 0, skipped: 0, errors: 0 },
        error: err.userMessage || 'Errore durante importazione NeDi'
      })
    } finally {
      setNediImportLoading(false)
    }
  }

  // NeDi Sync Scheduler functions
  const loadNediSchedulerStatus = async () => {
    setNediSchedulerLoading(true)
    try {
      const response = await nediApi.getSchedulerStatus()
      setNediSchedulerStatus(response.data)
      setNediSchedulerConfig({
        enabled: response.data.enabled,
        interval_minutes: response.data.interval_minutes,
        node_limit: response.data.node_limit
      })
    } catch (err: any) {
      console.error('Error loading NeDi scheduler status:', err)
    } finally {
      setNediSchedulerLoading(false)
    }
  }

  const saveNediSchedulerConfig = async () => {
    setNediSchedulerLoading(true)
    try {
      const response = await nediApi.configureScheduler(nediSchedulerConfig)
      setNediSchedulerStatus(response.data.status)
      setSaveMessage({ type: 'success', text: 'Configurazione NeDi Sync salvata' })
      setTimeout(() => setSaveMessage(null), 3000)
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.userMessage || 'Errore durante salvataggio configurazione NeDi' })
    } finally {
      setNediSchedulerLoading(false)
    }
  }

  const runNediSyncNow = async () => {
    setNediSyncNowLoading(true)
    try {
      const response = await nediApi.runSyncNow()
      if (response.data.success) {
        setSaveMessage({ type: 'success', text: 'Sincronizzazione NeDi completata' })
      } else {
        setSaveMessage({ type: 'error', text: response.data.message || 'Errore durante sincronizzazione' })
      }
      // Refresh scheduler status
      loadNediSchedulerStatus()
      setTimeout(() => setSaveMessage(null), 3000)
    } catch (err: any) {
      setSaveMessage({ type: 'error', text: err.userMessage || 'Errore durante sincronizzazione NeDi' })
    } finally {
      setNediSyncNowLoading(false)
    }
  }

  const getDiscoveryIcon = () => {
    if (!discoveryStatus) return <Play className="h-4 w-4" />
    switch (discoveryStatus.status) {
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'completed':
        return <CheckCircle className="h-4 w-4" />
      case 'error':
        return <AlertCircle className="h-4 w-4" />
      default:
        return <Play className="h-4 w-4" />
    }
  }

  const getDiscoveryButtonClass = () => {
    if (!discoveryStatus || discoveryStatus.status === 'idle') {
      return 'bg-green-600 hover:bg-green-700'
    }
    switch (discoveryStatus.status) {
      case 'running':
        return 'bg-yellow-600 hover:bg-yellow-700'
      case 'completed':
        return 'bg-green-600 hover:bg-green-700'
      case 'error':
        return 'bg-red-600 hover:bg-red-700'
      default:
        return 'bg-green-600 hover:bg-green-700'
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Impostazioni
        </h1>
        <button
          onClick={handleSave}
          disabled={saveLoading || settingsLoading}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saveLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {saveLoading ? 'Salvataggio...' : 'Salva Impostazioni'}
        </button>
      </div>

      {/* Save message */}
      {saveMessage && (
        <div className={`mb-4 p-4 rounded-lg ${
          saveMessage.type === 'success'
            ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
            : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
        }`}>
          <div className="flex items-center gap-2">
            {saveMessage.type === 'success' ? (
              <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
            ) : (
              <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
            )}
            <p className={`font-medium ${
              saveMessage.type === 'success'
                ? 'text-green-800 dark:text-green-300'
                : 'text-red-800 dark:text-red-300'
            }`}>
              {saveMessage.text}
            </p>
          </div>
        </div>
      )}

      {/* Settings loading state */}
      {settingsLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600 dark:text-blue-400" />
          <span className="ml-3 text-gray-600 dark:text-gray-400">Caricamento impostazioni...</span>
        </div>
      )}

      {/* Settings error state */}
      {settingsError && !settingsLoading && (
        <div className="mb-4 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
            <p className="text-red-800 dark:text-red-300">{settingsError}</p>
          </div>
          <button
            onClick={loadSettings}
            className="mt-2 text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
          >
            Riprova
          </button>
        </div>
      )}

      <div className="space-y-6">
        {/* Discovery Settings */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <Clock className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              Discovery
            </h2>
          </div>

          <div className="space-y-4">
            <div>
              <label htmlFor="discovery-interval" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Intervallo Discovery (minuti)
              </label>
              <input
                id="discovery-interval"
                type="number"
                value={settings.discovery_interval}
                onChange={(e) => setSettings({ ...settings, discovery_interval: parseInt(e.target.value) })}
                className="w-full max-w-xs px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                min={5}
                max={60}
              />
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Intervallo tra ogni ciclo di discovery automatico (5-60 minuti)
              </p>
            </div>

            <div>
              <button
                onClick={startDiscovery}
                disabled={discoveryLoading || discoveryStatus?.status === 'running'}
                className={`flex items-center gap-2 px-4 py-2 text-white rounded-lg transition-colors disabled:opacity-50 ${getDiscoveryButtonClass()}`}
              >
                {getDiscoveryIcon()}
                {discoveryStatus?.status === 'running' ? 'Discovery in corso...' : 'Avvia Discovery Manuale'}
              </button>
            </div>

            {/* Discovery Status */}
            {discoveryStatus && (
              <div className={`p-4 rounded-lg ${
                discoveryStatus.status === 'running' ? 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800' :
                discoveryStatus.status === 'completed' ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800' :
                discoveryStatus.status === 'error' ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800' :
                'bg-gray-50 dark:bg-gray-700'
              }`}>
                <p className={`font-medium ${
                  discoveryStatus.status === 'running' ? 'text-yellow-800 dark:text-yellow-300' :
                  discoveryStatus.status === 'completed' ? 'text-green-800 dark:text-green-300' :
                  discoveryStatus.status === 'error' ? 'text-red-800 dark:text-red-300' :
                  'text-gray-800 dark:text-gray-300'
                }`}>
                  {discoveryStatus.message}
                </p>
                {(discoveryStatus.status === 'completed' || discoveryStatus.status === 'running') && (
                  <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    <p>Switch processati: {discoveryStatus.switches_processed}</p>
                    <p>MAC trovati: {discoveryStatus.macs_found}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Seed Discovery */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <Network className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              Seed Discovery
            </h2>
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Scopri automaticamente gli switch di rete partendo da un dispositivo seed via LLDP.
            Il sistema esplorera' i neighbor LLDP e aggiungera' automaticamente i nuovi switch trovati.
          </p>

          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="seed-ip" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Indirizzo IP Seed Device
                </label>
                <input
                  id="seed-ip"
                  type="text"
                  value={seedConfig.seed_ip}
                  onChange={(e) => setSeedConfig({ ...seedConfig, seed_ip: e.target.value })}
                  placeholder="192.168.1.1"
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                />
              </div>

              <div>
                <label htmlFor="seed-community" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  SNMP Community String
                </label>
                <input
                  id="seed-community"
                  type="text"
                  value={seedConfig.snmp_community}
                  onChange={(e) => setSeedConfig({ ...seedConfig, snmp_community: e.target.value })}
                  placeholder="public"
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                />
              </div>

              <div>
                <label htmlFor="seed-device-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Tipo Dispositivo
                </label>
                <select
                  id="seed-device-type"
                  value={seedConfig.device_type}
                  onChange={(e) => setSeedConfig({ ...seedConfig, device_type: e.target.value })}
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                >
                  <option value="huawei">Huawei</option>
                  <option value="cisco">Cisco</option>
                  <option value="extreme">Extreme</option>
                </select>
              </div>

              <div>
                <label htmlFor="seed-max-depth" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Profondita' Massima
                </label>
                <input
                  id="seed-max-depth"
                  type="number"
                  value={seedConfig.max_depth}
                  onChange={(e) => setSeedConfig({ ...seedConfig, max_depth: parseInt(e.target.value) || 1 })}
                  min={1}
                  max={10}
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Numero di livelli LLDP da esplorare (1-10)
                </p>
              </div>
            </div>

            <div>
              <button
                onClick={startSeedDiscovery}
                disabled={seedDiscoveryLoading || !seedConfig.seed_ip.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {seedDiscoveryLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Network className="h-4 w-4" />
                )}
                {seedDiscoveryLoading ? 'Scoperta in corso...' : 'Avvia Seed Discovery'}
              </button>
            </div>

            {/* Seed Discovery Result */}
            {seedDiscoveryResult && (
              <div className={`p-4 rounded-lg ${
                seedDiscoveryResult.status === 'success' ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800' :
                seedDiscoveryResult.status === 'completed_with_errors' ? 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800' :
                'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  {seedDiscoveryResult.status === 'success' ? (
                    <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                  ) : seedDiscoveryResult.status === 'completed_with_errors' ? (
                    <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  )}
                  <p className={`font-medium ${
                    seedDiscoveryResult.status === 'success' ? 'text-green-800 dark:text-green-300' :
                    seedDiscoveryResult.status === 'completed_with_errors' ? 'text-yellow-800 dark:text-yellow-300' :
                    'text-red-800 dark:text-red-300'
                  }`}>
                    {seedDiscoveryResult.message}
                  </p>
                </div>

                {seedDiscoveryResult.seed_switch && (
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Seed switch: <strong>{seedDiscoveryResult.seed_switch}</strong>
                  </p>
                )}

                <div className="mt-2 grid grid-cols-3 gap-4 text-sm">
                  <div className="text-center p-2 bg-white dark:bg-gray-700 rounded">
                    <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{seedDiscoveryResult.switches_discovered}</p>
                    <p className="text-gray-500 dark:text-gray-400">Scoperti</p>
                  </div>
                  <div className="text-center p-2 bg-white dark:bg-gray-700 rounded">
                    <p className="text-2xl font-bold text-green-600 dark:text-green-400">{seedDiscoveryResult.switches_added}</p>
                    <p className="text-gray-500 dark:text-gray-400">Aggiunti</p>
                  </div>
                  <div className="text-center p-2 bg-white dark:bg-gray-700 rounded">
                    <p className="text-2xl font-bold text-gray-600 dark:text-gray-400">{seedDiscoveryResult.switches_already_exist}</p>
                    <p className="text-gray-500 dark:text-gray-400">Esistenti</p>
                  </div>
                </div>

                {seedDiscoveryResult.discovered_switches.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Switch trovati:</p>
                    <div className="max-h-40 overflow-y-auto space-y-1">
                      {seedDiscoveryResult.discovered_switches.map((sw, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs p-2 bg-white dark:bg-gray-700 rounded">
                          {sw.added ? (
                            <CheckCircle className="h-3 w-3 text-green-500 flex-shrink-0" />
                          ) : sw.exists ? (
                            <span className="h-3 w-3 rounded-full bg-gray-400 flex-shrink-0" />
                          ) : (
                            <span className="h-3 w-3 rounded-full bg-yellow-400 flex-shrink-0" />
                          )}
                          <span className="font-mono">{sw.ip || 'N/A'}</span>
                          <span className="text-gray-500">-</span>
                          <span>{sw.hostname || 'Sconosciuto'}</span>
                          {sw.added && <span className="text-green-600 dark:text-green-400 ml-auto">Nuovo</span>}
                          {sw.exists && <span className="text-gray-500 ml-auto">Esistente</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {seedDiscoveryResult.errors.length > 0 && (
                  <div className="mt-3 text-xs text-red-600 dark:text-red-400">
                    <p className="font-medium">Errori:</p>
                    <ul className="list-disc list-inside">
                      {seedDiscoveryResult.errors.map((err, idx) => (
                        <li key={idx}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* NeDi Integration */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <Server className="h-5 w-5 text-orange-600 dark:text-orange-400" />
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              NeDi Integration
            </h2>
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Importa dispositivi e MAC address dal database NeDi (Network Discovery).
            NeDi e' un sistema di discovery di rete esistente che puo' essere usato come fonte dati.
          </p>

          <div className="space-y-4">
            {/* NeDi Status */}
            <div className="flex items-center gap-4">
              <button
                onClick={loadNediStatus}
                disabled={nediStatusLoading}
                className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-50"
              >
                {nediStatusLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Verifica Connessione
              </button>

              <button
                onClick={importFromNedi}
                disabled={nediImportLoading || !nediStatus?.connected}
                className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {nediImportLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Database className="h-4 w-4" />
                )}
                {nediImportLoading ? 'Importazione...' : 'Importa da NeDi'}
              </button>
            </div>

            {/* NeDi Status Display */}
            {nediStatus && (
              <div className={`p-4 rounded-lg border ${
                nediStatus.connected
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                  : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  {nediStatus.connected ? (
                    <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  )}
                  <p className={`font-medium ${
                    nediStatus.connected
                      ? 'text-green-800 dark:text-green-300'
                      : 'text-red-800 dark:text-red-300'
                  }`}>
                    {nediStatus.connected ? 'Connesso a NeDi' : 'Connessione fallita'}
                  </p>
                </div>

                <div className="text-sm text-gray-600 dark:text-gray-400">
                  <p>Host: <span className="font-mono">{nediStatus.host}</span></p>
                  {nediStatus.connected && (
                    <>
                      <p>Dispositivi: <strong>{nediStatus.device_count.toLocaleString()}</strong></p>
                      <p>MAC Address: <strong>{nediStatus.node_count.toLocaleString()}</strong></p>
                      <p>Tabelle: {nediStatus.tables.length}</p>
                    </>
                  )}
                  {nediStatus.error && (
                    <p className="text-red-600 dark:text-red-400 mt-1">Errore: {nediStatus.error}</p>
                  )}
                </div>
              </div>
            )}

            {/* NeDi Import Result */}
            {nediImportResult && (
              <div className={`p-4 rounded-lg border ${
                nediImportResult.success
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                  : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
              }`}>
                <div className="flex items-center gap-2 mb-3">
                  {nediImportResult.success ? (
                    <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  )}
                  <p className={`font-medium ${
                    nediImportResult.success
                      ? 'text-green-800 dark:text-green-300'
                      : 'text-red-800 dark:text-red-300'
                  }`}>
                    {nediImportResult.success ? 'Importazione completata' : 'Importazione fallita'}
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div className="p-3 bg-white dark:bg-gray-700 rounded-lg">
                    <p className="font-medium text-gray-700 dark:text-gray-300 mb-2">Dispositivi</p>
                    <div className="space-y-1 text-xs">
                      <p className="flex justify-between"><span>Creati:</span> <strong className="text-green-600">{nediImportResult.devices.created}</strong></p>
                      <p className="flex justify-between"><span>Aggiornati:</span> <strong className="text-blue-600">{nediImportResult.devices.updated}</strong></p>
                      <p className="flex justify-between"><span>Saltati:</span> <strong className="text-gray-500">{nediImportResult.devices.skipped}</strong></p>
                      <p className="flex justify-between"><span>Errori:</span> <strong className="text-red-600">{nediImportResult.devices.errors}</strong></p>
                    </div>
                  </div>

                  <div className="p-3 bg-white dark:bg-gray-700 rounded-lg">
                    <p className="font-medium text-gray-700 dark:text-gray-300 mb-2">MAC Address</p>
                    <div className="space-y-1 text-xs">
                      <p className="flex justify-between"><span>Creati:</span> <strong className="text-green-600">{nediImportResult.nodes.created}</strong></p>
                      <p className="flex justify-between"><span>Aggiornati:</span> <strong className="text-blue-600">{nediImportResult.nodes.updated}</strong></p>
                      <p className="flex justify-between"><span>Saltati:</span> <strong className="text-gray-500">{nediImportResult.nodes.skipped}</strong></p>
                      <p className="flex justify-between"><span>Errori:</span> <strong className="text-red-600">{nediImportResult.nodes.errors}</strong></p>
                    </div>
                  </div>

                  <div className="p-3 bg-white dark:bg-gray-700 rounded-lg">
                    <p className="font-medium text-gray-700 dark:text-gray-300 mb-2">Link Topologia</p>
                    <div className="space-y-1 text-xs">
                      <p className="flex justify-between"><span>Creati:</span> <strong className="text-green-600">{nediImportResult.links.created}</strong></p>
                      <p className="flex justify-between"><span>Aggiornati:</span> <strong className="text-blue-600">{nediImportResult.links.updated}</strong></p>
                      <p className="flex justify-between"><span>Saltati:</span> <strong className="text-gray-500">{nediImportResult.links.skipped}</strong></p>
                      <p className="flex justify-between"><span>Errori:</span> <strong className="text-red-600">{nediImportResult.links.errors}</strong></p>
                    </div>
                  </div>
                </div>

                {nediImportResult.error && (
                  <p className="mt-3 text-sm text-red-600 dark:text-red-400">
                    Errore: {nediImportResult.error}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* NeDi Sync Scheduler */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <RefreshCw className="h-5 w-5 text-green-600 dark:text-green-400" />
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              NeDi Sync Automatico
            </h2>
            {nediSchedulerStatus?.is_running && (
              <span className="px-2 py-1 text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 rounded-full animate-pulse">
                Sync in corso...
              </span>
            )}
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Sincronizza automaticamente i MAC address dal database NeDi invece di usare il discovery SNMP lento.
            NeDi viene aggiornato ogni pochi minuti e ha dati freschi su tutti i dispositivi.
          </p>

          <div className="space-y-4">
            {/* Scheduler Status */}
            {nediSchedulerStatus && (
              <div className={`p-4 rounded-lg border ${
                nediSchedulerStatus.enabled
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                  : 'bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-600'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {nediSchedulerStatus.enabled ? (
                      <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                    ) : (
                      <XCircle className="h-5 w-5 text-gray-400" />
                    )}
                    <span className={`font-medium ${
                      nediSchedulerStatus.enabled
                        ? 'text-green-800 dark:text-green-300'
                        : 'text-gray-600 dark:text-gray-400'
                    }`}>
                      {nediSchedulerStatus.enabled ? 'Sync Automatico Attivo' : 'Sync Automatico Disattivo'}
                    </span>
                  </div>
                  <button
                    onClick={runNediSyncNow}
                    disabled={nediSyncNowLoading || nediSchedulerStatus.is_running}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {nediSyncNowLoading || nediSchedulerStatus.is_running ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                    Sync Ora
                  </button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Intervallo:</span>
                    <span className="ml-1 font-medium text-gray-900 dark:text-white">{nediSchedulerStatus.interval_minutes} min</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Limite MAC:</span>
                    <span className="ml-1 font-medium text-gray-900 dark:text-white">{nediSchedulerStatus.node_limit.toLocaleString()}</span>
                  </div>
                  {nediSchedulerStatus.last_run && (
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Ultimo sync:</span>
                      <span className="ml-1 font-medium text-gray-900 dark:text-white">{formatDateTime(nediSchedulerStatus.last_run)}</span>
                    </div>
                  )}
                  {nediSchedulerStatus.next_run && (
                    <div>
                      <span className="text-gray-500 dark:text-gray-400">Prossimo:</span>
                      <span className="ml-1 font-medium text-gray-900 dark:text-white">{formatDateTime(nediSchedulerStatus.next_run)}</span>
                    </div>
                  )}
                </div>

                {/* Last result summary */}
                {nediSchedulerStatus.last_result && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-600">
                    <div className="flex items-center gap-2 mb-2">
                      {nediSchedulerStatus.last_result.success ? (
                        <CheckCircle className="h-4 w-4 text-green-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Ultimo risultato: {nediSchedulerStatus.last_result.success ? 'Successo' : 'Errore'}
                      </span>
                    </div>
                    {nediSchedulerStatus.last_result.nodes && (
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        MAC: {nediSchedulerStatus.last_result.nodes.created} creati, {nediSchedulerStatus.last_result.nodes.updated} aggiornati
                        {nediSchedulerStatus.last_result.devices && (
                          <span> | Dispositivi: {nediSchedulerStatus.last_result.devices.created + nediSchedulerStatus.last_result.devices.updated}</span>
                        )}
                      </div>
                    )}
                    {nediSchedulerStatus.last_result.error && (
                      <p className="text-xs text-red-600 dark:text-red-400 mt-1">{nediSchedulerStatus.last_result.error}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Configuration */}
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Configurazione Sync
              </h3>

              <div className="flex items-center gap-3 mb-3">
                <input
                  type="checkbox"
                  id="nedi_sync_enabled"
                  checked={nediSchedulerConfig.enabled}
                  onChange={(e) => setNediSchedulerConfig({ ...nediSchedulerConfig, enabled: e.target.checked })}
                  className="h-4 w-4 text-green-600 rounded"
                />
                <label htmlFor="nedi_sync_enabled" className="text-gray-700 dark:text-gray-300">
                  Abilita sincronizzazione automatica da NeDi
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="nedi-sync-interval" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Intervallo Sync (minuti)
                  </label>
                  <select
                    id="nedi-sync-interval"
                    value={nediSchedulerConfig.interval_minutes}
                    onChange={(e) => setNediSchedulerConfig({ ...nediSchedulerConfig, interval_minutes: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                  >
                    <option value={5}>Ogni 5 minuti</option>
                    <option value={10}>Ogni 10 minuti</option>
                    <option value={15}>Ogni 15 minuti (consigliato)</option>
                    <option value={30}>Ogni 30 minuti</option>
                    <option value={60}>Ogni ora</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="nedi-node-limit" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Limite MAC da sincronizzare
                  </label>
                  <select
                    id="nedi-node-limit"
                    value={nediSchedulerConfig.node_limit}
                    onChange={(e) => setNediSchedulerConfig({ ...nediSchedulerConfig, node_limit: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                  >
                    <option value={50000}>50.000 MAC</option>
                    <option value={100000}>100.000 MAC</option>
                    <option value={200000}>200.000 MAC (consigliato)</option>
                    <option value={500000}>500.000 MAC</option>
                  </select>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-4">
                <button
                  onClick={saveNediSchedulerConfig}
                  disabled={nediSchedulerLoading}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {nediSchedulerLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Salva Configurazione
                </button>
                <button
                  onClick={loadNediSchedulerStatus}
                  disabled={nediSchedulerLoading}
                  className="text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
                >
                  <RefreshCw className={`h-4 w-4 ${nediSchedulerLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Discovery Logs */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              <h2 className="text-lg font-medium text-gray-900 dark:text-white">
                Log Discovery
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={loadDiscoveryLogs}
                disabled={discoveryLogsLoading}
                className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                aria-label="Aggiorna log discovery"
              >
                <RefreshCw className={`h-4 w-4 ${discoveryLogsLoading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={() => setDiscoveryLogsExpanded(!discoveryLogsExpanded)}
                className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                aria-label={discoveryLogsExpanded ? 'Comprimi log' : 'Espandi log'}
              >
                {discoveryLogsExpanded ? (
                  <>
                    <ChevronUp className="h-4 w-4" />
                    Comprimi
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-4 w-4" />
                    Espandi
                  </>
                )}
              </button>
            </div>
          </div>

          {discoveryLogsLoading && discoveryLogs.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-600 dark:text-blue-400" />
              <span className="ml-2 text-gray-600 dark:text-gray-400">Caricamento log...</span>
            </div>
          ) : discoveryLogs.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 italic py-4">
              Nessun log di discovery disponibile. Avvia un discovery per generare log.
            </p>
          ) : (
            <div className={`space-y-2 ${discoveryLogsExpanded ? '' : 'max-h-64'} overflow-y-auto`}>
              {discoveryLogs.slice(0, discoveryLogsExpanded ? discoveryLogs.length : 5).map((log) => (
                <div
                  key={log.id}
                  className={`p-3 rounded-lg border ${
                    log.status === 'success'
                      ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                      : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      {log.status === 'success' ? (
                        <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 flex-shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-600 dark:text-red-400 flex-shrink-0" />
                      )}
                      <div>
                        <p className={`text-sm font-medium ${
                          log.status === 'success'
                            ? 'text-green-800 dark:text-green-300'
                            : 'text-red-800 dark:text-red-300'
                        }`}>
                          {log.switch_hostname || 'Discovery globale'}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {new Date(log.started_at).toLocaleString('it-IT', {
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit'
                          })}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={`text-xs px-2 py-1 rounded ${
                        log.discovery_type === 'snmp'
                          ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                          : 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                      }`}>
                        {log.discovery_type.toUpperCase()}
                      </span>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400">
                    <span>MAC trovati: <strong>{log.mac_count}</strong></span>
                    {log.duration_ms !== null && log.duration_ms !== undefined && (
                      <span>Durata: <strong>{log.duration_ms}ms</strong></span>
                    )}
                  </div>
                  {log.error_message && (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30 p-2 rounded">
                      Errore: {log.error_message}
                    </p>
                  )}
                </div>
              ))}
              {!discoveryLogsExpanded && discoveryLogs.length > 5 && (
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center py-2">
                  Mostrando {5} di {discoveryLogs.length} log. Clicca "Espandi" per vedere tutti.
                </p>
              )}
            </div>
          )}
        </section>

        {/* Data Retention */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <Database className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              Retention Dati
            </h2>
          </div>

          <div>
            <label htmlFor="history-retention" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Retention Storico (giorni)
            </label>
            <input
              id="history-retention"
              type="number"
              value={settings.history_retention_days}
              onChange={(e) => setSettings({ ...settings, history_retention_days: parseInt(e.target.value) })}
              className="w-full max-w-xs px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
              min={30}
              max={365}
            />
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              I dati storici piu' vecchi verranno eliminati automaticamente
            </p>
          </div>
        </section>

        {/* Backup Database */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <HardDrive className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              <h2 className="text-lg font-medium text-gray-900 dark:text-white">
                Backup Database
              </h2>
            </div>
            <button
              onClick={createBackup}
              disabled={backupLoading}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
            >
              {backupLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <HardDrive className="h-4 w-4" />
              )}
              {backupLoading ? 'Backup in corso...' : 'Crea Backup Ora'}
            </button>
          </div>

          {/* Backup message */}
          {backupMessage && (
            <div className={`mb-4 p-3 rounded-lg ${
              backupMessage.type === 'success'
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-300'
            }`}>
              {backupMessage.text}
            </div>
          )}

          <div className="space-y-4">
            {/* Schedule configuration */}
            <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Backup Automatico
              </h3>

              <div className="flex items-center gap-3 mb-3">
                <input
                  type="checkbox"
                  id="backup_enabled"
                  checked={backupConfig.enabled}
                  onChange={(e) => setBackupConfig({ ...backupConfig, enabled: e.target.checked })}
                  className="h-4 w-4 text-blue-600 rounded"
                />
                <label htmlFor="backup_enabled" className="text-gray-700 dark:text-gray-300">
                  Abilita backup automatico
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="backup-interval" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Intervallo (ore)
                  </label>
                  <select
                    id="backup-interval"
                    value={backupConfig.interval_hours}
                    onChange={(e) => setBackupConfig({ ...backupConfig, interval_hours: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                  >
                    <option value={6}>Ogni 6 ore</option>
                    <option value={12}>Ogni 12 ore</option>
                    <option value={24}>Giornaliero (24 ore)</option>
                    <option value={48}>Ogni 2 giorni</option>
                    <option value={168}>Settimanale</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="backup-time" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Orario backup giornaliero
                  </label>
                  <input
                    id="backup-time"
                    type="time"
                    value={backupConfig.time}
                    onChange={(e) => setBackupConfig({ ...backupConfig, time: e.target.value })}
                    className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                  />
                </div>
              </div>

              <div className="mt-3 flex items-center gap-4">
                <button
                  onClick={saveBackupConfig}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                >
                  Salva Configurazione
                </button>
                {backupScheduler?.next_scheduled_backup && (
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Prossimo backup: {formatDateTime(backupScheduler.next_scheduled_backup)}
                  </span>
                )}
              </div>
            </div>

            {/* Backup list */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Backup Disponibili ({backups.length})
                </h3>
                <button
                  onClick={loadBackupData}
                  className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                  aria-label="Aggiorna lista backup"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
              </div>

              {backups.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 italic">
                  Nessun backup disponibile. Crea il primo backup cliccando il pulsante sopra.
                </p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {backups.map((backup) => (
                    <div
                      key={backup.filename}
                      className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white font-mono">
                          {backup.filename}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {formatDateTime(backup.created_at)} • {backup.size_formatted}
                        </p>
                      </div>
                      <button
                        onClick={() => deleteBackup(backup.filename)}
                        className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 p-1"
                        aria-label={`Elimina backup ${backup.filename}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Alert Settings */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center gap-3 mb-4">
            <BellIcon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              Alert
            </h2>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="alert_new_mac"
                checked={settings.alert_new_mac}
                onChange={(e) => setSettings({ ...settings, alert_new_mac: e.target.checked })}
                className="h-4 w-4 text-blue-600 rounded"
              />
              <label htmlFor="alert_new_mac" className="text-gray-700 dark:text-gray-300">
                Alert per nuovo MAC (mai visto prima)
              </label>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="alert_mac_move"
                checked={settings.alert_mac_move}
                onChange={(e) => setSettings({ ...settings, alert_mac_move: e.target.checked })}
                className="h-4 w-4 text-blue-600 rounded"
              />
              <label htmlFor="alert_mac_move" className="text-gray-700 dark:text-gray-300">
                Alert per movimento MAC (cambio porta)
              </label>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="alert_mac_disappear"
                checked={settings.alert_mac_disappear}
                onChange={(e) => setSettings({ ...settings, alert_mac_disappear: e.target.checked })}
                className="h-4 w-4 text-blue-600 rounded"
              />
              <label htmlFor="alert_mac_disappear" className="text-gray-700 dark:text-gray-300">
                Alert per MAC scomparso
              </label>
            </div>

            <div>
              <label htmlFor="alert-disappear-hours" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Soglia scomparsa (ore)
              </label>
              <input
                id="alert-disappear-hours"
                type="number"
                value={settings.alert_disappear_hours}
                onChange={(e) => setSettings({ ...settings, alert_disappear_hours: parseInt(e.target.value) })}
                className="w-full max-w-xs px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                min={1}
                max={168}
              />
            </div>

            <div>
              <label htmlFor="alert-port-threshold" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Soglia MAC per porta (warning uplink)
              </label>
              <input
                id="alert-port-threshold"
                type="number"
                value={settings.alert_port_threshold}
                onChange={(e) => setSettings({ ...settings, alert_port_threshold: parseInt(e.target.value) })}
                className="w-full max-w-xs px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
                min={2}
                max={100}
              />
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Alert se una porta ha piu' di N MAC (possibile uplink non mappato)
              </p>
            </div>
          </div>
        </section>

        {/* Telegram Settings */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <svg className="h-5 w-5 text-blue-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.359 8.627-.168.9-.5 1.201-.82 1.23-.697.064-1.226-.461-1.901-.903-1.056-.692-1.653-1.123-2.678-1.799-1.185-.781-.417-1.21.258-1.911.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.139-5.062 3.345-.479.329-.913.489-1.302.481-.428-.009-1.252-.242-1.865-.442-.751-.244-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.015 3.333-1.386 4.025-1.627 4.477-1.635.099-.002.321.023.465.141.121.099.154.232.17.325.015.094.034.31.019.479z"/>
              </svg>
              <h2 className="text-lg font-medium text-gray-900 dark:text-white">
                Telegram
              </h2>
            </div>
            <button
              onClick={testTelegram}
              disabled={telegramLoading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors text-sm disabled:opacity-50"
            >
              {telegramLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {telegramLoading ? 'Invio...' : 'Test Notifica'}
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label htmlFor="telegram_bot_token" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Bot Token
              </label>
              <input
                id="telegram_bot_token"
                type="password"
                value={settings.telegram_bot_token}
                onChange={(e) => setSettings({ ...settings, telegram_bot_token: e.target.value })}
                placeholder="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
                className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label htmlFor="telegram_chat_id" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Chat ID
              </label>
              <input
                id="telegram_chat_id"
                type="text"
                value={settings.telegram_chat_id}
                onChange={(e) => setSettings({ ...settings, telegram_chat_id: e.target.value })}
                placeholder="-1001234567890"
                className="w-full max-w-xs px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white"
              />
            </div>

            {/* Telegram Test Result */}
            {telegramResult && (
              <div className={`p-4 rounded-lg ${
                telegramResult.success
                  ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                  : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
              }`}>
                <div className="flex items-center gap-2">
                  {telegramResult.success ? (
                    <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  )}
                  <p className={`font-medium ${
                    telegramResult.success
                      ? 'text-green-800 dark:text-green-300'
                      : 'text-red-800 dark:text-red-300'
                  }`}>
                    {telegramResult.message}
                  </p>
                </div>
                {telegramResult.details && (
                  <p className={`mt-1 text-sm ${
                    telegramResult.success
                      ? 'text-green-700 dark:text-green-400'
                      : 'text-red-700 dark:text-red-400'
                  }`}>
                    {telegramResult.details}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
