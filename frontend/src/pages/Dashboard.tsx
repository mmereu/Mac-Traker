import { useState, useEffect } from 'react'
import { Server, Wifi, Bell, Clock, RefreshCw, Building2, ShieldCheck, AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { dashboardApi, DashboardStats, SiteStatsBySite } from '../api/client'

interface TrendDataPoint {
  date: string;
  count: number;
}

interface MacBreakdown {
  total: number;
  real: number;
  random: number;
  multicast: number;
}

interface IntentSummary {
  health_score: number;
  total_checks: number;
  passed: number;
  issues: { critical: number; errors: number; warnings: number };
  top_issues: { check: string; severity: string; message: string }[];
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [topSwitches, setTopSwitches] = useState<{ id: number; hostname: string; mac_count: number }[]>([])
  const [trendData, setTrendData] = useState<TrendDataPoint[]>([])
  const [siteStats, setSiteStats] = useState<SiteStatsBySite | null>(null)
  const [macBreakdown, setMacBreakdown] = useState<MacBreakdown | null>(null)
  const [intentSummary, setIntentSummary] = useState<IntentSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [statsRes, topSwitchesRes, trendsRes, siteStatsRes, macBreakdownRes] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getTopSwitches(10),
        dashboardApi.getTrends(7),
        dashboardApi.getStatsBySite(),
        dashboardApi.getMacBreakdown(),
      ])
      setStats(statsRes.data)
      setTopSwitches(topSwitchesRes.data)
      setTrendData(trendsRes.data)
      setSiteStats(siteStatsRes.data)
      setMacBreakdown(macBreakdownRes.data)
    } catch (err: any) {
      console.error('Failed to fetch dashboard data:', err)
      setError(err.userMessage || 'Errore nel caricamento dei dati')
    } finally {
      setLoading(false)
    }

    // Fetch intent summary separately (non-blocking, with timeout)
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 15000)
      const intentRes = await fetch('/api/intent/summary', { signal: controller.signal })
      clearTimeout(timeoutId)
      if (intentRes.ok) {
        setIntentSummary(await intentRes.json())
      }
    } catch {
      // Intent summary is optional - don't block dashboard
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const formatLastDiscovery = (dateStr: string | undefined | null) => {
    if (!dateStr) return 'Mai'
    try {
      const date = new Date(dateStr)
      return date.toLocaleString('it-IT', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return 'Mai'
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Aggiorna
        </button>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/50 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400">
              <Wifi className="h-6 w-6" />
            </div>
            <div className="ml-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">MAC Attivi</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                {loading ? '...' : (macBreakdown?.real ?? stats?.mac_count ?? 0).toLocaleString()}
              </p>
            </div>
          </div>
          {macBreakdown && !loading && (
            <div className="mt-3 pt-3 border-t dark:border-gray-700 space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Reali (vendor)</span>
                <span className="font-medium text-blue-600 dark:text-blue-400">{macBreakdown.real.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Random (privacy)</span>
                <span className="font-medium text-orange-500 dark:text-orange-400">{macBreakdown.random.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Multicast</span>
                <span className="font-medium text-gray-400 dark:text-gray-500">{macBreakdown.multicast.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-xs pt-1 border-t dark:border-gray-700">
                <span className="text-gray-500 dark:text-gray-400">Totale</span>
                <span className="font-medium text-gray-700 dark:text-gray-300">{macBreakdown.total.toLocaleString()}</span>
              </div>
            </div>
          )}
        </div>
        <StatCard
          title="Switch Monitorati"
          value={loading ? '...' : String(stats?.switch_count ?? 0)}
          icon={Server}
          color="green"
        />
        <StatCard
          title="Alert Non Letti"
          value={loading ? '...' : String(stats?.alert_count ?? 0)}
          icon={Bell}
          color="red"
        />
        <StatCard
          title="Ultimo Discovery"
          value={loading ? '...' : formatLastDiscovery(stats?.last_discovery)}
          icon={Clock}
          color="yellow"
          smallText
        />
      </div>

      {/* Intent Verification Widget */}
      {intentSummary && (
        <div className="mb-8">
          <Link
            to="/intent"
            className="block bg-white dark:bg-gray-800 rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className={`w-16 h-16 rounded-full flex items-center justify-center ${
                  intentSummary.health_score >= 80 ? 'bg-green-100 dark:bg-green-900/30' :
                  intentSummary.health_score >= 60 ? 'bg-yellow-100 dark:bg-yellow-900/30' :
                  intentSummary.health_score >= 40 ? 'bg-orange-100 dark:bg-orange-900/30' :
                  'bg-red-100 dark:bg-red-900/30'
                }`}>
                  <ShieldCheck className={`h-8 w-8 ${
                    intentSummary.health_score >= 80 ? 'text-green-600 dark:text-green-400' :
                    intentSummary.health_score >= 60 ? 'text-yellow-600 dark:text-yellow-400' :
                    intentSummary.health_score >= 40 ? 'text-orange-600 dark:text-orange-400' :
                    'text-red-600 dark:text-red-400'
                  }`} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Network Health Score
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Intent Verification: {intentSummary.passed}/{intentSummary.total_checks} check superati
                  </p>
                </div>
              </div>
              <div className="text-right">
                <div className={`text-4xl font-bold ${
                  intentSummary.health_score >= 80 ? 'text-green-600 dark:text-green-400' :
                  intentSummary.health_score >= 60 ? 'text-yellow-600 dark:text-yellow-400' :
                  intentSummary.health_score >= 40 ? 'text-orange-600 dark:text-orange-400' :
                  'text-red-600 dark:text-red-400'
                }`}>
                  {Math.round(intentSummary.health_score)}%
                </div>
                {(intentSummary.issues.critical > 0 || intentSummary.issues.errors > 0) && (
                  <div className="flex items-center gap-2 justify-end mt-1">
                    <AlertTriangle className="h-4 w-4 text-orange-500" />
                    <span className="text-sm text-orange-600 dark:text-orange-400">
                      {intentSummary.issues.critical + intentSummary.issues.errors} issue
                    </span>
                  </div>
                )}
              </div>
            </div>
            {intentSummary.top_issues.length > 0 && (
              <div className="mt-4 pt-4 border-t dark:border-gray-700">
                <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">Top Issues:</div>
                <div className="space-y-1">
                  {intentSummary.top_issues.slice(0, 3).map((issue, idx) => (
                    <div key={idx} className="text-sm flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${
                        issue.severity === 'critical' ? 'bg-red-500' :
                        issue.severity === 'error' ? 'bg-orange-500' :
                        'bg-yellow-500'
                      }`} />
                      <span className="text-gray-700 dark:text-gray-300 truncate">
                        {issue.check}: {issue.message}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Link>
        </div>
      )}

      {/* Site Stats Section */}
      {siteStats && siteStats.sites.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            Statistiche per Sede
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Site Stats Table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Dettaglio Sedi ({siteStats.total_sites} totali)
              </h3>
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-white dark:bg-gray-800">
                    <tr className="border-b dark:border-gray-700">
                      <th className="text-left py-2 px-2 font-medium text-gray-600 dark:text-gray-400">Sede</th>
                      <th className="text-right py-2 px-2 font-medium text-gray-600 dark:text-gray-400">Switch</th>
                      <th className="text-right py-2 px-2 font-medium text-gray-600 dark:text-gray-400">MAC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {siteStats.sites.map((site) => (
                      <tr key={site.site_code} className="border-b dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/50">
                        <td className="py-2 px-2 font-medium text-gray-900 dark:text-white">
                          {site.site_name}
                        </td>
                        <td className="py-2 px-2 text-right text-gray-700 dark:text-gray-300">
                          {site.switch_count}
                        </td>
                        <td className="py-2 px-2 text-right text-blue-600 dark:text-blue-400 font-semibold">
                          {site.mac_count.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                    {siteStats.switches_without_site > 0 && (
                      <tr className="border-b dark:border-gray-700/50 text-gray-500 dark:text-gray-400 italic">
                        <td className="py-2 px-2">Senza sede</td>
                        <td className="py-2 px-2 text-right">{siteStats.switches_without_site}</td>
                        <td className="py-2 px-2 text-right">{siteStats.macs_without_site.toLocaleString()}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Site Stats Bar Chart */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                MAC per Sede
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={siteStats.sites.slice(0, 10).map(s => ({
                    name: `Sede ${s.site_code}`,
                    mac_count: s.mac_count,
                    switch_count: s.switch_count
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: 'currentColor', fontSize: 12 }}
                      className="text-gray-600 dark:text-gray-400"
                    />
                    <YAxis
                      tick={{ fill: 'currentColor' }}
                      className="text-gray-600 dark:text-gray-400"
                      allowDecimals={false}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--tooltip-bg, #1f2937)',
                        border: 'none',
                        borderRadius: '8px',
                        color: 'var(--tooltip-text, #f3f4f6)'
                      }}
                      formatter={(value: number, name: string) => [
                        value.toLocaleString(),
                        name === 'mac_count' ? 'MAC' : 'Switch'
                      ]}
                    />
                    <Bar dataKey="mac_count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Charts and Top Switches */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Trend MAC nel Tempo
          </h2>
          <div className="h-64">
            {loading ? (
              <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
                <span>Caricamento...</span>
              </div>
            ) : trendData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
                <span className="text-sm">Grafico trend disponibile dopo più sessioni di discovery</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData.map(d => ({
                  ...d,
                  dateLabel: new Date(d.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
                }))}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis
                    dataKey="dateLabel"
                    tick={{ fill: 'currentColor' }}
                    className="text-gray-600 dark:text-gray-400 text-xs"
                  />
                  <YAxis
                    tick={{ fill: 'currentColor' }}
                    className="text-gray-600 dark:text-gray-400 text-xs"
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--tooltip-bg, #1f2937)',
                      border: 'none',
                      borderRadius: '8px',
                      color: 'var(--tooltip-text, #f3f4f6)'
                    }}
                    labelFormatter={(value) => `Data: ${value}`}
                    formatter={(value: number) => [`${value} MAC`, 'Totale']}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ fill: '#3b82f6', strokeWidth: 2, r: 4 }}
                    activeDot={{ r: 6, fill: '#2563eb' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Top 10 Switch per MAC
          </h2>
          <div className="h-64 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
                Caricamento...
              </div>
            ) : topSwitches.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
                Nessun dato disponibile
              </div>
            ) : (
              <ul className="space-y-3">
                {topSwitches.map((sw, index) => (
                  <li key={sw.id} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center justify-center w-6 h-6 text-xs font-bold text-white bg-blue-600 rounded-full">
                        {index + 1}
                      </span>
                      <span className="font-medium text-gray-900 dark:text-white">
                        {sw.hostname}
                      </span>
                    </div>
                    <span className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                      {sw.mac_count} MAC
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

interface StatCardProps {
  title: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  color: 'blue' | 'green' | 'red' | 'yellow'
  smallText?: boolean
}

function StatCard({ title, value, icon: Icon, color, smallText }: StatCardProps) {
  const colors = {
    blue: 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400',
    green: 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400',
    red: 'bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400',
    yellow: 'bg-yellow-100 dark:bg-yellow-900/50 text-yellow-600 dark:text-yellow-400',
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
      <div className="flex items-center">
        <div className={`p-3 rounded-lg ${colors[color]}`}>
          <Icon className="h-6 w-6" />
        </div>
        <div className="ml-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          <p className={`font-semibold text-gray-900 dark:text-white ${smallText ? 'text-sm' : 'text-2xl'}`}>
            {value}
          </p>
        </div>
      </div>
    </div>
  )
}
