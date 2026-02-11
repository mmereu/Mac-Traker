import { Link } from 'react-router-dom'
import { Home, AlertTriangle } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <AlertTriangle className="h-16 w-16 mx-auto text-yellow-500 mb-4" />
        <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
          404
        </h1>
        <p className="text-xl text-gray-600 dark:text-gray-400 mb-6">
          Pagina non trovata
        </p>
        <p className="text-gray-500 dark:text-gray-500 mb-8">
          La pagina che stai cercando non esiste o e' stata spostata.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Home className="h-5 w-5" />
          Torna alla Dashboard
        </Link>
      </div>
    </div>
  )
}
