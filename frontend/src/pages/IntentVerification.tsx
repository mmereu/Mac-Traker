import { useState, useEffect } from 'react'
import { ShieldCheck, AlertTriangle, AlertCircle, Info, RefreshCw, Play, ChevronDown, ChevronRight, Lightbulb } from 'lucide-react'

interface CheckResult {
  check_id: string
  check_name: string
  category: string
  severity: string
  passed: boolean
  message: string
  affected_count: number
  affected_items: any[]
  checked_at: string
  details?: any
  remediation?: string  // Suggested fix/action
}

interface IntentSummary {
  total_checks: number
  passed: number
  failed: number
  by_severity: Record<string, number>
  by_category: Record<string, number>
  checks: CheckResult[]
  run_at: string
}

interface QuickSummary {
  health_score: number
  total_checks: number
  passed: number
  issues: {
    critical: number
    errors: number
    warnings: number
  }
  top_issues: { check: string; severity: string; message: string }[]
}

const severityColors: Record<string, { bg: string; text: string; icon: any }> = {
  critical: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', icon: AlertCircle },
  error: { bg: 'bg-orange-100 dark:bg-orange-900/30', text: 'text-orange-700 dark:text-orange-400', icon: AlertTriangle },
  warning: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', icon: AlertTriangle },
  info: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', icon: Info },
}

const categoryColors: Record<string, string> = {
  topology: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400',
  security: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
  compliance: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
  performance: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
  availability: 'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-400',
}

export default function IntentVerification() {
  const [summary, setSummary] = useState<QuickSummary | null>(null)
  const [fullResults, setFullResults] = useState<IntentSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [expandedChecks, setExpandedChecks] = useState<Set<string>>(new Set())

  const fetchSummary = async () => {
    try {
      const response = await fetch('/api/intent/summary')
      if (response.ok) {
        const data = await response.json()
        setSummary(data)
      }
    } catch (error) {
      console.error('Error fetching intent summary:', error)
    } finally {
      setLoading(false)
    }
  }

  const runAllChecks = async () => {
    setRunning(true)
    try {
      const response = await fetch('/api/intent/run', { method: 'POST' })
      if (response.ok) {
        const data = await response.json()
        setFullResults(data)
        // Update summary with new results
        fetchSummary()
      }
    } catch (error) {
      console.error('Error running intent checks:', error)
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    fetchSummary()
  }, [])

  const toggleCheck = (checkId: string) => {
    const newExpanded = new Set(expandedChecks)
    if (newExpanded.has(checkId)) {
      newExpanded.delete(checkId)
    } else {
      newExpanded.add(checkId)
    }
    setExpandedChecks(newExpanded)
  }

  const getHealthColor = (score: number) => {
    if (score >= 80) return 'text-green-600 dark:text-green-400'
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400'
    if (score >= 40) return 'text-orange-600 dark:text-orange-400'
    return 'text-red-600 dark:text-red-400'
  }

  const getHealthBg = (score: number) => {
    if (score >= 80) return 'bg-green-500'
    if (score >= 60) return 'bg-yellow-500'
    if (score >= 40) return 'bg-orange-500'
    return 'bg-red-500'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-blue-600" />
            Intent Verification
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Network compliance checks - IP Fabric-like intent verification
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchSummary}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={runAllChecks}
            disabled={running}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {running ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {running ? 'Running...' : 'Run All Checks'}
          </button>
        </div>
      </div>

      {/* Health Score Card */}
      {summary && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {/* Health Score */}
            <div className="col-span-1 flex flex-col items-center justify-center">
              <div className="relative w-32 h-32">
                <svg className="w-full h-full transform -rotate-90">
                  <circle
                    cx="64"
                    cy="64"
                    r="56"
                    stroke="currentColor"
                    strokeWidth="12"
                    fill="none"
                    className="text-gray-200 dark:text-gray-700"
                  />
                  <circle
                    cx="64"
                    cy="64"
                    r="56"
                    stroke="currentColor"
                    strokeWidth="12"
                    fill="none"
                    strokeDasharray={`${(summary.health_score / 100) * 351.86} 351.86`}
                    className={getHealthColor(summary.health_score)}
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-3xl font-bold ${getHealthColor(summary.health_score)}`}>
                    {Math.round(summary.health_score)}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Health Score</span>
                </div>
              </div>
            </div>

            {/* Stats */}
            <div className="col-span-3 grid grid-cols-3 gap-4">
              <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
                <div className="text-3xl font-bold text-green-600 dark:text-green-400">
                  {summary.passed}
                </div>
                <div className="text-sm text-green-700 dark:text-green-300">Checks Passed</div>
              </div>
              <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4">
                <div className="text-3xl font-bold text-red-600 dark:text-red-400">
                  {summary.total_checks - summary.passed}
                </div>
                <div className="text-sm text-red-700 dark:text-red-300">Checks Failed</div>
              </div>
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">
                  {summary.total_checks}
                </div>
                <div className="text-sm text-blue-700 dark:text-blue-300">Total Checks</div>
              </div>

              {/* Issue breakdown */}
              <div className="col-span-3 flex gap-4 mt-2">
                {summary.issues.critical > 0 && (
                  <div className="flex items-center gap-1 text-sm text-red-600 dark:text-red-400">
                    <AlertCircle className="h-4 w-4" />
                    {summary.issues.critical} Critical
                  </div>
                )}
                {summary.issues.errors > 0 && (
                  <div className="flex items-center gap-1 text-sm text-orange-600 dark:text-orange-400">
                    <AlertTriangle className="h-4 w-4" />
                    {summary.issues.errors} Errors
                  </div>
                )}
                {summary.issues.warnings > 0 && (
                  <div className="flex items-center gap-1 text-sm text-yellow-600 dark:text-yellow-400">
                    <AlertTriangle className="h-4 w-4" />
                    {summary.issues.warnings} Warnings
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Top Issues */}
      {summary && summary.top_issues.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">Top Issues</h2>
          <div className="space-y-2">
            {summary.top_issues.map((issue, idx) => {
              const sev = severityColors[issue.severity] || severityColors.info
              const Icon = sev.icon
              return (
                <div
                  key={idx}
                  className={`flex items-center gap-3 p-3 rounded-lg ${sev.bg}`}
                >
                  <Icon className={`h-5 w-5 ${sev.text}`} />
                  <div className="flex-1">
                    <div className={`font-medium ${sev.text}`}>{issue.check}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">{issue.message}</div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded ${sev.bg} ${sev.text} font-medium uppercase`}>
                    {issue.severity}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Full Results */}
      {fullResults && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <div className="p-4 border-b dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Detailed Results
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Last run: {new Date(fullResults.run_at).toLocaleString('it-IT')}
            </p>
          </div>
          <div className="divide-y dark:divide-gray-700">
            {fullResults.checks.map((check) => {
              const sev = severityColors[check.severity] || severityColors.info
              const Icon = sev.icon
              const isExpanded = expandedChecks.has(check.check_id)

              return (
                <div key={check.check_id} className="p-4">
                  <div
                    className="flex items-center gap-3 cursor-pointer"
                    onClick={() => toggleCheck(check.check_id)}
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-5 w-5 text-gray-400" />
                    ) : (
                      <ChevronRight className="h-5 w-5 text-gray-400" />
                    )}
                    {check.passed ? (
                      <ShieldCheck className="h-5 w-5 text-green-600" />
                    ) : (
                      <Icon className={`h-5 w-5 ${sev.text}`} />
                    )}
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900 dark:text-white">
                          {check.check_name}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded ${categoryColors[check.category] || 'bg-gray-100 text-gray-600'}`}>
                          {check.category}
                        </span>
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">
                        {check.message}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {check.affected_count > 0 && (
                        <span className="text-sm text-gray-500 dark:text-gray-400">
                          {check.affected_count} affected
                        </span>
                      )}
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        check.passed
                          ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                          : `${sev.bg} ${sev.text}`
                      }`}>
                        {check.passed ? 'PASSED' : check.severity.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="mt-3 ml-8 space-y-3">
                      {/* Remediation suggestion */}
                      {check.remediation && (
                        <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                          <div className="flex items-start gap-2">
                            <Lightbulb className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                            <div>
                              <div className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-1">
                                Suggerimenti per la risoluzione:
                              </div>
                              <div className="text-sm text-blue-700 dark:text-blue-400 whitespace-pre-line">
                                {check.remediation}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Affected items */}
                      {check.affected_items.length > 0 && (
                        <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                          <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Elementi interessati ({check.affected_count})
                          </div>
                          <div className="max-h-64 overflow-y-auto">
                            <table className="min-w-full text-sm">
                              <tbody className="divide-y dark:divide-gray-700">
                                {check.affected_items.slice(0, 20).map((item, idx) => (
                                  <tr key={idx} className="text-gray-600 dark:text-gray-400">
                                    <td className="py-1 pr-4 font-mono">
                                      {item.mac_address || item.switch || item.ip_address || item.vlan_id || '-'}
                                    </td>
                                    <td className="py-1 pr-4">
                                      {item.port || item.vendor || item.site_count || ''}
                                    </td>
                                    <td className="py-1">
                                      {item.issue || item.suggestion || item.note ||
                                       (item.locations ? `${item.locations.length} locations` : '')}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            {check.affected_count > 20 && (
                              <div className="text-center text-sm text-gray-500 mt-2">
                                ...e altri {check.affected_count - 20}
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center p-12">
          <RefreshCw className="h-8 w-8 animate-spin text-blue-600" />
          <span className="ml-2 text-gray-600 dark:text-gray-400">Loading...</span>
        </div>
      )}
    </div>
  )
}
