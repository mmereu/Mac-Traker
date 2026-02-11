import { ReactNode, useState, useEffect, useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Search,
  Server,
  FolderCog,
  Network,
  Bell,
  Settings,
  Moon,
  Sun,
  Menu,
  X,
  GitCompare,
  Webhook,
  Users,
  Camera,
  ShieldCheck,
  Route,
} from 'lucide-react'
import clsx from 'clsx'
import { alertsApi } from '../api/client'

interface LayoutProps {
  children: ReactNode
  darkMode: boolean
  toggleDarkMode: () => void
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Ricerca MAC', href: '/mac-search', icon: Search },
  { name: 'Host Table', href: '/hosts', icon: Users },
  { name: 'Snapshots', href: '/snapshots', icon: Camera },
  { name: 'Confronto', href: '/snapshot-compare', icon: GitCompare },
  { name: 'Switch', href: '/switches', icon: Server },
  { name: 'Gruppi', href: '/groups', icon: FolderCog },
  { name: 'Topologia', href: '/topology', icon: Network },
  { name: 'VLAN Table', href: '/vlans', icon: Network },
  { name: 'ARP Table', href: '/arp-table', icon: Network },
  { name: 'Intent Check', href: '/intent', icon: ShieldCheck },
  { name: 'VLAN Check', href: '/vlan-check', icon: ShieldCheck },
  { name: 'Path Sim', href: '/path-sim', icon: Route },
  { name: 'Alert', href: '/alerts', icon: Bell },
  { name: 'Alerting', href: '/alert-config', icon: Webhook },
  { name: 'Impostazioni', href: '/settings', icon: Settings },
]

export default function Layout({ children, darkMode, toggleDarkMode }: LayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const [unreadCount, setUnreadCount] = useState<number>(0)
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false)
  const [quickSearch, setQuickSearch] = useState<string>('')

  // Handle quick search submission
  const handleQuickSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (quickSearch.trim()) {
      navigate(`/mac-search?q=${encodeURIComponent(quickSearch.trim())}`)
      setQuickSearch('')
    } else {
      navigate('/mac-search')
    }
  }

  // Fetch unread count on mount and periodically
  const fetchUnreadCount = useCallback(async () => {
    try {
      const response = await alertsApi.list({})
      setUnreadCount(response.data.unread_count || 0)
    } catch (err) {
      console.error('Error fetching unread count:', err)
    }
  }, [])

  useEffect(() => {
    fetchUnreadCount()
    // Refresh every 30 seconds
    const interval = setInterval(fetchUnreadCount, 30000)
    return () => clearInterval(interval)
  }, [fetchUnreadCount])

  // Also refresh when navigating back from alerts page
  useEffect(() => {
    if (location.pathname !== '/alerts') {
      fetchUnreadCount()
    }
  }, [location.pathname, fetchUnreadCount])

  const handleAlertClick = () => {
    navigate('/alerts')
  }

  // Close sidebar when navigating on mobile
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Skip to main content link for accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        Vai al contenuto principale
      </a>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-50 w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transform transition-transform duration-300 ease-in-out md:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        role="navigation"
        aria-label="Menu principale"
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center">
            <Network className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            <span className="ml-2 text-xl font-semibold text-gray-900 dark:text-white">
              Mac-Traker
            </span>
          </div>
          {/* Close button - mobile only */}
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-2 md:hidden text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Chiudi menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="mt-6 px-3">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href ||
              (item.href !== '/' && location.pathname.startsWith(item.href))
            return (
              <Link
                key={item.name}
                to={item.href}
                className={clsx(
                  'flex items-center px-3 py-2 mt-1 text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800',
                  isActive
                    ? 'bg-blue-50 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                )}
              >
                <item.icon className="h-5 w-5 mr-3" />
                {item.name}
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Main content */}
      <div className="md:pl-64">
        {/* Header */}
        <header className="h-16 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between px-4 md:px-6">
          {/* Left side - hamburger menu on mobile */}
          <div className="flex items-center gap-3">
            {/* Hamburger menu - mobile only */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 md:hidden text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Apri menu"
            >
              <Menu className="h-5 w-5" />
            </button>

            {/* Quick Search */}
            <form onSubmit={handleQuickSearch} className="flex-1 max-w-md hidden sm:block">
              <div className="relative">
                <label htmlFor="header-quick-search" className="sr-only">
                  Cerca MAC address
                </label>
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  id="header-quick-search"
                  type="text"
                  placeholder="Cerca MAC address..."
                  value={quickSearch}
                  onChange={(e) => setQuickSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-gray-100 dark:bg-gray-700 border-0 rounded-lg text-sm text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
                />
              </div>
            </form>
          </div>

          {/* Right side */}
          <div className="flex items-center gap-2 md:gap-4">
            {/* Search button - mobile only */}
            <button
              onClick={() => navigate('/mac-search')}
              className="p-2 sm:hidden text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Cerca MAC"
            >
              <Search className="h-5 w-5" />
            </button>

            {/* Alert badge */}
            <button
              onClick={handleAlertClick}
              className="relative p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
              aria-label={`Visualizza alert${unreadCount > 0 ? ` (${unreadCount} non letti)` : ''}`}
            >
              <Bell className="h-5 w-5" />
              {unreadCount > 0 && (
                <span
                  className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center"
                  aria-label={`${unreadCount} alert non letti`}
                >
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </button>

            {/* Theme toggle */}
            <button
              onClick={toggleDarkMode}
              className="p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
              aria-label={darkMode ? 'Attiva light mode' : 'Attiva dark mode'}
            >
              {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </button>
          </div>
        </header>

        {/* Page content */}
        <main id="main-content" className="p-4 md:p-6" tabIndex={-1}>
          {children}
        </main>

        {/* Footer */}
        <footer className="px-4 md:px-6 py-4 border-t border-gray-200 dark:border-gray-700 text-sm text-gray-500 dark:text-gray-400">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2">
            <span>Mac-Traker v1.0.0</span>
            <span>Ultimo discovery: --</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
