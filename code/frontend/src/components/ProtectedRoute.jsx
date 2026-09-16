import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/** Client-side role gate. This is a UX convenience, not the security
 * boundary -- the real authorization happens server-side per role/id on
 * every endpoint (see docs/SPEC.md §5). It exists so a borrower can't even
 * see a lender-shaped dashboard shell, and so an expired/mismatched session
 * bounces straight to the correct role's login instead of a blank/broken
 * page. */
export default function ProtectedRoute({ role, children }) {
  const { auth, checked } = useAuth()
  const location = useLocation()

  if (!checked) return <div className="loading">Checking session...</div>
  if (!auth || auth.role !== role) {
    return <Navigate to={`/login/${role}`} replace state={{ from: location.pathname }} />
  }
  return children
}
