import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import MacSearch from './pages/MacSearch'
import MacDetail from './pages/MacDetail'
import SwitchList from './pages/SwitchList'
import SwitchDetail from './pages/SwitchDetail'
import Groups from './pages/Groups'
import Topology from './pages/Topology'
import Alerts from './pages/Alerts'
import Settings from './pages/Settings'
import SnapshotCompare from './pages/SnapshotCompare'
import AlertConfig from './pages/AlertConfig'
import Hosts from './pages/Hosts'
import Snapshots from './pages/Snapshots'
import VlanTable from './pages/VlanTable'
import ArpTable from './pages/ArpTable'
import IntentVerification from './pages/IntentVerification'
import PathSimulation from './pages/PathSimulation'
import VlanConsistency from './pages/VlanConsistency'
import NotFound from './pages/NotFound'

function App() {
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode')
    return saved ? JSON.parse(saved) : false
  })

  useEffect(() => {
    localStorage.setItem('darkMode', JSON.stringify(darkMode))
    if (darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [darkMode])

  const toggleDarkMode = () => setDarkMode(!darkMode)

  return (
    <BrowserRouter>
      <Layout darkMode={darkMode} toggleDarkMode={toggleDarkMode}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/mac-search" element={<MacSearch />} />
          <Route path="/mac/:id" element={<MacDetail />} />
          <Route path="/switches" element={<SwitchList />} />
          <Route path="/switches/:id" element={<SwitchDetail />} />
          <Route path="/groups" element={<Groups />} />
          <Route path="/topology" element={<Topology />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/snapshot-compare" element={<SnapshotCompare />} />
          <Route path="/snapshots/compare/:id1/:id2" element={<SnapshotCompare />} />
          <Route path="/alert-config" element={<AlertConfig />} />
          <Route path="/hosts" element={<Hosts />} />
          <Route path="/snapshots" element={<Snapshots />} />
          <Route path="/vlans" element={<VlanTable />} />
          <Route path="/vlans/:vlanId" element={<VlanTable />} />
          <Route path="/arp-table" element={<ArpTable />} />
          <Route path="/intent" element={<IntentVerification />} />
          <Route path="/path-sim" element={<PathSimulation />} />
          <Route path="/vlan-check" element={<VlanConsistency />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
