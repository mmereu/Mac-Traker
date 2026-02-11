import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Server, X, Trash2, Edit, Loader2, ChevronLeft, ChevronRight, Search, Filter } from 'lucide-react'
import { switchesApi, groupsApi, type Switch, type SwitchCreate, type SwitchGroup, type DeleteResult, type SiteCodeInfo } from '../api/client'
import { ConfirmDeleteModal } from '../components/ConfirmDeleteModal'
import { ConfirmDeleteAllModal } from '../components/ConfirmDeleteAllModal'
import { toast } from 'react-hot-toast'

// Validation helper
const isValidIPAddress = (ip: string): boolean => {
  if (!ip) return false
  const parts = ip.split('.')
  if (parts.length !== 4) return false
  return parts.every(part => {
    const num = parseInt(part, 10)
    return !isNaN(num) && num >= 0 && num <= 255 && part === num.toString()
  })
}

interface FormErrors {
  hostname?: string
  ip_address?: string
  snmp_community?: string
}

const ITEMS_PER_PAGE = 10

export default function SwitchList() {
  const [switches, setSwitches] = useState<Switch[]>([])
  const [groups, setGroups] = useState<SwitchGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [editingSwitch, setEditingSwitch] = useState<Switch | null>(null)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  // Bulk delete states
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [isDeleteAllModalOpen, setIsDeleteAllModalOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [totalItems, setTotalItems] = useState(0)

  // Filter state
  const [filterSearch, setFilterSearch] = useState('')
  const [filterDeviceType, setFilterDeviceType] = useState('')
  const [filterGroupId, setFilterGroupId] = useState<number | undefined>(undefined)
  const [filterSiteCode, setFilterSiteCode] = useState('')
  const [siteCodes, setSiteCodes] = useState<SiteCodeInfo[]>([])

  const [formData, setFormData] = useState<SwitchCreate>({
    hostname: '',
    ip_address: '',
    device_type: '',
    snmp_community: 'public',
    group_id: undefined,
    location: '',
  })

  const fetchSwitches = useCallback(async (page: number = currentPage) => {
    try {
      setLoading(true)
      const skip = (page - 1) * ITEMS_PER_PAGE
      const response = await switchesApi.list({
        skip,
        limit: ITEMS_PER_PAGE,
        search: filterSearch || undefined,
        device_type: filterDeviceType || undefined,
        group_id: filterGroupId,
        site_code: filterSiteCode || undefined,
      })
      setSwitches(response.data.items)
      setTotalItems(response.data.total)
    } catch (err) {
      console.error('Errore nel caricamento switch:', err)
    } finally {
      setLoading(false)
    }
  }, [currentPage, filterSearch, filterDeviceType, filterGroupId, filterSiteCode])

  const fetchSiteCodes = async () => {
    try {
      const response = await switchesApi.getSiteCodes()
      setSiteCodes(response.data)
    } catch (err) {
      console.error('Errore nel caricamento site codes:', err)
    }
  }

  const fetchGroups = async () => {
    try {
      const response = await groupsApi.list()
      setGroups(response.data.items)
    } catch (err) {
      console.error('Errore nel caricamento gruppi:', err)
    }
  }

  // Fetch switches when page or filters change
  useEffect(() => {
    fetchSwitches(currentPage)
  }, [currentPage, filterSearch, filterDeviceType, filterGroupId, filterSiteCode])

  // Fetch groups and site codes on mount
  useEffect(() => {
    fetchGroups()
    fetchSiteCodes()
  }, [])

  // Calculate pagination info
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE)

  // Handler to change page
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage)
    }
  }

  // Handler for filter changes - RESET PAGINATION TO PAGE 1
  const handleFilterSearchChange = (value: string) => {
    setFilterSearch(value)
    setCurrentPage(1) // Reset pagination when filter changes
  }

  const handleFilterDeviceTypeChange = (value: string) => {
    setFilterDeviceType(value)
    setCurrentPage(1) // Reset pagination when filter changes
  }

  const handleFilterGroupChange = (value: string) => {
    setFilterGroupId(value ? parseInt(value) : undefined)
    setCurrentPage(1) // Reset pagination when filter changes
  }

  const handleFilterSiteCodeChange = (value: string) => {
    setFilterSiteCode(value)
    setCurrentPage(1) // Reset pagination when filter changes
  }

  const clearFilters = () => {
    setFilterSearch('')
    setFilterDeviceType('')
    setFilterGroupId(undefined)
    setFilterSiteCode('')
    setCurrentPage(1) // Reset pagination when filters are cleared
  }

  const resetForm = () => {
    setFormData({
      hostname: '',
      ip_address: '',
      device_type: '',
      snmp_community: 'public',
      group_id: undefined,
      location: '',
    })
    setEditingSwitch(null)
    setError(null)
    setFormErrors({})
    setTouched({})
  }

  // Validate form and return errors
  const validateForm = (): FormErrors => {
    const errors: FormErrors = {}

    if (!formData.hostname.trim()) {
      errors.hostname = 'Hostname è obbligatorio'
    }

    if (!formData.ip_address.trim()) {
      errors.ip_address = 'Indirizzo IP è obbligatorio'
    } else if (!isValidIPAddress(formData.ip_address.trim())) {
      errors.ip_address = 'Formato IP non valido (es. 192.168.1.1)'
    }

    if (!formData.snmp_community || !formData.snmp_community.trim()) {
      errors.snmp_community = 'SNMP Community è obbligatoria'
    }

    return errors
  }

  // Handle field blur to show errors on touch
  const handleBlur = (field: string) => {
    setTouched(prev => ({ ...prev, [field]: true }))
    setFormErrors(validateForm())
  }

  const openAddModal = () => {
    resetForm()
    setShowModal(true)
  }

  const openEditModal = (sw: Switch) => {
    setFormData({
      hostname: sw.hostname,
      ip_address: sw.ip_address,
      device_type: sw.device_type,
      snmp_community: sw.snmp_community || '',
      group_id: sw.group_id,
      location: sw.location || '',
    })
    setEditingSwitch(sw)
    setShowModal(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Mark all fields as touched to show all errors
    setTouched({ hostname: true, ip_address: true, snmp_community: true })

    // Validate form
    const errors = validateForm()
    setFormErrors(errors)

    // If there are errors, don't submit
    if (Object.keys(errors).length > 0) {
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      // Build clean object, only include non-empty values
      const dataToSend: any = {
        hostname: formData.hostname.trim(),
        ip_address: formData.ip_address.trim(),
        device_type: formData.device_type || 'huawei',
      }

      // Only add optional fields if they have values
      if (formData.snmp_community && formData.snmp_community.trim()) {
        dataToSend.snmp_community = formData.snmp_community.trim()
      }
      if (formData.group_id) {
        dataToSend.group_id = formData.group_id
      }
      if (formData.location && formData.location.trim()) {
        dataToSend.location = formData.location.trim()
      }

      if (editingSwitch) {
        await switchesApi.update(editingSwitch.id, dataToSend)
        toast.success(`Switch "${formData.hostname}" aggiornato con successo`)
      } else {
        await switchesApi.create(dataToSend)
        toast.success(`Switch "${formData.hostname}" creato con successo`)
      }

      setShowModal(false)
      resetForm()
      fetchSwitches()

      // Clear success message after 3 seconds
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err: any) {
      // Use user-friendly message from API interceptor
      setError(err.userMessage || 'Errore durante il salvataggio')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (sw: Switch) => {
    if (!confirm(`Sei sicuro di voler eliminare lo switch "${sw.hostname}"?`)) {
      return
    }

    try {
      await switchesApi.delete(sw.id)
      toast.success(`Switch "${sw.hostname}" eliminato con successo`)
      fetchSwitches()
    } catch (err: any) {
      toast.error(err.userMessage || 'Errore durante l\'eliminazione')
    }
  }

  // Bulk delete handlers
  const toggleSelect = (id: number) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(switchId => switchId !== id) : [...prev, id]
    )
  }

  const toggleSelectAll = () => {
    if (selectedIds.length === switches.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(switches.map(sw => sw.id))
    }
  }

  const clearSelection = () => {
    setSelectedIds([])
  }

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return

    setIsDeleting(true)
    try {
      const result = await switchesApi.deleteSwitchesBulk(selectedIds)
      toast.success(`${result.deleted_count} switch eliminati con successo`)
      setIsDeleteModalOpen(false)
      setSelectedIds([])
      fetchSwitches()
    } catch (err: any) {
      toast.error(err.userMessage || 'Errore durante l\'eliminazione in bulk')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleDeleteAll = async () => {
    setIsDeleting(true)
    try {
      const result = await switchesApi.deleteAllSwitches()
      toast.success(`${result.deleted_count} switch eliminati con successo`)
      setIsDeleteAllModalOpen(false)
      fetchSwitches()
    } catch (err: any) {
      toast.error(err.userMessage || 'Errore durante l\'eliminazione di tutti gli switch')
    } finally {
      setIsDeleting(false)
    }
  }

  // Check if all switches on current page are selected
  const allCurrentSelected = switches.length > 0 && selectedIds.length === switches.length
  const someCurrentSelected = selectedIds.length > 0 && selectedIds.length < switches.length

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Gestione Switch
        </h1>
        <button
          onClick={openAddModal}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Aggiungi Switch
        </button>
      </div>

      {/* Bulk delete toolbar */}
      {selectedIds.length > 0 && (
        <div className="mb-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg shadow-md border border-blue-200 dark:border-blue-800/30 animate-fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                {selectedIds.length} {selectedIds.length === 1 ? 'switch' : 'switch'} selezionati
              </span>
              <button
                onClick={clearSelection}
                className="text-sm text-gray-600 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
              >
                <X className="h-4 w-4 inline mr-1" />
                Deseleziona
              </button>
            </div>
            <button
              onClick={() => setIsDeleteModalOpen(true)}
              disabled={isDeleting}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Trash2 className="h-4 w-4" />
              Elimina Selezionati
            </button>
          </div>
        </div>
      )}

      {/* Delete all button */}
      {totalItems > 0 && (
        <div className="mb-4 flex justify-end">
          <button
            onClick={() => setIsDeleteAllModalOpen(true)}
            disabled={isDeleting}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Trash2 className="h-4 w-4" />
            Elimina Tutti
          </button>
        </div>
      )}

      {/* Success Message */}
      {successMessage && (
        <div className="mb-4 p-4 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 rounded-lg">
          {successMessage}
        </div>
      )}

      {/* Error Message (outside modal, for delete errors etc.) */}
      {error && !showModal && (
        <div className="mb-4 p-4 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 p-4 bg-white dark:bg-gray-800 rounded-lg shadow">
        <div className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-[200px]">
            <label htmlFor="filter-search" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              <Search className="inline h-4 w-4 mr-1" />
              Cerca
            </label>
            <input
              id="filter-search"
              type="text"
              value={filterSearch}
              onChange={(e) => handleFilterSearchChange(e.target.value)}
              placeholder="Hostname, IP, posizione..."
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="min-w-[150px]">
            <label htmlFor="filter-device-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              <Filter className="inline h-4 w-4 mr-1" />
              Tipo
            </label>
            <select
              id="filter-device-type"
              value={filterDeviceType}
              onChange={(e) => handleFilterDeviceTypeChange(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Tutti i tipi</option>
              <option value="huawei">Huawei</option>
              <option value="cisco">Cisco</option>
              <option value="extreme">Extreme</option>
            </select>
          </div>
          <div className="min-w-[150px]">
            <label htmlFor="filter-group" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Gruppo
            </label>
            <select
              id="filter-group"
              value={filterGroupId || ''}
              onChange={(e) => handleFilterGroupChange(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Tutti i gruppi</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div className="min-w-[150px]">
            <label htmlFor="filter-site-code" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Sede
            </label>
            <select
              id="filter-site-code"
              value={filterSiteCode}
              onChange={(e) => handleFilterSiteCodeChange(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Tutte le sedi</option>
              {siteCodes.map((s) => (
                <option key={s.code} value={s.code}>Sede {s.code} ({s.count})</option>
              ))}
            </select>
          </div>
          {(filterSearch || filterDeviceType || filterGroupId || filterSiteCode) && (
            <button
              onClick={clearFilters}
              className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <X className="inline h-4 w-4 mr-1" />
              Cancella filtri
            </button>
          )}
        </div>
        {totalItems > 0 && (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            Trovati <strong>{totalItems}</strong> switch
            {totalPages > 1 && ` • Pagina ${currentPage} di ${totalPages}`}
          </div>
        )}
      </div>

      {/* Switch List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-x-auto">
        {loading ? (
          <div className="p-12 text-center text-gray-500 dark:text-gray-400">
            <Loader2 className="h-8 w-8 mx-auto mb-4 animate-spin" />
            <p>Caricamento...</p>
          </div>
        ) : switches.length === 0 ? (
          <div className="p-12 text-center text-gray-500 dark:text-gray-400">
            <Server className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Nessuno switch configurato</p>
            <p className="text-sm mt-2">Aggiungi il primo switch per iniziare</p>
          </div>
        ) : (
          <table className="w-full min-w-[750px]">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <input
                    type="checkbox"
                    checked={allCurrentSelected}
                    onChange={toggleSelectAll}
                    className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                  />
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Hostname
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  IP Address
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Tipo
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Gruppo
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Sede
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Stato
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  MAC Count
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Azioni
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {switches.map((sw) => (
                <tr
                  key={sw.id}
                  className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${
                    selectedIds.includes(sw.id) ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                  }`}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(sw.id)}
                      onChange={() => toggleSelect(sw.id)}
                      className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                    />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <Link to={`/switches/${sw.id}`} className="text-blue-600 dark:text-blue-400 hover:underline font-medium">
                      {sw.hostname}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap font-mono text-sm text-gray-900 dark:text-gray-100">
                    {sw.ip_address}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap capitalize text-gray-700 dark:text-gray-300">
                    {sw.device_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-gray-700 dark:text-gray-300">
                    {sw.group?.name || '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-gray-700 dark:text-gray-300">
                    {sw.site_code ? `Sede ${sw.site_code}` : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs rounded-full ${sw.is_active ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'}`}>
                      {sw.is_active ? 'Attivo' : 'Inattivo'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-gray-700 dark:text-gray-300">
                    {sw.mac_count || 0}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEditModal(sw)}
                        className="p-1 text-gray-500 hover:text-blue-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                        aria-label={`Modifica switch ${sw.hostname}`}
                        title="Modifica"
                      >
                        <Edit className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(sw)}
                        className="p-1 text-gray-500 hover:text-red-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                        aria-label={`Elimina switch ${sw.hostname}`}
                        title="Elimina"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && !loading && (
        <div className="mt-4 flex items-center justify-between">
          <div className="text-sm text-gray-500 dark:text-gray-400">
            Mostrando {((currentPage - 1) * ITEMS_PER_PAGE) + 1} - {Math.min(currentPage * ITEMS_PER_PAGE, totalItems)} di {totalItems} switch
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Pagina precedente"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-1">
              {/* Generate page buttons */}
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(page => {
                  // Show first, last, current, and neighbors
                  if (page === 1 || page === totalPages) return true
                  if (Math.abs(page - currentPage) <= 1) return true
                  return false
                })
                .reduce<(number | string)[]>((acc, page, idx, arr) => {
                  // Add ellipsis between gaps
                  if (idx > 0 && typeof arr[idx - 1] === 'number' && page - (arr[idx - 1] as number) > 1) {
                    acc.push('...')
                  }
                  acc.push(page)
                  return acc
                }, [])
                .map((item, idx) =>
                  item === '...' ? (
                    <span key={`ellipsis-${idx}`} className="px-2 text-gray-400">...</span>
                  ) : (
                    <button
                      key={item}
                      onClick={() => handlePageChange(item as number)}
                      className={`px-3 py-1 rounded-lg text-sm ${
                        currentPage === item
                          ? 'bg-blue-600 text-white'
                          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                      }`}
                      aria-label={`Pagina ${item}`}
                      aria-current={currentPage === item ? 'page' : undefined}
                    >
                      {item}
                    </button>
                  )
                )}
            </div>
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Pagina successiva"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      {/* Modal Form */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between p-4 border-b dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editingSwitch ? 'Modifica Switch' : 'Nuovo Switch'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                aria-label="Chiudi finestra"
                title="Chiudi"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              {error && (
                <div className="p-3 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label htmlFor="switch-hostname" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Hostname *
                </label>
                <input
                  id="switch-hostname"
                  type="text"
                  value={formData.hostname}
                  onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                  onBlur={() => handleBlur('hostname')}
                  className={`w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                    touched.hostname && formErrors.hostname ? 'border-red-500 dark:border-red-500' : ''
                  }`}
                  placeholder="es. SW-CORE-01"
                />
                {touched.hostname && formErrors.hostname && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">{formErrors.hostname}</p>
                )}
              </div>

              <div>
                <label htmlFor="switch-ip-address" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Indirizzo IP *
                </label>
                <input
                  id="switch-ip-address"
                  type="text"
                  value={formData.ip_address}
                  onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                  onBlur={() => handleBlur('ip_address')}
                  className={`w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                    touched.ip_address && formErrors.ip_address ? 'border-red-500 dark:border-red-500' : ''
                  }`}
                  placeholder="es. 192.168.1.1"
                />
                {touched.ip_address && formErrors.ip_address && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">{formErrors.ip_address}</p>
                )}
              </div>

              <div>
                <label htmlFor="switch-device-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Tipo Dispositivo
                </label>
                <select
                  id="switch-device-type"
                  value={formData.device_type}
                  onChange={(e) => setFormData({ ...formData, device_type: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="" disabled>Seleziona tipo...</option>
                  <option value="huawei">Huawei</option>
                  <option value="cisco">Cisco</option>
                  <option value="extreme">Extreme</option>
                </select>
              </div>

              <div>
                <label htmlFor="switch-snmp-community" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  SNMP Community *
                </label>
                <input
                  id="switch-snmp-community"
                  type="text"
                  value={formData.snmp_community}
                  onChange={(e) => setFormData({ ...formData, snmp_community: e.target.value })}
                  onBlur={() => handleBlur('snmp_community')}
                  className={`w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                    touched.snmp_community && formErrors.snmp_community ? 'border-red-500 dark:border-red-500' : ''
                  }`}
                  placeholder="es. public"
                />
                {touched.snmp_community && formErrors.snmp_community && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">{formErrors.snmp_community}</p>
                )}
              </div>

              <div>
                <label htmlFor="switch-group" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Gruppo
                </label>
                <select
                  id="switch-group"
                  value={formData.group_id || ''}
                  onChange={(e) => setFormData({ ...formData, group_id: e.target.value ? parseInt(e.target.value) : undefined })}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">Nessun gruppo</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="switch-location" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Posizione
                </label>
                <input
                  id="switch-location"
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="es. Sala Server Piano 1"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {editingSwitch ? 'Salva' : 'Crea'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Modal */}
      <ConfirmDeleteModal
        isOpen={isDeleteModalOpen}
        onConfirm={handleBulkDelete}
        onCancel={() => setIsDeleteModalOpen(false)}
        count={selectedIds.length}
        type="selected"
        isLoading={isDeleting}
      />

      {/* Delete All Modal */}
      <ConfirmDeleteAllModal
        isOpen={isDeleteAllModalOpen}
        onConfirm={handleDeleteAll}
        onCancel={() => setIsDeleteAllModalOpen(false)}
        count={totalItems}
        isLoading={isDeleting}
      />
    </div>
  )
}