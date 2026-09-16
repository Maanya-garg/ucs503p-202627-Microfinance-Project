const BASE = import.meta.env.VITE_API_BASE || ''

async function request(path, options = {}) {
  const { headers, token, ...rest } = options
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders, ...headers },
    ...rest,
  })
  if (!res.ok) {
    let detail = res.statusText
    let body = null
    try {
      body = await res.json()
      const d = body.detail !== undefined ? body.detail : body
      detail = typeof d === 'string' ? d : JSON.stringify(d)
    } catch {
      // ignore -- fall back to statusText
    }
    const err = new Error(`${res.status} ${detail}`)
    // Structured error bodies (e.g. payments' insufficient_funds shape) are
    // exposed here so callers don't need to regex-parse err.message.
    err.status = res.status
    err.body = body && (body.detail !== undefined ? body.detail : body)
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

// role: 'borrower' | 'lender' | 'shg' | 'admin'. Borrower auth paths are the
// pre-existing, unprefixed ones; the other three roles are new and live
// under /api/auth/{role}/*, per API_CONTRACT.md section 1.
const authPath = (role, action) => (role === 'borrower' ? `/api/auth/${action}` : `/api/auth/${role}/${action}`)

export const api = {
  // ---------------------------------------------------------------- auth
  authLogin: (role, body) => request(authPath(role, 'login'), { method: 'POST', body: JSON.stringify(body) }),
  authMe: (role, token) => request(authPath(role, 'me'), { token }),
  authLogout: (role, token) => request(authPath(role, 'logout'), { method: 'POST', token }),

  // ----------------------------------------------------------- dashboard
  dashboardSummary: (token) => request('/api/dashboard/summary', { token }),
  homeHighlights: () => request('/api/dashboard/home-highlights'),
  modelHealth: (token) => request('/api/admin/model-health', { token }),

  // ---------------------------------------------------------- individuals
  listIndividuals: (params = {}, token) => {
    const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    return request(`/api/individuals?${new URLSearchParams(clean)}`, { token })
  },
  getIndividual: (id, token) => request(`/api/individuals/${id}`, { token }),
  scoreHistory: (id, token) => request(`/api/individuals/${id}/score-history`, { token }),
  recomputeScore: (id, token) => request(`/api/individuals/${id}/recompute-score`, { method: 'POST', token }),
  suggestedLenders: (id, token) => request(`/api/individuals/${id}/suggested-lenders`, { token }),

  // ----------------------------------------------------------------- shgs
  listShgs: (params = {}, token) => request(`/api/shgs?${new URLSearchParams(params)}`, { token }),
  getShg: (id, token) => request(`/api/shgs/${id}`, { token }),
  shgLenders: (id, token) => request(`/api/shgs/${id}/lenders`, { token }),
  linkLender: (shgId, lenderId, notes, token) =>
    request(`/api/shgs/${shgId}/link-lender`, {
      method: 'POST',
      token,
      body: JSON.stringify({ shg_id: shgId, lender_id: lenderId, notes }),
    }),

  // -------------------------------------------------------------- lenders
  listLenders: (token) => request('/api/lenders', { token }),
  getLender: (id, token) => request(`/api/lenders/${id}`, { token }),
  eligibleBorrowers: (lenderId, token) => request(`/api/lenders/${lenderId}/eligible-borrowers`, { token }),
  lenderReputation: (lenderId, token) => request(`/api/lenders/${lenderId}/reputation`, { token }),
  lenderLinks: (lenderId, token) => request(`/api/lenders/${lenderId}/links`, { token }),

  // ---------------------------------------------------------------- links
  listLinks: (params = {}, token) => request(`/api/links?${new URLSearchParams(params)}`, { token }),
  // Lender-initiated link request (new lender-only path per API_CONTRACT.md §5).
  createLenderLink: (lenderId, shgId, notes, token) =>
    request('/api/links', {
      method: 'POST',
      token,
      body: JSON.stringify({ lender_id: lenderId, shg_id: shgId, notes }),
    }),
  decideLink: (linkId, approve, notes, token) =>
    request(`/api/links/${linkId}/decide`, {
      method: 'POST',
      token,
      body: JSON.stringify({ approve, notes }),
    }),

  // --------------------------------------------------------------- offers
  listOffers: (params = {}, token) => {
    const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    return request(`/api/offers?${new URLSearchParams(clean)}`, { token })
  },
  proposeOffer: (payload, token) => request('/api/offers', { method: 'POST', token, body: JSON.stringify(payload) }),
  decideOffer: (offerId, accept, token) =>
    request(`/api/offers/${offerId}/decide`, { method: 'POST', token, body: JSON.stringify({ accept }) }),

  // ----------------------------------------------------------- geo/anomaly
  geoDistricts: (token) => request('/api/geo/districts', { token }),
  listAnomalies: (token) => request('/api/anomalies', { token }),
  runAnomalyDetection: (token) => request('/api/anomalies/run', { method: 'POST', token }),

  // ---------------------------------------------------------- loan requests
  listLoanRequests: (params = {}, token) => {
    const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    return request(`/api/loan-requests?${new URLSearchParams(clean)}`, { token })
  },
  eligibleLendersFor: (individualId, token) =>
    request(`/api/loan-requests/eligible-lenders?individual_id=${individualId}`, { token }),
  createLoanRequest: (payload, token) =>
    request('/api/loan-requests', { method: 'POST', token, body: JSON.stringify(payload) }),
  withdrawLoanRequest: (requestId, token) =>
    request(`/api/loan-requests/${requestId}/withdraw`, { method: 'POST', token }),
  decideLoanRequest: (requestId, payload, token) =>
    request(`/api/loan-requests/${requestId}/decide`, { method: 'POST', token, body: JSON.stringify(payload) }),
  retargetLoanRequest: (requestId, targetLenderId, token) =>
    request(`/api/loan-requests/${requestId}/retarget`, {
      method: 'POST',
      token,
      body: JSON.stringify({ target_lender_id: targetLenderId ?? null }),
    }),

  // ---------------------------------------------------------------- payments
  dueSummary: (individualId, token) => request(`/api/payments/due-summary?individual_id=${individualId}`, { token }),
  payLoan: (loanId, token) => request('/api/payments/pay', { method: 'POST', token, body: JSON.stringify({ loan_id: loanId }) }),
}
