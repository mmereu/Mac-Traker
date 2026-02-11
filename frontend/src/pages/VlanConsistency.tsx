import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

interface VlanMismatch {
  mac_address: string
  vendor: string | null
  vlan_count: number
  vlans: number[]
  locations: { switch: string; port: string; vlan_id: number }[]
  issue: string
}

interface TrunkMismatch {
  link: string
  local_switch: string
  remote_switch: string
  only_on_local: number[]
  only_on_remote: number[]
  common_vlans: number
  issue: string
}

interface CheckResult {
  check_id: string
  check_name: string
  passed: boolean
  message: string
  affected_items: VlanMismatch[] | TrunkMismatch[]
  details?: { total_issues?: number }
}

export default function VlanConsistency() {
  const [vlanCheck, setVlanCheck] = useState<CheckResult | null>(null)
  const [trunkCheck, setTrunkCheck] = useState<CheckResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'vlan' | 'trunk'>('vlan')

  useEffect(() => {
    fetchChecks()
  }, [])

  const fetchChecks = async () => {
    setLoading(true)
    try {
      const [vlanRes, trunkRes] = await Promise.all([
        fetch('/api/intent/run/vlan_consistency', { method: 'POST' }),
        fetch('/api/intent/run/vlan_mismatch_on_trunk', { method: 'POST' })
      ])

      if (vlanRes.ok) setVlanCheck(await vlanRes.json())
      if (trunkRes.ok) setTrunkCheck(await trunkRes.json())
    } catch (err) {
      console.error('Error fetching VLAN checks:', err)
    } finally {
      setLoading(false)
    }
  }

  const vlanMismatches = vlanCheck?.affected_items as VlanMismatch[] || []
  const trunkMismatches = trunkCheck?.affected_items as TrunkMismatch[] || []

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            VLAN Consistency Check
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Verifica coerenza VLAN tra MAC e trunk
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/intent"
            className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            ← Intent Checks
          </Link>
          <button
            onClick={fetchChecks}
            disabled={loading}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Analisi...' : 'Riesegui Check'}
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className={`p-4 rounded-lg border ${
          vlanCheck?.passed
            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
            : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
        }`}>
          <h3 className="font-semibold text-gray-900 dark:text-white">MAC su VLAN diverse</h3>
          <p className="text-2xl font-bold mt-1">
            {vlanMismatches.length} <span className="text-sm font-normal">mismatch</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {vlanCheck?.message || 'Caricamento...'}
          </p>
        </div>

        <div className={`p-4 rounded-lg border ${
          trunkCheck?.passed
            ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
            : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
        }`}>
          <h3 className="font-semibold text-gray-900 dark:text-white">VLAN mismatch su trunk</h3>
          <p className="text-2xl font-bold mt-1">
            {trunkMismatches.length} <span className="text-sm font-normal">link</span>
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {trunkCheck?.message || 'Caricamento...'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700 mb-4">
        <nav className="flex gap-4">
          <button
            onClick={() => setActiveTab('vlan')}
            className={`pb-2 px-1 border-b-2 text-sm font-medium ${
              activeTab === 'vlan'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
            }`}
          >
            MAC su VLAN diverse ({vlanMismatches.length})
          </button>
          <button
            onClick={() => setActiveTab('trunk')}
            className={`pb-2 px-1 border-b-2 text-sm font-medium ${
              activeTab === 'trunk'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
            }`}
          >
            Trunk VLAN mismatch ({trunkMismatches.length})
          </button>
        </nav>
      </div>

      {/* VLAN Tab Content */}
      {activeTab === 'vlan' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">MAC</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Vendor</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">VLANs</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Locations</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {vlanMismatches.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/mac-search?q=${item.mac_address}`}
                      className="font-mono text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      {item.mac_address}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                    {item.vendor || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {item.vlans.map(v => (
                        <span key={v} className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs rounded">
                          VLAN {v}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <div className="space-y-1">
                      {item.locations.slice(0, 3).map((loc, i) => (
                        <div key={i} className="text-gray-600 dark:text-gray-400">
                          {loc.switch}:{loc.port} (VLAN {loc.vlan_id})
                        </div>
                      ))}
                      {item.locations.length > 3 && (
                        <div className="text-gray-400 text-xs">+{item.locations.length - 3} altre</div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {vlanMismatches.length === 0 && !loading && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                    ✓ Nessun MAC su VLAN diverse
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Trunk Tab Content */}
      {activeTab === 'trunk' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Link</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Solo Local</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Solo Remote</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">In comune</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {trunkMismatches.slice(0, 50).map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-gray-900 dark:text-white">{item.local_switch}</div>
                    <div className="text-xs text-gray-500">↔ {item.remote_switch}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {item.only_on_local.slice(0, 5).map(v => (
                        <span key={v} className="px-1.5 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs rounded">
                          {v}
                        </span>
                      ))}
                      {item.only_on_local.length > 5 && (
                        <span className="text-xs text-gray-400">+{item.only_on_local.length - 5}</span>
                      )}
                      {item.only_on_local.length === 0 && <span className="text-xs text-gray-400">-</span>}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {item.only_on_remote.slice(0, 5).map(v => (
                        <span key={v} className="px-1.5 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 text-xs rounded">
                          {v}
                        </span>
                      ))}
                      {item.only_on_remote.length > 5 && (
                        <span className="text-xs text-gray-400">+{item.only_on_remote.length - 5}</span>
                      )}
                      {item.only_on_remote.length === 0 && <span className="text-xs text-gray-400">-</span>}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-center">
                    <span className="px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded">
                      {item.common_vlans}
                    </span>
                  </td>
                </tr>
              ))}
              {trunkMismatches.length > 50 && (
                <tr>
                  <td colSpan={4} className="px-4 py-3 text-center text-gray-500 dark:text-gray-400 text-sm">
                    Mostrati 50 di {trunkMismatches.length} mismatch
                  </td>
                </tr>
              )}
              {trunkMismatches.length === 0 && !loading && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                    ✓ Nessun mismatch VLAN sui trunk
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
