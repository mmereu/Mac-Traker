import { useState, useEffect } from 'react'
import { Plus, FolderCog, Edit, Trash2, X, AlertCircle, CheckCircle } from 'lucide-react'
import { groupsApi, SwitchGroup, SwitchGroupCreate } from '../api/client'

interface FormErrors {
  name?: string
  ssh_port?: string
}

export default function Groups() {
  const [groups, setGroups] = useState<SwitchGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingGroup, setEditingGroup] = useState<SwitchGroup | null>(null)
  const [formData, setFormData] = useState<SwitchGroupCreate>({
    name: '',
    description: '',
    ssh_username: '',
    ssh_password: '',
    ssh_port: 22,
  })
  const [saving, setSaving] = useState(false)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<{ name?: boolean; ssh_port?: boolean }>({})

  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      const response = await groupsApi.list()
      setGroups(response.data.items)
    } catch (err: any) {
      setError(err.userMessage || 'Errore nel caricamento dei gruppi')
    } finally {
      setLoading(false)
    }
  }

  const validateForm = (): FormErrors => {
    const errors: FormErrors = {}
    if (!formData.name?.trim()) {
      errors.name = 'Nome gruppo è obbligatorio'
    }
    if (formData.ssh_port && (formData.ssh_port < 1 || formData.ssh_port > 65535)) {
      errors.ssh_port = 'Porta SSH deve essere tra 1 e 65535'
    }
    return errors
  }

  const openCreateModal = () => {
    setEditingGroup(null)
    setFormData({
      name: '',
      description: '',
      ssh_username: '',
      ssh_password: '',
      ssh_port: 22,
    })
    setFormErrors({})
    setTouched({})
    setShowModal(true)
  }

  const openEditModal = (group: SwitchGroup) => {
    setEditingGroup(group)
    setFormData({
      name: group.name,
      description: group.description || '',
      ssh_username: group.ssh_username || '',
      ssh_password: '',
      ssh_port: group.ssh_port,
    })
    setFormErrors({})
    setTouched({})
    setShowModal(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validate form
    const errors = validateForm()
    setFormErrors(errors)
    setTouched({ name: true, ssh_port: true })

    if (Object.keys(errors).length > 0) {
      return
    }

    setSaving(true)
    setError('')

    try {
      const dataToSend: any = {
        name: formData.name,
        ssh_port: formData.ssh_port || 22,
      }

      if (formData.description?.trim()) {
        dataToSend.description = formData.description.trim()
      }
      if (formData.ssh_username?.trim()) {
        dataToSend.ssh_username = formData.ssh_username.trim()
      }
      if (formData.ssh_password?.trim()) {
        dataToSend.ssh_password = formData.ssh_password.trim()
      }

      if (editingGroup) {
        await groupsApi.update(editingGroup.id, dataToSend)
        setSuccess('Gruppo aggiornato con successo')
      } else {
        await groupsApi.create(dataToSend)
        setSuccess('Gruppo creato con successo')
      }

      setShowModal(false)
      loadGroups()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.userMessage || 'Errore nel salvataggio')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await groupsApi.delete(id)
      setSuccess('Gruppo eliminato con successo')
      setDeleteConfirm(null)
      loadGroups()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.userMessage || 'Errore nella eliminazione')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Gruppi Credenziali
        </h1>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nuovo Gruppo
        </button>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-5 w-5" />
          {error}
        </div>
      )}

      {success && (
        <div className="mb-4 p-4 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-lg flex items-center gap-2">
          <CheckCircle className="h-5 w-5" />
          {success}
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        {groups.length === 0 ? (
          <div className="p-12 text-center text-gray-500 dark:text-gray-400">
            <FolderCog className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Nessun gruppo configurato</p>
            <p className="text-sm mt-2">I gruppi permettono di condividere credenziali SSH tra switch</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {groups.map((group) => (
              <div key={group.id} className="p-6 flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    {group.name}
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {group.description || 'Nessuna descrizione'}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    SSH: {group.ssh_username || '-'}@porta {group.ssh_port} | {group.switch_count} switch
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {deleteConfirm === group.id ? (
                    <>
                      <span className="text-sm text-red-600 dark:text-red-400 mr-2">Confermi?</span>
                      <button
                        onClick={() => handleDelete(group.id)}
                        className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
                      >
                        Sì
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(null)}
                        className="px-3 py-1 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200 text-sm rounded hover:bg-gray-400"
                      >
                        No
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => openEditModal(group)}
                        className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                        aria-label={`Modifica gruppo ${group.name}`}
                        title="Modifica"
                      >
                        <Edit className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(group.id)}
                        className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                        aria-label={`Elimina gruppo ${group.name}`}
                        title="Elimina"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editingGroup ? 'Modifica Gruppo' : 'Nuovo Gruppo'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                aria-label="Chiudi finestra"
                title="Chiudi"
              >
                <X className="h-5 w-5 text-gray-500" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              <div>
                <label htmlFor="group-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Nome Gruppo *
                </label>
                <input
                  id="group-name"
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  onBlur={() => {
                    setTouched({ ...touched, name: true })
                    setFormErrors(validateForm())
                  }}
                  className={`w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 ${
                    touched.name && formErrors.name ? 'border-red-500 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
                  }`}
                  placeholder="es. DATACENTER_CORE"
                />
                {touched.name && formErrors.name && (
                  <p className="mt-1 text-sm text-red-600 dark:text-red-400">{formErrors.name}</p>
                )}
              </div>

              <div>
                <label htmlFor="group-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Descrizione
                </label>
                <input
                  id="group-description"
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  placeholder="Descrizione opzionale"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label htmlFor="group-ssh-username" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    SSH Username
                  </label>
                  <input
                    id="group-ssh-username"
                    type="text"
                    value={formData.ssh_username}
                    onChange={(e) => setFormData({ ...formData, ssh_username: e.target.value })}
                    className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                    placeholder="admin"
                  />
                </div>

                <div>
                  <label htmlFor="ssh-port" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    SSH Port
                  </label>
                  <input
                    id="ssh-port"
                    type="number"
                    value={formData.ssh_port}
                    onChange={(e) => setFormData({ ...formData, ssh_port: parseInt(e.target.value) || 22 })}
                    onBlur={() => {
                      setTouched({ ...touched, ssh_port: true })
                      setFormErrors(validateForm())
                    }}
                    className={`w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 ${
                      touched.ssh_port && formErrors.ssh_port ? 'border-red-500 dark:border-red-500' : 'border-gray-300 dark:border-gray-600'
                    }`}
                    min="1"
                    max="65535"
                  />
                  {touched.ssh_port && formErrors.ssh_port && (
                    <p className="mt-1 text-sm text-red-600 dark:text-red-400">{formErrors.ssh_port}</p>
                  )}
                </div>
              </div>

              <div>
                <label htmlFor="group-ssh-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  SSH Password {editingGroup && '(lascia vuoto per non modificare)'}
                </label>
                <input
                  id="group-ssh-password"
                  type="password"
                  value={formData.ssh_password}
                  onChange={(e) => setFormData({ ...formData, ssh_password: e.target.value })}
                  className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  placeholder="••••••••"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? 'Salvataggio...' : editingGroup ? 'Aggiorna' : 'Crea'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
