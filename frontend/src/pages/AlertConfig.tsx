import { useState, useEffect } from 'react'
import { Bell, Webhook, Plus, Edit2, Trash2, Save, X, Play, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import api from '../api/client'

interface AlertRule {
  id: number
  name: string
  description: string | null
  rule_type: string
  conditions: Record<string, any>
  alert_severity: string
  is_enabled: boolean
  created_at: string
  updated_at: string
}

interface WebhookConfig {
  id: number
  name: string
  url: string
  webhook_type: string
  alert_types: string[]
  is_enabled: boolean
  last_triggered: string | null
  last_status: string | null
  created_at: string
}

const RULE_TYPES = [
  { value: 'oui_filter', label: 'Filtro OUI', description: 'Alert per MAC con specifico OUI' },
  { value: 'vendor_filter', label: 'Filtro Vendor', description: 'Alert per MAC di specifico vendor' },
  { value: 'switch_filter', label: 'Filtro Switch', description: 'Alert per MAC su specifico switch' },
  { value: 'vlan_filter', label: 'Filtro VLAN', description: 'Alert per MAC su specifica VLAN' },
]

const WEBHOOK_TYPES = [
  { value: 'generic', label: 'Generico (JSON)' },
  { value: 'slack', label: 'Slack' },
  { value: 'teams', label: 'Microsoft Teams' },
  { value: 'discord', label: 'Discord' },
  { value: 'siem', label: 'SIEM/Syslog' },
]

const ALERT_TYPES = [
  { value: 'all', label: 'Tutti gli alert' },
  { value: 'new_mac', label: 'Nuovo MAC' },
  { value: 'mac_move', label: 'Spostamento MAC' },
  { value: 'mac_disappear', label: 'MAC scomparso' },
  { value: 'port_threshold', label: 'Soglia porte' },
]

export default function AlertConfig() {
  const [activeTab, setActiveTab] = useState<'rules' | 'webhooks'>('rules')
  const [rules, setRules] = useState<AlertRule[]>([])
  const [webhooks, setWebhooks] = useState<WebhookConfig[]>([])
  const [loading, setLoading] = useState(true)

  // Rule editing
  const [editingRule, setEditingRule] = useState<Partial<AlertRule> | null>(null)
  const [savingRule, setSavingRule] = useState(false)

  // Webhook editing
  const [editingWebhook, setEditingWebhook] = useState<Partial<WebhookConfig> | null>(null)
  const [savingWebhook, setSavingWebhook] = useState(false)
  const [testingWebhook, setTestingWebhook] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [rulesRes, webhooksRes] = await Promise.all([
        api.get('/alerting/rules'),
        api.get('/alerting/webhooks')
      ])
      setRules(rulesRes.data)
      setWebhooks(webhooksRes.data)
    } catch (err) {
      console.error('Error loading config:', err)
    } finally {
      setLoading(false)
    }
  }

  // === Rule Management ===
  const saveRule = async () => {
    if (!editingRule?.name || !editingRule?.rule_type) return
    setSavingRule(true)
    try {
      if (editingRule.id) {
        await api.put(`/alerting/rules/${editingRule.id}`, editingRule)
      } else {
        await api.post('/alerting/rules', editingRule)
      }
      setEditingRule(null)
      loadData()
    } catch (err) {
      console.error('Error saving rule:', err)
    } finally {
      setSavingRule(false)
    }
  }

  const deleteRule = async (id: number) => {
    if (!confirm('Eliminare questa regola?')) return
    try {
      await api.delete(`/alerting/rules/${id}`)
      loadData()
    } catch (err) {
      console.error('Error deleting rule:', err)
    }
  }

  const toggleRule = async (rule: AlertRule) => {
    try {
      await api.put(`/alerting/rules/${rule.id}`, { is_enabled: !rule.is_enabled })
      loadData()
    } catch (err) {
      console.error('Error toggling rule:', err)
    }
  }

  // === Webhook Management ===
  const saveWebhook = async () => {
    if (!editingWebhook?.name || !editingWebhook?.url) return
    setSavingWebhook(true)
    try {
      if (editingWebhook.id) {
        await api.put(`/alerting/webhooks/${editingWebhook.id}`, editingWebhook)
      } else {
        await api.post('/alerting/webhooks', editingWebhook)
      }
      setEditingWebhook(null)
      loadData()
    } catch (err) {
      console.error('Error saving webhook:', err)
    } finally {
      setSavingWebhook(false)
    }
  }

  const deleteWebhook = async (id: number) => {
    if (!confirm('Eliminare questo webhook?')) return
    try {
      await api.delete(`/alerting/webhooks/${id}`)
      loadData()
    } catch (err) {
      console.error('Error deleting webhook:', err)
    }
  }

  const toggleWebhook = async (wh: WebhookConfig) => {
    try {
      await api.put(`/alerting/webhooks/${wh.id}`, { is_enabled: !wh.is_enabled })
      loadData()
    } catch (err) {
      console.error('Error toggling webhook:', err)
    }
  }

  const testWebhook = async (id: number) => {
    setTestingWebhook(id)
    setTestResult(null)
    try {
      await api.post(`/alerting/webhooks/${id}/test`)
      setTestResult({ id, success: true, message: 'Test inviato con successo!' })
      loadData()
    } catch (err: any) {
      setTestResult({ id, success: false, message: err.response?.data?.detail || 'Test fallito' })
    } finally {
      setTestingWebhook(null)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Configurazione Alerting
      </h1>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex -mb-px">
          <button
            onClick={() => setActiveTab('rules')}
            className={`px-6 py-3 text-sm font-medium border-b-2 ${
              activeTab === 'rules'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
            }`}
          >
            <Bell className="h-4 w-4 inline mr-2" />
            Regole Custom ({rules.length})
          </button>
          <button
            onClick={() => setActiveTab('webhooks')}
            className={`px-6 py-3 text-sm font-medium border-b-2 ${
              activeTab === 'webhooks'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
            }`}
          >
            <Webhook className="h-4 w-4 inline mr-2" />
            Webhooks ({webhooks.length})
          </button>
        </nav>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        </div>
      ) : activeTab === 'rules' ? (
        <div className="space-y-4">
          {/* Add Rule Button */}
          <div className="flex justify-end">
            <button
              onClick={() => setEditingRule({ name: '', rule_type: 'oui_filter', conditions: {}, alert_severity: 'warning', is_enabled: true })}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              Nuova Regola
            </button>
          </div>

          {/* Rules List */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow divide-y divide-gray-200 dark:divide-gray-700">
            {rules.length === 0 ? (
              <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                <Bell className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Nessuna regola custom configurata</p>
                <p className="text-sm">Crea regole per generare alert personalizzati</p>
              </div>
            ) : (
              rules.map(rule => (
                <div key={rule.id} className="p-4 flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <span className={`w-3 h-3 rounded-full ${rule.is_enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
                      <span className="font-medium text-gray-900 dark:text-white">{rule.name}</span>
                      <span className={`px-2 py-0.5 text-xs rounded ${
                        rule.alert_severity === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                        rule.alert_severity === 'warning' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                        'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                      }`}>
                        {rule.alert_severity}
                      </span>
                    </div>
                    {rule.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 ml-6">{rule.description}</p>
                    )}
                    <p className="text-xs text-gray-400 mt-1 ml-6">
                      Tipo: {RULE_TYPES.find(t => t.value === rule.rule_type)?.label || rule.rule_type}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => toggleRule(rule)}
                      className={`px-3 py-1 text-sm rounded ${rule.is_enabled ? 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'}`}
                    >
                      {rule.is_enabled ? 'Disabilita' : 'Abilita'}
                    </button>
                    <button
                      onClick={() => setEditingRule(rule)}
                      className="p-2 text-gray-400 hover:text-blue-500"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => deleteRule(rule.id)}
                      className="p-2 text-gray-400 hover:text-red-500"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Add Webhook Button */}
          <div className="flex justify-end">
            <button
              onClick={() => setEditingWebhook({ name: '', url: '', webhook_type: 'generic', alert_types: ['all'], is_enabled: true })}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              Nuovo Webhook
            </button>
          </div>

          {/* Webhooks List */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow divide-y divide-gray-200 dark:divide-gray-700">
            {webhooks.length === 0 ? (
              <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                <Webhook className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Nessun webhook configurato</p>
                <p className="text-sm">Configura webhook per inviare alert a Slack, Teams o SIEM</p>
              </div>
            ) : (
              webhooks.map(wh => (
                <div key={wh.id} className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <span className={`w-3 h-3 rounded-full ${wh.is_enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
                        <span className="font-medium text-gray-900 dark:text-white">{wh.name}</span>
                        <span className="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                          {WEBHOOK_TYPES.find(t => t.value === wh.webhook_type)?.label || wh.webhook_type}
                        </span>
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 ml-6 font-mono truncate max-w-md">
                        {wh.url}
                      </p>
                      {wh.last_triggered && (
                        <p className="text-xs text-gray-400 mt-1 ml-6">
                          Ultimo invio: {new Date(wh.last_triggered).toLocaleString()}
                          {wh.last_status && (
                            <span className={wh.last_status === 'success' ? 'text-green-500 ml-2' : 'text-red-500 ml-2'}>
                              ({wh.last_status})
                            </span>
                          )}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => testWebhook(wh.id)}
                        disabled={testingWebhook === wh.id}
                        className="px-3 py-1 text-sm bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 rounded hover:bg-purple-200 disabled:opacity-50"
                      >
                        {testingWebhook === wh.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => toggleWebhook(wh)}
                        className={`px-3 py-1 text-sm rounded ${wh.is_enabled ? 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'}`}
                      >
                        {wh.is_enabled ? 'Disabilita' : 'Abilita'}
                      </button>
                      <button
                        onClick={() => setEditingWebhook(wh)}
                        className="p-2 text-gray-400 hover:text-blue-500"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => deleteWebhook(wh.id)}
                        className="p-2 text-gray-400 hover:text-red-500"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  {testResult?.id === wh.id && (
                    <div className={`mt-2 ml-6 p-2 rounded text-sm ${testResult.success ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}>
                      {testResult.success ? <CheckCircle className="h-4 w-4 inline mr-1" /> : <XCircle className="h-4 w-4 inline mr-1" />}
                      {testResult.message}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Rule Edit Modal */}
      {editingRule && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                {editingRule.id ? 'Modifica Regola' : 'Nuova Regola'}
              </h3>
              <button onClick={() => setEditingRule(null)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nome</label>
                <input
                  type="text"
                  value={editingRule.name || ''}
                  onChange={(e) => setEditingRule({ ...editingRule, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrizione</label>
                <input
                  type="text"
                  value={editingRule.description || ''}
                  onChange={(e) => setEditingRule({ ...editingRule, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tipo Regola</label>
                <select
                  value={editingRule.rule_type || 'oui_filter'}
                  onChange={(e) => setEditingRule({ ...editingRule, rule_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {RULE_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Condizione ({editingRule.rule_type === 'oui_filter' ? 'OUI (es: 00:18:6E)' :
                              editingRule.rule_type === 'vendor_filter' ? 'Nome Vendor' :
                              editingRule.rule_type === 'switch_filter' ? 'Hostname Switch' : 'VLAN ID'})
                </label>
                <input
                  type="text"
                  value={editingRule.conditions?.value || ''}
                  onChange={(e) => setEditingRule({ ...editingRule, conditions: { value: e.target.value } })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder={editingRule.rule_type === 'oui_filter' ? '00:18:6E' :
                              editingRule.rule_type === 'vendor_filter' ? 'SHANGHAI SIMCOM' :
                              editingRule.rule_type === 'switch_filter' ? '29_L2_CED_7' : '13'}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Severità Alert</label>
                <select
                  value={editingRule.alert_severity || 'warning'}
                  onChange={(e) => setEditingRule({ ...editingRule, alert_severity: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setEditingRule(null)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                Annulla
              </button>
              <button
                onClick={saveRule}
                disabled={savingRule || !editingRule.name}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {savingRule ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Salva
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Webhook Edit Modal */}
      {editingWebhook && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                {editingWebhook.id ? 'Modifica Webhook' : 'Nuovo Webhook'}
              </h3>
              <button onClick={() => setEditingWebhook(null)} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nome</label>
                <input
                  type="text"
                  value={editingWebhook.name || ''}
                  onChange={(e) => setEditingWebhook({ ...editingWebhook, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">URL</label>
                <input
                  type="url"
                  value={editingWebhook.url || ''}
                  onChange={(e) => setEditingWebhook({ ...editingWebhook, url: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="https://hooks.slack.com/services/..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tipo</label>
                <select
                  value={editingWebhook.webhook_type || 'generic'}
                  onChange={(e) => setEditingWebhook({ ...editingWebhook, webhook_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {WEBHOOK_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tipi di Alert</label>
                <select
                  value={editingWebhook.alert_types?.[0] || 'all'}
                  onChange={(e) => setEditingWebhook({ ...editingWebhook, alert_types: [e.target.value] })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {ALERT_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setEditingWebhook(null)}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                Annulla
              </button>
              <button
                onClick={saveWebhook}
                disabled={savingWebhook || !editingWebhook.name || !editingWebhook.url}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {savingWebhook ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Salva
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
