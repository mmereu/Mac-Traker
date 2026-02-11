import { useEffect, useRef, useState } from 'react'
import { RefreshCw, ZoomIn, ZoomOut, X, Network, Search, XCircle, MapPin, Route, CheckCircle, Download, Image, FileCode, Building2 } from 'lucide-react'
import { Network as VisNetwork, DataSet } from 'vis-network/standalone'
import api, { macsApi, EndpointTraceResponse } from '../api/client'

interface TopologyNode {
  id: number
  label: string
  hostname: string
  ip_address: string
  device_type: string
  is_active: boolean
  mac_count: number
  site_code?: string
  x?: number
  y?: number
}

interface TopologyEdge {
  from: number
  to: number
  local_port: string
  remote_port?: string
  protocol: string
}

interface TopologyData {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  last_updated?: string
}

interface SwitchMac {
  mac_address: string
  ip_address: string
  port_name: string
  vlan_id: number
  vendor_name: string
  last_seen: string
}

interface SwitchMacsData {
  switch_id: number
  switch_hostname: string
  mac_count: number
  macs: SwitchMac[]
}

interface MacPathNode {
  switch_id: number
  hostname: string
  ip_address: string
  port_name: string | null
  is_endpoint: boolean
}

interface MacPathData {
  mac_address: string
  ip_address: string | null
  vendor_name: string | null
  endpoint_switch_id: number
  endpoint_switch_hostname: string
  endpoint_port: string
  path: MacPathNode[]
  path_node_ids: number[]
  path_edge_keys: string[]
}

export default function Topology() {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<VisNetwork | null>(null)
  const [topology, setTopology] = useState<TopologyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSwitch, setSelectedSwitch] = useState<TopologyNode | null>(null)
  const [switchMacs, setSwitchMacs] = useState<SwitchMacsData | null>(null)
  const [loadingMacs, setLoadingMacs] = useState(false)

  // MAC path highlighting state
  const [macSearch, setMacSearch] = useState('')
  const [macPath, setMacPath] = useState<MacPathData | null>(null)
  const [loadingPath, setLoadingPath] = useState(false)
  const [pathError, setPathError] = useState<string | null>(null)
  const nodesDataSetRef = useRef<DataSet<any> | null>(null)
  const edgesDataSetRef = useRef<DataSet<any> | null>(null)

  // Endpoint trace state
  const [endpointTrace, setEndpointTrace] = useState<EndpointTraceResponse | null>(null)
  const [loadingTrace, setLoadingTrace] = useState(false)

  // Layout mode state - force only
  const [layoutMode] = useState<'force'>('force')

  // Export dropdown state
  const [showExportMenu, setShowExportMenu] = useState(false)

  // Hop-by-hop navigation state
  const [selectedHopIndex, setSelectedHopIndex] = useState<number | null>(null)

  // Offline graph lookup toggle
  const [useOfflineGraph, setUseOfflineGraph] = useState(true)
  const [graphStats, setGraphStats] = useState<{ node_count: number; edge_count: number; built_at: string | null; is_valid: boolean } | null>(null)

  // Site filter state
  const [siteFilter, setSiteFilter] = useState<string>('')
  const [siteSummary, setSiteSummary] = useState<{ site_code: string; site_name: string; switch_count: number; link_count: number }[]>([])

  // L3 Only filter - show only core/L3 switches
  const [l3Only, setL3Only] = useState(false)

  // Fetch site summary for filter dropdown
  const fetchSiteSummary = async () => {
    try {
      const response = await api.get<{ sites: { site_code: string; site_name: string; switch_count: number; link_count: number }[] }>('/topology/sites-summary')
      const sites = response.data.sites || []
      setSiteSummary(sites)
      // Auto-select first site if no site is selected (prevents loading all 1500+ switches)
      if (sites.length > 0 && !siteFilter) {
        setSiteFilter(sites[0].site_code)
      }
    } catch (err) {
      console.error('Error fetching site summary:', err)
    }
  }

  // Fetch topology data
  const fetchTopology = async (siteCode?: string) => {
    try {
      setLoading(true)
      setError(null)
      const url = siteCode ? `/topology/by-site/${siteCode}` : '/topology'
      const response = await api.get<TopologyData>(url)
      setTopology(response.data)
    } catch (err) {
      console.error('Error fetching topology:', err)
      setError('Errore nel caricamento della topologia')
    } finally {
      setLoading(false)
    }
  }

  // Refresh topology (trigger LLDP discovery)
  const handleRefresh = async () => {
    try {
      setRefreshing(true)
      await api.post('/topology/refresh')
      await fetchTopology()
    } catch (err) {
      console.error('Error refreshing topology:', err)
    } finally {
      setRefreshing(false)
    }
  }

  // Fetch MACs for selected switch
  const fetchSwitchMacs = async (switchId: number) => {
    try {
      setLoadingMacs(true)
      const response = await api.get<SwitchMacsData>(`/topology/switch/${switchId}/macs`)
      setSwitchMacs(response.data)
    } catch (err) {
      console.error('Error fetching switch MACs:', err)
    } finally {
      setLoadingMacs(false)
    }
  }

  // Build/refresh the offline graph
  const buildOfflineGraph = async () => {
    try {
      const response = await api.post<{ node_count: number; edge_count: number; built_at: string | null; is_valid: boolean }>('/graph/build')
      setGraphStats(response.data)
    } catch (err) {
      console.error('Error building offline graph:', err)
    }
  }

  // Fetch graph stats on mount
  useEffect(() => {
    const fetchGraphStats = async () => {
      try {
        const response = await api.get<{ node_count: number; edge_count: number; built_at: string | null; is_valid: boolean }>('/graph/stats')
        setGraphStats(response.data)
      } catch (err) {
        // Graph not built yet
        setGraphStats(null)
      }
    }
    fetchGraphStats()
  }, [])

  // Search for MAC and highlight path
  const searchMacPath = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!macSearch.trim()) return

    try {
      setLoadingPath(true)
      setPathError(null)
      setEndpointTrace(null)

      // Choose API based on toggle
      const pathEndpoint = useOfflineGraph
        ? `/graph/mac/${encodeURIComponent(macSearch.trim())}`
        : `/topology/mac-path/${encodeURIComponent(macSearch.trim())}`

      // SSH trace is PRIMARY source (more accurate, real-time)
      // Database path is FALLBACK only
      // Pass the selected site to traceEndpoint for accurate SSH tracing
      let traceResponse = null
      try {
        traceResponse = await macsApi.traceEndpoint(macSearch.trim(), siteFilter || undefined)
      } catch (traceErr: any) {
        console.log('SSH trace error:', traceErr?.message || traceErr)
        // Will fall through to database fallback
      }

      if (traceResponse?.data && traceResponse.data.endpoint_switch_hostname) {
        // SSH trace succeeded - use it as the source of truth
        setEndpointTrace(traceResponse.data)

        // Build path from SSH trace_path
        const sshPath = traceResponse.data.trace_path || []
        if (sshPath.length > 0) {
          // Find node IDs for switches in the SSH path
          const pathNodeIds: number[] = []
          const pathEdgeKeys: string[] = []

          // Parse trace_path entries like "05_L3_S6730_251:Eth-Trunk23 -> XGigabitEthernet1/0/17"
          for (const step of sshPath) {
            const switchName = step.split(':')[0]
            // Find switch in topology by hostname
            const matchingNode = topology?.nodes.find(n =>
              n.hostname === switchName || n.hostname.includes(switchName)
            )
            if (matchingNode) {
              pathNodeIds.push(matchingNode.id)
            }
          }

          // Build edge keys between consecutive nodes
          for (let i = 0; i < pathNodeIds.length - 1; i++) {
            pathEdgeKeys.push(`${pathNodeIds[i]}-${pathNodeIds[i+1]}`)
            pathEdgeKeys.push(`${pathNodeIds[i+1]}-${pathNodeIds[i]}`)
          }

          // Create macPath object from SSH data
          setMacPath({
            mac_address: traceResponse.data.mac_address,
            ip_address: null,
            vendor_name: traceResponse.data.vendor_name || '',
            endpoint_switch_id: pathNodeIds[pathNodeIds.length - 1] || 0,
            endpoint_switch_hostname: traceResponse.data.endpoint_switch_hostname,
            endpoint_port: traceResponse.data.endpoint_port_name,
            path: sshPath.map((step, idx) => ({
              switch_id: pathNodeIds[idx] || 0,
              hostname: step.split(':')[0],
              ip_address: idx === sshPath.length - 1 ? traceResponse.data.endpoint_switch_ip : '',
              port_name: step.includes(':') ? step.split(':')[1]?.split(' ')[0] || '' : '',
              is_endpoint: idx === sshPath.length - 1
            })),
            path_node_ids: pathNodeIds,
            path_edge_keys: pathEdgeKeys
          })

          // If path has only 1 node (BFS failed / no LLDP links), try frontend BFS
          if (pathNodeIds.length === 1 && topology) {
            let endpointId = pathNodeIds[0]
            // Find core/L3 switch in current topology
            const coreNode = topology.nodes.find(n =>
              n.hostname.includes('L3') || n.hostname.toLowerCase().includes('core')
            )
            // If the single node IS the core switch, try offline graph for the real endpoint
            if (coreNode && coreNode.id === endpointId) {
              try {
                const graphResponse = await api.get<MacPathData>(pathEndpoint)
                if (graphResponse.data?.endpoint_switch_id && graphResponse.data.endpoint_switch_id !== endpointId) {
                  endpointId = graphResponse.data.endpoint_switch_id
                  // Verify this node exists in the current topology
                  const realEndpoint = topology.nodes.find(n => n.id === endpointId)
                  if (!realEndpoint) {
                    endpointId = pathNodeIds[0] // revert if not in topology
                  }
                }
              } catch (graphErr) {
                console.log('Offline graph fallback failed:', graphErr)
              }
            }
            if (coreNode && coreNode.id !== endpointId) {
              // BFS from core to endpoint using topology edges
              const adj: Record<number, number[]> = {}
              for (const edge of topology.edges) {
                if (!adj[edge.from]) adj[edge.from] = []
                if (!adj[edge.to]) adj[edge.to] = []
                adj[edge.from].push(edge.to)
                adj[edge.to].push(edge.from)
              }
              const visited = new Set<number>()
              const parent = new Map<number, number>()
              const queue = [coreNode.id]
              visited.add(coreNode.id)
              let found = false
              while (queue.length > 0) {
                const current = queue.shift()!
                if (current === endpointId) { found = true; break }
                for (const neighbor of (adj[current] || [])) {
                  if (!visited.has(neighbor)) {
                    visited.add(neighbor)
                    parent.set(neighbor, current)
                    queue.push(neighbor)
                  }
                }
              }
              if (found) {
                // Reconstruct path from core to endpoint
                const bfsPath: number[] = []
                let cur = endpointId
                while (cur !== undefined) {
                  bfsPath.unshift(cur)
                  cur = parent.get(cur)!
                  if (cur === coreNode.id) { bfsPath.unshift(cur); break }
                }
                // Build edge keys
                const bfsEdgeKeys: string[] = []
                for (let i = 0; i < bfsPath.length - 1; i++) {
                  bfsEdgeKeys.push(`${bfsPath[i]}-${bfsPath[i+1]}`)
                  bfsEdgeKeys.push(`${bfsPath[i+1]}-${bfsPath[i]}`)
                }
                // Update path data with the fuller BFS path
                pathNodeIds.length = 0
                pathNodeIds.push(...bfsPath)
                pathEdgeKeys.length = 0
                pathEdgeKeys.push(...bfsEdgeKeys)

                // Update macPath with extended path info
                const extendedPath = bfsPath.map((nid, idx) => {
                  const tNode = topology.nodes.find(n => n.id === nid)
                  return {
                    switch_id: nid,
                    hostname: tNode?.hostname || `Switch ${nid}`,
                    ip_address: tNode?.ip_address || '',
                    port_name: idx === bfsPath.length - 1 ? (sshPath[sshPath.length - 1]?.includes(':') ? sshPath[sshPath.length - 1].split(':')[1]?.split(' ')[0] || '' : '') : '',
                    is_endpoint: idx === bfsPath.length - 1
                  }
                })
                setMacPath(prev => prev ? { ...prev, path: extendedPath, path_node_ids: [...bfsPath], path_edge_keys: [...bfsEdgeKeys] } : prev)
              }
            }
          }

          if (pathNodeIds.length > 0) {
            highlightPath(pathNodeIds, pathEdgeKeys)
          }
        } else {
          // SSH trace has endpoint but no trace_path (DB fallback gave empty path)
          // Find the endpoint switch on the map and BFS from core
          const endpointHostname = traceResponse.data.endpoint_switch_hostname
          const endpointNode = topology?.nodes.find(n =>
            n.hostname === endpointHostname || n.hostname.includes(endpointHostname)
          )

          if (endpointNode && topology) {
            const coreNode = topology.nodes.find(n =>
              n.hostname.includes('L3') || n.hostname.toLowerCase().includes('core')
            )

            let pathNodeIds: number[] = [endpointNode.id]
            let pathEdgeKeys: string[] = []

            if (coreNode && coreNode.id !== endpointNode.id) {
              // BFS from core to endpoint
              const adj: Record<number, number[]> = {}
              for (const edge of topology.edges) {
                if (!adj[edge.from]) adj[edge.from] = []
                if (!adj[edge.to]) adj[edge.to] = []
                adj[edge.from].push(edge.to)
                adj[edge.to].push(edge.from)
              }
              const visited = new Set<number>()
              const parent = new Map<number, number>()
              const queue = [coreNode.id]
              visited.add(coreNode.id)
              let found = false
              while (queue.length > 0) {
                const current = queue.shift()!
                if (current === endpointNode.id) { found = true; break }
                for (const neighbor of (adj[current] || [])) {
                  if (!visited.has(neighbor)) {
                    visited.add(neighbor)
                    parent.set(neighbor, current)
                    queue.push(neighbor)
                  }
                }
              }
              if (found) {
                const bfsPath: number[] = []
                let cur = endpointNode.id
                while (cur !== undefined) {
                  bfsPath.unshift(cur)
                  cur = parent.get(cur)!
                  if (cur === coreNode.id) { bfsPath.unshift(cur); break }
                }
                pathNodeIds = bfsPath
                for (let i = 0; i < bfsPath.length - 1; i++) {
                  pathEdgeKeys.push(`${bfsPath[i]}-${bfsPath[i+1]}`)
                  pathEdgeKeys.push(`${bfsPath[i+1]}-${bfsPath[i]}`)
                }
              }
            }

            // Build macPath for the hop-by-hop panel
            const pathData = pathNodeIds.map((nid, idx) => {
              const tNode = topology.nodes.find(n => n.id === nid)
              return {
                switch_id: nid,
                hostname: tNode?.hostname || `Switch ${nid}`,
                ip_address: tNode?.ip_address || '',
                port_name: idx === pathNodeIds.length - 1 ? (traceResponse.data.endpoint_port_name || '') : '',
                is_endpoint: idx === pathNodeIds.length - 1
              }
            })
            setMacPath({
              mac_address: traceResponse.data.mac_address,
              ip_address: null,
              vendor_name: traceResponse.data.vendor_name || '',
              endpoint_switch_id: endpointNode.id,
              endpoint_switch_hostname: endpointHostname,
              endpoint_port: traceResponse.data.endpoint_port_name || '',
              path: pathData,
              path_node_ids: pathNodeIds,
              path_edge_keys: pathEdgeKeys
            })

            highlightPath(pathNodeIds, pathEdgeKeys)
          } else {
            setMacPath(null)
          }
        }
      } else {
        // SSH trace failed - try database as fallback
        console.log('SSH trace failed, trying database fallback...')
        const pathResponse = await api.get<MacPathData>(pathEndpoint)
        if (pathResponse.data) {
          setMacPath(pathResponse.data)
          highlightPath(pathResponse.data.path_node_ids, pathResponse.data.path_edge_keys)
          setEndpointTrace(null)
        } else {
          setPathError('MAC non trovato nella topologia')
          setMacPath(null)
          clearHighlight()
        }
      }
    } catch (err: any) {
      console.error('Error searching MAC path:', err)
      setPathError(err.response?.data?.detail || 'MAC non trovato')
      setMacPath(null)
      clearHighlight()
    } finally {
      setLoadingPath(false)
    }
  }

  // Highlight path nodes and edges in the network
  const highlightPath = (nodeIds: number[], edgeKeys: string[]) => {
    if (!nodesDataSetRef.current || !edgesDataSetRef.current || !topology) return

    const nodeIdSet = new Set(nodeIds)

    // Update all nodes - highlighted nodes get circularImage with prominent border
    const nodeUpdates = topology.nodes.map(node => {
      const isInPath = nodeIdSet.has(node.id)
      if (isInPath) {
        return {
          id: node.id,
          shape: 'circularImage',
          image: node.device_type === 'huawei'
            ? 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMzYjgyZjYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIyIiB5PSI2IiB3aWR0aD0iMjAiIGhlaWdodD0iMTIiIHJ4PSIyIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjEyIiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjEyIiByPSIxLjUiLz48bGluZSB4MT0iMTAiIHkxPSIxMiIgeDI9IjE0IiB5Mj0iMTIiLz48L3N2Zz4='
            : 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMxMGI5ODEiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIyIiB5PSI2IiB3aWR0aD0iMjAiIGhlaWdodD0iMTIiIHJ4PSIyIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjEyIiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjEyIiByPSIxLjUiLz48bGluZSB4MT0iMTAiIHkxPSIxMiIgeDI9IjE0IiB5Mj0iMTIiLz48L3N2Zz4=',
          size: 45,
          color: {
            border: '#f59e0b',
            background: '#fef3c7',
          },
          borderWidth: 6,
          shadow: { enabled: true, color: 'rgba(245, 158, 11, 0.6)', size: 20, x: 0, y: 0 },
          font: { color: '#92400e', size: 13, face: 'system-ui', bold: { color: '#92400e' } },
        }
      } else {
        // Dim non-path nodes for contrast
        return {
          id: node.id,
          color: {
            border: node.is_active ? '#d1d5db' : '#fca5a5',
            background: '#f9fafb',
          },
          borderWidth: 1,
          shadow: false,
          font: { color: '#9ca3af', size: 11, face: 'system-ui' },
          opacity: 0.5,
        }
      }
    })
    nodesDataSetRef.current.update(nodeUpdates)

    // Highlight edges in the path
    const edgeKeySet = new Set(edgeKeys)
    const edgeUpdates: any[] = []
    edgesDataSetRef.current.forEach((edge: any) => {
      const edgeKey1 = `${edge.from}-${edge.to}`
      const edgeKey2 = `${edge.to}-${edge.from}`
      const isInPath = edgeKeySet.has(edgeKey1) || edgeKeySet.has(edgeKey2)
      edgeUpdates.push({
        id: edge.id,
        color: { color: isInPath ? '#f59e0b' : '#e5e7eb', highlight: '#3b82f6' },
        width: isInPath ? 5 : 1,
        shadow: isInPath ? { enabled: true, color: 'rgba(245, 158, 11, 0.4)', size: 8 } : false,
      })
    })
    edgesDataSetRef.current.update(edgeUpdates)

    // Focus on the highlighted path with appropriate zoom
    if (networkRef.current && nodeIds.length > 0) {
      if (nodeIds.length <= 2) {
        // For 1-2 nodes, use focus for better zoom
        networkRef.current.focus(nodeIds[0], {
          scale: 1.8,
          animation: {
            duration: 600,
            easingFunction: 'easeInOutQuad'
          }
        })
      } else {
        networkRef.current.fit({
          nodes: nodeIds,
          animation: {
            duration: 600,
            easingFunction: 'easeInOutQuad'
          }
        })
      }
    }
  }

  // Clear path highlighting - restore original shape and style
  const clearHighlight = () => {
    if (!nodesDataSetRef.current || !edgesDataSetRef.current || !topology) return

    // Reset all nodes to default style (restore shape: 'image' from circularImage)
    const nodeUpdates = topology.nodes.map(node => ({
      id: node.id,
      shape: 'image',
      image: node.device_type === 'huawei'
        ? 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMzYjgyZjYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIyIiB5PSI2IiB3aWR0aD0iMjAiIGhlaWdodD0iMTIiIHJ4PSIyIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjEyIiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjEyIiByPSIxLjUiLz48bGluZSB4MT0iMTAiIHkxPSIxMiIgeDI9IjE0IiB5Mj0iMTIiLz48L3N2Zz4='
        : 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMxMGI5ODEiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIyIiB5PSI2IiB3aWR0aD0iMjAiIGhlaWdodD0iMTIiIHJ4PSIyIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjEyIiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjEyIiByPSIxLjUiLz48bGluZSB4MT0iMTAiIHkxPSIxMiIgeDI9IjE0IiB5Mj0iMTIiLz48L3N2Zz4=',
      size: 30,
      color: {
        border: node.is_active ? '#3b82f6' : '#ef4444',
        background: '#ffffff',
      },
      borderWidth: 2,
      shadow: true,
      font: { color: '#374151', size: 12, face: 'system-ui' },
      opacity: 1.0,
    }))
    nodesDataSetRef.current.update(nodeUpdates)

    // Reset all edges to default style
    const edgeUpdates: any[] = []
    edgesDataSetRef.current.forEach((edge: any) => {
      edgeUpdates.push({
        id: edge.id,
        color: { color: '#9ca3af', highlight: '#3b82f6' },
        width: 2,
        shadow: true,
      })
    })
    edgesDataSetRef.current.update(edgeUpdates)
  }

  // Clear MAC search
  const clearMacSearch = () => {
    setMacSearch('')
    setMacPath(null)
    setPathError(null)
    setEndpointTrace(null)
    setSelectedHopIndex(null)
    clearHighlight()
  }

  // Close export menu on outside click
  useEffect(() => {
    const handleClickOutside = () => setShowExportMenu(false)
    if (showExportMenu) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [showExportMenu])

  // Initialize - fetch site summary first, topology will be loaded when site is selected
  useEffect(() => {
    fetchSiteSummary()
  }, [])

  // Re-fetch topology when site filter changes (only if a site is selected)
  useEffect(() => {
    if (siteFilter) {
      fetchTopology(siteFilter)
    }
  }, [siteFilter])

  useEffect(() => {
    if (!containerRef.current || !topology || topology.nodes.length === 0) return

    // Filter nodes based on L3 Only toggle
    const filteredNodes = l3Only
      ? topology.nodes.filter(node => node.hostname.includes('L3') || node.hostname.includes('Core') || node.hostname.includes('core'))
      : topology.nodes

    // Get IDs of filtered nodes for edge filtering
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id))

    // Create vis.js datasets
    const nodes = new DataSet(
      filteredNodes.map(node => ({
        id: node.id,
        label: `${node.hostname}\n(${node.mac_count} MAC)`,
        title: `${node.hostname}\nIP: ${node.ip_address}\nTipo: ${node.device_type}\nMAC: ${node.mac_count}`,
        shape: 'image',
        image: node.device_type === 'huawei'
          ? 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMzYjgyZjYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIyIiB5PSI2IiB3aWR0aD0iMjAiIGhlaWdodD0iMTIiIHJ4PSIyIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjEyIiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjEyIiByPSIxLjUiLz48bGluZSB4MT0iMTAiIHkxPSIxMiIgeDI9IjE0IiB5Mj0iMTIiLz48L3N2Zz4='
          : 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMxMGI5ODEiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIyIiB5PSI2IiB3aWR0aD0iMjAiIGhlaWdodD0iMTIiIHJ4PSIyIi8+PGNpcmNsZSBjeD0iNiIgY3k9IjEyIiByPSIxLjUiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjEyIiByPSIxLjUiLz48bGluZSB4MT0iMTAiIHkxPSIxMiIgeDI9IjE0IiB5Mj0iMTIiLz48L3N2Zz4=',
        size: 30,
        color: {
          border: node.is_active ? '#3b82f6' : '#ef4444',
          background: '#ffffff',
        },
        font: {
          color: '#374151',
          size: 12,
          face: 'system-ui',
        },
      }))
    )
    // Store reference for highlighting
    nodesDataSetRef.current = nodes

    // Filter edges based on L3 Only toggle - only edges between filtered nodes
    const filteredEdges = l3Only
      ? topology.edges.filter(edge => filteredNodeIds.has(edge.from) && filteredNodeIds.has(edge.to))
      : topology.edges

    // Count edges per node to identify hub nodes
    const nodeEdgeCount: Record<number, number> = {}
    filteredEdges.forEach((edge) => {
      nodeEdgeCount[edge.from] = (nodeEdgeCount[edge.from] || 0) + 1
      nodeEdgeCount[edge.to] = (nodeEdgeCount[edge.to] || 0) + 1
    })

    // Count edges between same node pairs to handle multiple links
    const edgePairCount: Record<string, number> = {}
    const edgePairIndex: Record<string, number> = {}

    filteredEdges.forEach((edge) => {
      const pairKey = [Math.min(edge.from, edge.to), Math.max(edge.from, edge.to)].join('-')
      edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
    })

    const edges = new DataSet(
      filteredEdges.map((edge, index) => {
        const pairKey = [Math.min(edge.from, edge.to), Math.max(edge.from, edge.to)].join('-')
        const totalEdges = edgePairCount[pairKey]
        const currentIndex = edgePairIndex[pairKey] || 0
        edgePairIndex[pairKey] = currentIndex + 1

        // Check if either node is a hub (many connections)
        const isHubConnection = nodeEdgeCount[edge.from] > 3 || nodeEdgeCount[edge.to] > 3

        // Calculate curve for edges - more curve for hub connections
        let smoothConfig: any
        if (totalEdges > 1) {
          // Multiple edges between same nodes - spread them out
          const offset = (currentIndex - (totalEdges - 1) / 2) * 0.4
          smoothConfig = {
            enabled: true,
            type: 'curvedCW',
            roundness: 0.25 + offset,
          }
        } else if (isHubConnection) {
          // Single edge to/from hub - use slight curve based on index
          smoothConfig = {
            enabled: true,
            type: index % 2 === 0 ? 'curvedCW' : 'curvedCCW',
            roundness: 0.15 + (index % 5) * 0.05,
          }
        } else {
          // Regular edge - straight or minimal curve
          smoothConfig = {
            enabled: true,
            type: 'dynamic',
          }
        }

        return {
          id: index,
          from: edge.from,
          to: edge.to,
          label: `${edge.local_port} ↔ ${edge.remote_port || '?'}`,
          title: `Locale: ${edge.local_port}\nRemoto: ${edge.remote_port || 'N/A'}\nProtocollo: ${edge.protocol.toUpperCase()}`,
          color: { color: '#9ca3af', highlight: '#3b82f6' },
          width: 2,
          font: { color: '#6b7280', size: 10, align: 'middle' },
          smooth: smoothConfig,
        }
      })
    )
    // Store reference for highlighting
    edgesDataSetRef.current = edges

    // Force-directed layout physics
    const forcePhysics = {
      enabled: true,
      barnesHut: {
        gravitationalConstant: -8000,    // Strong repulsion to spread nodes
        centralGravity: 0.1,             // Light pull to center
        springLength: 250,               // Longer edges
        springConstant: 0.02,            // Softer springs
        damping: 0.3,                    // Faster stabilization
        avoidOverlap: 1,                 // Prevent overlapping
      },
      stabilization: {
        enabled: true,
        iterations: 500,
        updateInterval: 25,
        fit: true,
      },
      minVelocity: 0.75,                 // Stop earlier for stability
    }

    const options = {
      nodes: {
        borderWidth: 2,
        shadow: true,
        margin: 10,
      },
      edges: {
        shadow: true,
        smooth: {
          enabled: true,
          type: 'curvedCW',
          roundness: 0.3,
          forceDirection: 'none',
        },
        length: 250,
      },
      layout: {
        improvedLayout: true,
        hierarchical: { enabled: false },
      },
      physics: forcePhysics,
      interaction: {
        hover: true,
        tooltipDelay: 200,
        navigationButtons: false,
        keyboard: true,
        dragNodes: true,             // Allow manual repositioning
        dragView: true,
        zoomView: true,
        multiselect: false,
      },
    }

    // Create network
    const network = new VisNetwork(containerRef.current, { nodes, edges }, options)
    networkRef.current = network

    // Handle node click
    network.on('click', (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0]
        const node = topology.nodes.find(n => n.id === nodeId)
        if (node) {
          setSelectedSwitch(node)
          fetchSwitchMacs(node.id)
        }
      } else {
        setSelectedSwitch(null)
        setSwitchMacs(null)
      }
    })

    return () => {
      network.destroy()
    }
  }, [topology, layoutMode, l3Only])

  const handleZoomIn = () => {
    if (networkRef.current) {
      const scale = networkRef.current.getScale()
      networkRef.current.moveTo({ scale: scale * 1.2 })
    }
  }

  const handleZoomOut = () => {
    if (networkRef.current) {
      const scale = networkRef.current.getScale()
      networkRef.current.moveTo({ scale: scale / 1.2 })
    }
  }

  // Export topology as PNG
  const exportAsPng = () => {
    if (!networkRef.current) return
    try {
      const canvas = (networkRef.current as any).canvas.frame.canvas
      const dataUrl = canvas.toDataURL('image/png')
      const link = document.createElement('a')
      link.download = `topology-${new Date().toISOString().slice(0,10)}.png`
      link.href = dataUrl
      link.click()
      setShowExportMenu(false)
    } catch (err) {
      console.error('Export PNG failed:', err)
    }
  }

  // Export topology as SVG (via canvas conversion)
  const exportAsSvg = () => {
    if (!networkRef.current || !topology) return
    try {
      // Create SVG from network data
      const positions = networkRef.current.getPositions()
      const scale = networkRef.current.getScale()
      const viewPosition = networkRef.current.getViewPosition()

      // Calculate bounding box
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      Object.values(positions).forEach((pos: any) => {
        minX = Math.min(minX, pos.x)
        minY = Math.min(minY, pos.y)
        maxX = Math.max(maxX, pos.x)
        maxY = Math.max(maxY, pos.y)
      })

      const padding = 100
      const width = maxX - minX + padding * 2
      const height = maxY - minY + padding * 2

      let svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <style>
    .node-label { font: 12px system-ui; fill: #374151; }
    .edge-label { font: 10px system-ui; fill: #6b7280; }
  </style>
  <rect width="100%" height="100%" fill="white"/>
  <g transform="translate(${padding - minX}, ${padding - minY})">`

      // Draw edges
      topology.edges.forEach(edge => {
        const from = positions[edge.from]
        const to = positions[edge.to]
        if (from && to) {
          svg += `
    <line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" stroke="#9ca3af" stroke-width="2"/>
    <text x="${(from.x + to.x) / 2}" y="${(from.y + to.y) / 2 - 5}" class="edge-label" text-anchor="middle">${edge.local_port} ↔ ${edge.remote_port || '?'}</text>`
        }
      })

      // Draw nodes
      topology.nodes.forEach(node => {
        const pos = positions[node.id]
        if (pos) {
          const color = node.is_active ? '#3b82f6' : '#ef4444'
          svg += `
    <circle cx="${pos.x}" cy="${pos.y}" r="25" fill="white" stroke="${color}" stroke-width="2"/>
    <text x="${pos.x}" y="${pos.y + 40}" class="node-label" text-anchor="middle">${node.hostname}</text>
    <text x="${pos.x}" y="${pos.y + 52}" class="node-label" text-anchor="middle" font-size="10">(${node.mac_count} MAC)</text>`
        }
      })

      svg += `
  </g>
</svg>`

      const blob = new Blob([svg], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.download = `topology-${new Date().toISOString().slice(0,10)}.svg`
      link.href = url
      link.click()
      URL.revokeObjectURL(url)
      setShowExportMenu(false)
    } catch (err) {
      console.error('Export SVG failed:', err)
    }
  }

  // Navigate to specific hop in path
  const navigateToHop = (hopIndex: number) => {
    if (!macPath || !networkRef.current) return
    setSelectedHopIndex(hopIndex)
    const nodeId = macPath.path_node_ids[hopIndex]

    // Focus on the selected node
    networkRef.current.focus(nodeId, {
      scale: 1.5,
      animation: {
        duration: 400,
        easingFunction: 'easeInOutQuad'
      }
    })

    // Highlight only this node more prominently (keep circularImage shape)
    if (nodesDataSetRef.current) {
      const updates = macPath.path_node_ids.map((id, i) => ({
        id,
        shape: 'circularImage',
        size: i === hopIndex ? 50 : 45,
        borderWidth: i === hopIndex ? 8 : 6,
        color: {
          border: i === hopIndex ? '#dc2626' : '#f59e0b',
          background: i === hopIndex ? '#fef2f2' : '#fef3c7',
        },
        shadow: { enabled: true, color: i === hopIndex ? 'rgba(220, 38, 38, 0.6)' : 'rgba(245, 158, 11, 0.5)', size: i === hopIndex ? 25 : 20, x: 0, y: 0 }
      }))
      nodesDataSetRef.current.update(updates)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
          Mappa Topologia
        </h1>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Aggiornamento...' : 'Aggiorna Topologia'}
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 p-4 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={handleZoomIn}
            className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            aria-label="Ingrandisci mappa"
            title="Zoom In"
          >
            <ZoomIn className="h-5 w-5" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            aria-label="Riduci mappa"
            title="Zoom Out"
          >
            <ZoomOut className="h-5 w-5" />
          </button>

          {/* Export Dropdown */}
          <div className="relative">
            <button
              onClick={(e) => { e.stopPropagation(); setShowExportMenu(!showExportMenu) }}
              className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg flex items-center gap-1"
              title="Esporta topologia"
            >
              <Download className="h-5 w-5" />
            </button>
            {showExportMenu && (
              <div
                className="absolute top-full left-0 mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-10 min-w-[140px]"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={exportAsPng}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-t-lg"
                >
                  <Image className="h-4 w-4" />
                  Esporta PNG
                </button>
                <button
                  onClick={exportAsSvg}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-b-lg"
                >
                  <FileCode className="h-4 w-4" />
                  Esporta SVG
                </button>
              </div>
            )}
          </div>

          {/* Site Filter */}
          <div className="ml-4 border-l border-gray-200 dark:border-gray-600 pl-4 flex items-center gap-2">
            <Building2 className="h-4 w-4 text-gray-400" />
            <select
              value={siteFilter}
              onChange={(e) => setSiteFilter(e.target.value)}
              className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white px-2 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              aria-label="Filtra per sede"
            >
              {siteSummary.map(site => (
                <option key={site.site_code} value={site.site_code}>
                  {site.site_name} ({site.switch_count} switch)
                </option>
              ))}
            </select>

            {/* L3 Only Toggle */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={l3Only}
                onChange={(e) => setL3Only(e.target.checked)}
                className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500 border-gray-300 dark:border-gray-600"
              />
              <span className="text-sm text-gray-600 dark:text-gray-400">L3 Only</span>
            </label>
          </div>

          {/* MAC Path Search */}
          <div className="ml-4 border-l border-gray-200 dark:border-gray-600 pl-4 flex items-center gap-2">
            <form onSubmit={searchMacPath} className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  value={macSearch}
                  onChange={(e) => setMacSearch(e.target.value)}
                  placeholder="Cerca MAC (es. 00:0C:29:...)"
                  className="pl-9 pr-8 py-1.5 w-56 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                  aria-label="Cerca MAC address per evidenziare percorso"
                />
                {macSearch && (
                  <button
                    type="button"
                    onClick={clearMacSearch}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    aria-label="Cancella ricerca"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                )}
              </div>
              <button
                type="submit"
                disabled={!macSearch.trim() || loadingPath}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                title="Evidenzia percorso MAC"
              >
                <MapPin className="h-4 w-4" />
                {loadingPath ? 'Cercando...' : 'Percorso'}
              </button>
            </form>

            {/* Offline Graph Toggle */}
            <div className="flex items-center gap-2 ml-2">
              <label className="flex items-center gap-1.5 cursor-pointer" title="Usa grafo pre-calcolato (più veloce, no SSH)">
                <input
                  type="checkbox"
                  checked={useOfflineGraph}
                  onChange={(e) => setUseOfflineGraph(e.target.checked)}
                  className="w-4 h-4 text-green-600 bg-gray-100 border-gray-300 rounded focus:ring-green-500 dark:bg-gray-700 dark:border-gray-600"
                />
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Offline
                </span>
              </label>
              {graphStats && (
                <span className="text-xs text-gray-400" title={`Grafo: ${graphStats.node_count} nodi, ${graphStats.edge_count} archi${graphStats.built_at ? ` - ${new Date(graphStats.built_at).toLocaleString('it-IT')}` : ''}`}>
                  {graphStats.is_valid ? '✓' : '⚠'}
                </span>
              )}
              <button
                type="button"
                onClick={buildOfflineGraph}
                className="text-xs text-blue-500 hover:text-blue-700 underline"
                title="Ricostruisci grafo offline"
              >
                Rebuild
              </button>
            </div>
          </div>

          <div className="ml-auto text-sm text-gray-500 dark:text-gray-400">
            {topology && topology.nodes.length > 0 ? (
              <span>
                {siteFilter && <span className="text-blue-600 dark:text-blue-400 font-medium">Sede {siteFilter}: </span>}
                {topology.nodes.length} switch, {topology.edges.length} collegamenti
                {topology.last_updated && ` - Aggiornato: ${new Date(topology.last_updated).toLocaleString('it-IT')}`}
              </span>
            ) : (
              'Usa il mouse per pan e zoom sulla mappa'
            )}
          </div>
        </div>

        {/* MAC Path Result Info */}
        {(macPath || pathError || endpointTrace) && (
          <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-amber-50 dark:bg-amber-900/20">
            {pathError ? (
              <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                <XCircle className="h-5 w-5" />
                <span>{pathError}</span>
              </div>
            ) : (
              <div className="space-y-3">
                {/* MAC Info Row */}
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-5 w-5 text-amber-600" />
                    <span className="font-semibold text-gray-900 dark:text-white">MAC:</span>
                    <span className="font-mono text-amber-700 dark:text-amber-400">{macPath?.mac_address || endpointTrace?.mac_address}</span>
                    {(macPath?.vendor_name || endpointTrace?.vendor_name) && (
                      <span className="text-gray-500 dark:text-gray-400">({macPath?.vendor_name || endpointTrace?.vendor_name})</span>
                    )}
                  </div>
                  <button
                    onClick={clearMacSearch}
                    className="ml-auto text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    aria-label="Chiudi percorso"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Endpoint Trace Info */}
                {endpointTrace && (
                  <div className="flex flex-wrap items-center gap-4 pl-7">
                    <div className="flex items-center gap-2">
                      <Route className="h-4 w-4 text-purple-600" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Endpoint Fisico:</span>
                      {endpointTrace.is_endpoint ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                          <CheckCircle className="h-3 w-3" />
                          Connessione diretta
                        </span>
                      ) : (
                        <span className="text-sm text-gray-600 dark:text-gray-300">
                          {endpointTrace.endpoint_switch_hostname} → <span className="font-mono">{endpointTrace.endpoint_port_name}</span>
                        </span>
                      )}
                    </div>
                    {endpointTrace.vlan_id && (
                      <span className="text-sm text-gray-500 dark:text-gray-400">VLAN {endpointTrace.vlan_id}</span>
                    )}
                  </div>
                )}

                {/* Interactive hop-by-hop path visualization */}
                {macPath && (
                  <div className="pl-7">
                    <div className="flex items-center gap-2 mb-2">
                      <Route className="h-4 w-4 text-amber-600" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Percorso Hop-by-Hop (clicca per navigare):</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      {macPath.path.map((n, i) => (
                        <div key={i} className="flex items-center">
                          <button
                            onClick={() => navigateToHop(i)}
                            className={`
                              px-3 py-1.5 rounded-lg text-sm font-medium transition-all
                              ${selectedHopIndex === i
                                ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 ring-2 ring-red-500 shadow-md'
                                : n.is_endpoint
                                  ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 hover:ring-2 hover:ring-green-400'
                                  : 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 hover:ring-2 hover:ring-amber-400'
                              }
                            `}
                            title={`${n.hostname}\nIP: ${n.ip_address}\n${n.port_name ? 'Porta: ' + n.port_name : ''}\nClicca per navigare`}
                          >
                            <span className="font-mono text-xs text-gray-400 mr-1">#{i + 1}</span>
                            {n.hostname}
                            {n.port_name && (
                              <span className="font-mono text-xs ml-1 opacity-70">:{n.port_name}</span>
                            )}
                            {n.is_endpoint && (
                              <CheckCircle className="inline-block h-3 w-3 ml-1" />
                            )}
                          </button>
                          {i < macPath.path.length - 1 && (
                            <span className="text-gray-400 mx-1 text-lg">→</span>
                          )}
                        </div>
                      ))}
                    </div>
                    {selectedHopIndex !== null && macPath.path[selectedHopIndex] && (
                      <div className="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded-lg text-sm">
                        <div className="font-medium text-red-700 dark:text-red-300">
                          Hop #{selectedHopIndex + 1}: {macPath.path[selectedHopIndex].hostname}
                        </div>
                        <div className="text-gray-600 dark:text-gray-400">
                          IP: {macPath.path[selectedHopIndex].ip_address}
                          {macPath.path[selectedHopIndex].port_name && (
                            <span> | Porta: <span className="font-mono">{macPath.path[selectedHopIndex].port_name}</span></span>
                          )}
                          {macPath.path[selectedHopIndex].is_endpoint && (
                            <span className="ml-2 text-green-600 dark:text-green-400 font-medium">✓ Endpoint finale</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Map Container */}
        <div className="relative">
          {loading ? (
            <div className="h-[600px] flex items-center justify-center">
              <div className="text-center">
                <Network className="h-12 w-12 text-gray-400 mx-auto mb-4 animate-pulse" />
                <p className="text-gray-500 dark:text-gray-400">Caricamento topologia...</p>
              </div>
            </div>
          ) : error ? (
            <div className="h-[600px] flex items-center justify-center">
              <div className="text-center text-red-500">
                <p className="text-lg mb-2">{error}</p>
                <button
                  onClick={fetchTopology}
                  className="text-blue-600 hover:underline"
                >
                  Riprova
                </button>
              </div>
            </div>
          ) : topology && topology.nodes.length === 0 ? (
            <div className="h-[600px] flex items-center justify-center text-gray-500 dark:text-gray-400">
              <div className="text-center">
                <Network className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-lg mb-2">Nessuno switch configurato</p>
                <p className="text-sm">Aggiungi degli switch per visualizzare la topologia</p>
              </div>
            </div>
          ) : (
            <div
              ref={containerRef}
              className="h-[600px]"
            />
          )}

          {/* Switch Detail Panel */}
          {selectedSwitch && (
            <div className="absolute top-4 right-4 w-80 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="font-semibold text-gray-900 dark:text-white">
                  {selectedSwitch.hostname}
                </h3>
                <button
                  onClick={() => {
                    setSelectedSwitch(null)
                    setSwitchMacs(null)
                  }}
                  className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  aria-label="Chiudi pannello dettagli"
                  title="Chiudi"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="p-4">
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">IP:</span>
                    <span className="font-mono text-gray-900 dark:text-white">{selectedSwitch.ip_address}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Tipo:</span>
                    <span className="capitalize text-gray-900 dark:text-white">{selectedSwitch.device_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Stato:</span>
                    <span className={selectedSwitch.is_active ? 'text-green-600' : 'text-red-600'}>
                      {selectedSwitch.is_active ? 'Attivo' : 'Inattivo'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">MAC Count:</span>
                    <span className="font-semibold text-gray-900 dark:text-white">{selectedSwitch.mac_count}</span>
                  </div>
                </div>

                {/* MAC List */}
                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    MAC Addresses ({switchMacs?.mac_count || 0})
                  </h4>
                  {loadingMacs ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400">Caricamento...</p>
                  ) : switchMacs && switchMacs.macs.length > 0 ? (
                    <div className="max-h-48 overflow-y-auto space-y-2">
                      {switchMacs.macs.slice(0, 10).map((mac, index) => (
                        <div
                          key={index}
                          className="text-xs bg-gray-50 dark:bg-gray-700 rounded p-2"
                        >
                          <div className="font-mono text-blue-600 dark:text-blue-400">
                            {mac.mac_address}
                          </div>
                          <div className="text-gray-500 dark:text-gray-400 mt-1">
                            {mac.ip_address || 'N/A'} - {mac.port_name} - VLAN {mac.vlan_id}
                          </div>
                          {mac.vendor_name && (
                            <div className="text-gray-400 dark:text-gray-500">
                              {mac.vendor_name}
                            </div>
                          )}
                        </div>
                      ))}
                      {switchMacs.macs.length > 10 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
                          +{switchMacs.macs.length - 10} altri MAC
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500 dark:text-gray-400">Nessun MAC trovato</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
