import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Edit, Trash2, AlertCircle, RefreshCw } from 'lucide-react'
import { switchesApi, Switch, Port, SwitchMac } from '../api/client'

export default function SwitchDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [switchData, setSwitchData] = useState<Switch | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [activeTab, setActiveTab] = useState<'ports' | 'macs'>('ports')
  const [ports, setPorts] = useState<Port[]>([])
  const [portsLoading, setPortsLoading] = useState(false)
  const [portsError, setPortsError] = useState('')
  const [macs, setMacs] = useState<SwitchMac[]>([])
  const [macsLoading, setMacsLoading] = useState(false)
  const [macsError, setMacsError] = useState('')

  const loadSwitch = async (switchId: number) => {
    try {
      const response = await switchesApi.get(switchId)
      setSwitchData(response.data)
    } catch (err: any) {
      setError(err.userMessage || 'Switch non trovato')
    } finally {
      setLoading(false)
    }
  }

  const loadPorts = async (switchId: number) => {
    setPortsLoading(true)
    setPortsError('')
    try {
      const response = await switchesApi.getPorts(switchId)
      setPorts(response.data.items)
    } catch (err: any) {
      setPortsError(err.userMessage || 'Errore nel caricamento delle porte')
    } finally {
      setPortsLoading(false)
    }
  }

  const loadMacs = async (switchId: number) => {
    setMacsLoading(true)
    setMacsError('')
    try {
      const response = await switchesApi.getMacs(switchId)
      setMacs(response.data.macs)
    } catch (err: any) {
      setMacsError(err.userMessage || 'Errore nel caricamento dei MAC')
    } finally {
      setMacsLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      const switchId = parseInt(id)
      loadSwitch(switchId)
      loadPorts(switchId)
      loadMacs(switchId)
    }
  }, [id])

  const handleDelete = async () => {
    if (!switchData) return
    setDeleting(true)
    try {
      await switchesApi.delete(switchData.id)
      navigate('/switches')
    } catch (err: any) {
      setError(err.userMessage || 'Errore nella eliminazione')
      setDeleting(false)
    }
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '--'
    return new Date(dateStr).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error || !switchData) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="h-12 w-12 mx-auto text-red-500 mb-4" />
        <p className="text-red-500 dark:text-red-400">{error || 'Switch non trovato'}</p>
        <Link to="/switches" className="text-blue-600 hover:underline mt-4 inline-block">
          Torna alla lista switch
        </Link>
      </div>
    )
  }

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="mb-4 text-sm">
        <ol className="flex items-center gap-2">
          <li>
            <Link to="/" className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
              Home
            </Link>
          </li>
          <li className="text-gray-400">/</li>
          <li>
            <Link to="/switches" className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
              Switch
            </Link>
          </li>
          <li className="text-gray-400">/</li>
          <li className="text-gray-900 dark:text-white font-medium">
            {switchData.hostname}
          </li>
        </ol>
      </nav>

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link
            to="/switches"
            className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            aria-label="Torna alla lista switch"
            title="Torna alla lista"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
              {switchData.hostname}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">
              {switchData.ip_address}
            </p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            switchData.is_active
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400'
          }`}>
            {switchData.is_active ? 'Attivo' : 'Inattivo'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {deleteConfirm ? (
            <>
              <span className="text-sm text-red-600 dark:text-red-400 mr-2">Confermi eliminazione?</span>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? 'Eliminazione...' : 'Si, elimina'}
              </button>
              <button
                onClick={() => setDeleteConfirm(false)}
                className="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-400"
              >
                Annulla
              </button>
            </>
          ) : (
            <>
              <Link
                to={`/switches`}
                state={{ editSwitch: switchData }}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Edit className="h-4 w-4" />
                Modifica
              </Link>
              <button
                onClick={() => setDeleteConfirm(true)}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
                Elimina
              </button>
            </>
          )}
        </div>
      </div>

      {/* Switch Info */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Informazioni Switch
          </h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Hostname</dt>
              <dd className="text-gray-900 dark:text-white font-medium">{switchData.hostname}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">IP Address</dt>
              <dd className="text-gray-900 dark:text-white font-mono">{switchData.ip_address}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Tipo</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.device_type}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Modello</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.model || '--'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Serial Number</dt>
              <dd className="text-gray-900 dark:text-white font-mono">{switchData.serial_number || '--'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">sysName (SNMP)</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.sys_name || '--'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Location</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.location || '--'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Gruppo</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.group?.name || '--'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">SNMP Community</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.snmp_community || '--'}</dd>
            </div>
          </dl>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Statistiche & Date
          </h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">MAC Connessi</dt>
              <dd className="text-gray-900 dark:text-white font-medium text-lg">{switchData.mac_count}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">VLAN Attive</dt>
              <dd className="text-gray-900 dark:text-white">{switchData.vlan_count ?? '--'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Porte Up / Down</dt>
              <dd className="text-gray-900 dark:text-white">
                {switchData.ports_up_count !== undefined ? (
                  <span>
                    <span className="text-green-600 dark:text-green-400">{switchData.ports_up_count} up</span>
                    {' / '}
                    <span className="text-red-600 dark:text-red-400">{switchData.ports_down_count ?? 0} down</span>
                  </span>
                ) : '--'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Creato il</dt>
              <dd className="text-gray-900 dark:text-white">{formatDate(switchData.created_at)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Ultimo Discovery</dt>
              <dd className="text-gray-900 dark:text-white">{formatDate(switchData.last_discovery)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Ultimo Contatto</dt>
              <dd className="text-gray-900 dark:text-white">{formatDate(switchData.last_seen)}</dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Tabs: Ports / MACs */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex gap-4 px-6">
            <button
              onClick={() => setActiveTab('ports')}
              className={`py-4 px-2 border-b-2 font-medium transition-colors ${
                activeTab === 'ports'
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              Porte {ports.length > 0 && `(${ports.length})`}
            </button>
            <button
              onClick={() => setActiveTab('macs')}
              className={`py-4 px-2 border-b-2 font-medium transition-colors ${
                activeTab === 'macs'
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              MAC Connessi {macs.length > 0 && `(${macs.length})`}
            </button>
          </nav>
        </div>
        <div className="p-6">
          {activeTab === 'ports' && (
            <>
              {portsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin text-blue-600" />
                  <span className="ml-2 text-gray-500 dark:text-gray-400">Caricamento porte...</span>
                </div>
              ) : portsError ? (
                <div className="text-center py-8">
                  <AlertCircle className="h-8 w-8 mx-auto text-red-500 mb-2" />
                  <p className="text-red-500 dark:text-red-400">{portsError}</p>
                  <button
                    onClick={() => id && loadPorts(parseInt(id))}
                    className="mt-4 px-4 py-2 text-blue-600 hover:underline"
                  >
                    Riprova
                  </button>
                </div>
              ) : ports.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                  Nessuna porta trovata. Esegui un discovery per popolare le porte.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-700">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Nome Porta
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Tipo
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          VLAN
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Stato Admin
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Stato Operativo
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Velocità
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Uplink
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          MAC Count
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Descrizione
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                      {ports.map((port) => {
                        // Calculate live MAC count from the macs array
                        const macCount = macs.filter(m => m.port_name === port.port_name).length
                        return (
                        <tr key={port.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-white">
                            {port.port_name}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              port.port_type === 'uplink'
                                ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400'
                                : port.port_type === 'trunk'
                                ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                                : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                            }`}>
                              {port.port_type}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                            {port.vlan_id || '--'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              port.admin_status === 'up'
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                            }`}>
                              {port.admin_status}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              port.oper_status === 'up'
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                            }`}>
                              {port.oper_status}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                            {port.speed || '--'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            {port.is_uplink ? (
                              <span className="text-purple-600 dark:text-purple-400 font-medium">Sì</span>
                            ) : (
                              <span className="text-gray-500 dark:text-gray-400">No</span>
                            )}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            {macCount > 1 ? (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400" title="Porta con MAC multipli - possibile uplink o hub">
                                <AlertCircle className="h-3 w-3" />
                                {macCount}
                              </span>
                            ) : (
                              <span className="text-gray-900 dark:text-gray-300">
                                {macCount}
                              </span>
                            )}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-xs truncate">
                            {port.port_description || '--'}
                          </td>
                        </tr>
                      )})}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          {activeTab === 'macs' && (
            <>
              {macsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-6 w-6 animate-spin text-blue-600" />
                  <span className="ml-2 text-gray-500 dark:text-gray-400">Caricamento MAC...</span>
                </div>
              ) : macsError ? (
                <div className="text-center py-8">
                  <AlertCircle className="h-8 w-8 mx-auto text-red-500 mb-2" />
                  <p className="text-red-500 dark:text-red-400">{macsError}</p>
                  <button
                    onClick={() => id && loadMacs(parseInt(id))}
                    className="mt-4 px-4 py-2 text-blue-600 hover:underline"
                  >
                    Riprova
                  </button>
                </div>
              ) : macs.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                  Nessun MAC connesso trovato. Esegui un discovery per popolare i dati.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-700">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          MAC Address
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          IP
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Porta
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          VLAN
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Vendor
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                          Ultimo Avvistamento
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                      {macs.map((mac, idx) => (
                        <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-blue-600 dark:text-blue-400">
                            {mac.mac_address}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-gray-300">
                            {mac.ip_address || '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-white">
                            {mac.port_name}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-300">
                            {mac.vlan_id || '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                            {mac.vendor_name || '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                            {formatDate(mac.last_seen)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
