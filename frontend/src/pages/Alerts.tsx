import { useState, useEffect } from 'react'
import { Bell, Check, Filter, Calendar, X } from 'lucide-react'
import { alertsApi, Alert } from '../api/client'

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [filter, setFilter] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    loadAlerts()
  }, [filter, dateFrom, dateTo])

  const loadAlerts = async () => {
    setLoading(true)
    try {
      const params: { alert_type?: string; date_from?: string; date_to?: string } = {}
      if (filter !== 'all') {
        params.alert_type = filter
      }
      if (dateFrom) {
        params.date_from = dateFrom
      }
      if (dateTo) {
        params.date_to = dateTo
      }
      const response = await alertsApi.list(params)
      setAlerts(response.data.items)
      setUnreadCount(response.data.unread_count)
    } catch (err) {
      console.error('Error loading alerts:', err)
    } finally {
      setLoading(false)
    }
  }

  const clearDateFilter = () => {
    setDateFrom('')
    setDateTo('')
  }

  // REMOVED: seedDemoData function (Feature #126 - use real data only from discovery)

  const markAsRead = async (alertId: number) => {
    try {
      await alertsApi.markRead(alertId)
      setAlerts(prev => prev.map(a =>
        a.id === alertId ? { ...a, is_read: true } : a
      ))
      setUnreadCount(prev => Math.max(0, prev - 1))
    } catch (err) {
      console.error('Error marking alert as read:', err)
    }
  }

  const markAllAsRead = async () => {
    try {
      await alertsApi.markAllRead()
      setAlerts(prev => prev.map(a => ({ ...a, is_read: true })))
      setUnreadCount(0)
    } catch (err) {
      console.error('Error marking all alerts as read:', err)
    }
  }

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
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            Alert
          </h1>
          {unreadCount > 0 && (
            <span className="px-2 py-1 bg-red-500 text-white text-sm rounded-full">
              {unreadCount} non letti
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* REMOVED: "Carica Demo" button (Feature #126 - use real data only) */}
          <button
            onClick={markAllAsRead}
            disabled={unreadCount === 0}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            Marca Tutti come Letti
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-500" />
          <span className="text-sm text-gray-500 dark:text-gray-400">Tipo:</span>
        </div>
        <div className="flex gap-2">
          {['all', 'new_mac', 'mac_move', 'mac_disappear', 'port_threshold'].map((type) => (
            <button
              key={type}
              onClick={() => setFilter(type)}
              className={`px-3 py-1 text-sm rounded-full transition-colors ${
                filter === type
                  ? 'bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            >
              {type === 'all' ? 'Tutti' :
               type === 'new_mac' ? 'Nuovo MAC' :
               type === 'mac_move' ? 'Movimento' :
               type === 'mac_disappear' ? 'Scomparso' :
               'Soglia Porta'}
            </button>
          ))}
        </div>
      </div>

      {/* Date Range Filter */}
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-gray-500" />
          <span className="text-sm text-gray-500 dark:text-gray-400">Periodo:</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Da"
          />
          <span className="text-gray-500 dark:text-gray-400">-</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="A"
          />
          {(dateFrom || dateTo) && (
            <button
              onClick={clearDateFilter}
              className="p-1.5 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              title="Cancella filtro date"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        {(dateFrom || dateTo) && (
          <span className="text-sm text-blue-600 dark:text-blue-400">
            Filtro attivo
          </span>
        )}
      </div>

      {/* Alert List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        {loading ? (
          <div className="p-12 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : alerts.length === 0 ? (
          <div className="p-12 text-center text-gray-500 dark:text-gray-400">
            <Bell className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Nessun alert</p>
            <p className="text-sm mt-2">Gli alert appariranno qui quando rilevati dal discovery</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`p-4 flex items-start gap-4 ${!alert.is_read ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
              >
                <div className={`p-2 rounded-full ${
                  alert.severity === 'critical' ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400' :
                  alert.severity === 'warning' ? 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400' :
                  'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400'
                }`}>
                  <Bell className="h-4 w-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 text-xs rounded ${
                      alert.alert_type === 'new_mac' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                      alert.alert_type === 'mac_move' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                      alert.alert_type === 'mac_disappear' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                      'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                    }`}>
                      {alert.alert_type === 'new_mac' ? 'Nuovo MAC' :
                       alert.alert_type === 'mac_move' ? 'Movimento' :
                       alert.alert_type === 'mac_disappear' ? 'Scomparso' :
                       'Soglia Porta'}
                    </span>
                    {!alert.is_read && (
                      <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
                    )}
                  </div>
                  <p className="text-gray-900 dark:text-white mt-1">{alert.message}</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    {formatDate(alert.created_at)}
                  </p>
                </div>
                {!alert.is_read && (
                  <button
                    onClick={() => markAsRead(alert.id)}
                    className="text-blue-600 dark:text-blue-400 text-sm hover:underline"
                  >
                    Segna come letto
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
