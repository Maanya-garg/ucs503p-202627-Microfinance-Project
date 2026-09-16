import { useState } from 'react'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import Breadcrumb from '../../components/Breadcrumb'
import ScoreBadge from '../../components/ScoreBadge'
import ScoreHistoryChart from '../../components/ScoreHistoryChart'
import ShapWaterfall from '../../components/ShapWaterfall'
import StatusChip from '../../components/StatusChip'
import { useApi } from '../../hooks/useApi'

function LoansTable({ loans }) {
  if (!loans.length) return <p className="muted small">No loan history yet.</p>
  return (
    <table>
      <thead>
        <tr><th>Principal</th><th>Rate</th><th>Tenure</th><th>Disbursed</th><th>Status</th><th>Repayments</th></tr>
      </thead>
      <tbody>
        {loans.map((l) => (
          <tr key={l.id}>
            <td>Rs. {l.principal_amount.toLocaleString('en-IN')}</td>
            <td>{l.interest_rate}%</td>
            <td>{l.tenure_months}mo</td>
            <td>{l.disbursement_date}</td>
            <td><StatusChip status={l.status} /></td>
            <td>{l.n_repayment_events}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function RequestLoanForm({ individualId, token, onCreated }) {
  const { data: eligibility } = useApi(() => api.eligibleLendersFor(individualId, token), [individualId])
  const [principal, setPrincipal] = useState(15000)
  const [tenure, setTenure] = useState(12)
  const [purpose, setPurpose] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.createLoanRequest(
        { individual_id: individualId, principal: Number(principal), tenure: Number(tenure), purpose: purpose || undefined },
        token,
      )
      setPurpose('')
      await onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      {eligibility && (
        <p className="small muted" style={{ marginTop: -8, marginBottom: 12 }}>
          {eligibility.count === 0
            ? "No lenders are currently eligible to see your requests yet -- your SHG isn't linked with an approved lender, or no lender serving independents matches your score. A request will still be created and wait until one is."
            : `${eligibility.count} lender${eligibility.count === 1 ? '' : 's'} would currently see a request from you: ${eligibility.lenders.map((l) => l.name).join(', ')}.`}
        </p>
      )}
      <form onSubmit={submit}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input type="number" min="1" value={principal} onChange={(e) => setPrincipal(e.target.value)} style={{ width: 110 }} title="Principal (Rs.)" />
          <input type="number" min="1" value={tenure} onChange={(e) => setTenure(e.target.value)} style={{ width: 90 }} title="Tenure (months)" />
          <input placeholder="Purpose (optional)" value={purpose} onChange={(e) => setPurpose(e.target.value)} style={{ flex: 1, minWidth: 160 }} />
          <button className="btn primary" type="submit" disabled={busy || !principal || !tenure}>
            {busy ? 'Requesting...' : 'Request loan'}
          </button>
        </div>
        {error && <div className="error-banner" style={{ marginTop: 10, marginBottom: 0 }}>{error}</div>}
      </form>
    </div>
  )
}

function RequestsTable({ requests, onWithdraw }) {
  if (!requests?.length) return <p className="muted small">You haven't requested a loan yet.</p>
  return (
    <table>
      <thead>
        <tr><th>Principal</th><th>Tenure</th><th>Purpose</th><th>Status</th><th>Lender</th><th></th></tr>
      </thead>
      <tbody>
        {requests.map((r) => (
          <tr key={r.id}>
            <td>Rs. {r.requested_principal.toLocaleString('en-IN')}</td>
            <td>{r.requested_tenure}mo</td>
            <td className="muted">{r.purpose || '--'}</td>
            <td><StatusChip status={r.status} /></td>
            <td className="muted">{r.decided_by_lender_name || '--'}</td>
            <td>
              {r.status === 'Pending' && (
                <button className="btn critical" onClick={() => onWithdraw(r.id)}>Withdraw</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function OffersTable({ offers, onDecide }) {
  if (!offers?.length) return <p className="muted small">No lender has proposed you a loan offer yet.</p>
  return (
    <table>
      <thead>
        <tr><th>Lender</th><th>Principal</th><th>Rate</th><th>Tenure</th><th>Status</th><th></th></tr>
      </thead>
      <tbody>
        {offers.map((o) => (
          <tr key={o.id}>
            <td>{o.lender_name}</td>
            <td>Rs. {o.principal_offer.toLocaleString('en-IN')}</td>
            <td>{o.rate_offer}%</td>
            <td>{o.tenure_offer}mo</td>
            <td><StatusChip status={o.status} /></td>
            <td>
              {o.status === 'Proposed' && (
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn good" onClick={() => onDecide(o.id, true)}>Accept</button>
                  <button className="btn critical" onClick={() => onDecide(o.id, false)}>Reject</button>
                </div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function SuggestedLendersCard({ individualId, token }) {
  const { data, loading, error } = useApi(() => api.suggestedLenders(individualId, token), [individualId])
  return (
    <div className="card">
      <h2>Suggested lenders for you</h2>
      <p className="card-sub">Lenders you're currently eligible for, ranked by their base interest rate.</p>
      {loading && <div className="loading">Loading...</div>}
      {error && <div className="error-banner">{error}</div>}
      {data && (
        data.count === 0
          ? <p className="muted small">No eligible lenders yet.</p>
          : (
            <table>
              <thead><tr><th>Lender</th><th>Type</th><th>Base rate</th><th>Max loan</th><th>Reputation</th></tr></thead>
              <tbody>
                {data.lenders.map((l) => (
                  <tr key={l.id}>
                    <td style={{ fontWeight: 600 }}>{l.name}</td>
                    <td className="muted">{l.type}</td>
                    <td>{l.base_interest_rate}%</td>
                    <td>Rs. {l.max_loan_amount.toLocaleString('en-IN')}</td>
                    <td>{l.reputation_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
      )}
    </div>
  )
}

function LenderDirectoryCard({ token }) {
  const { data, loading, error } = useApi(() => api.listLenders(token), [])
  return (
    <div className="card">
      <h2>Lender directory</h2>
      <p className="card-sub">Every lender on the platform (read-only).</p>
      {loading && <div className="loading">Loading...</div>}
      {error && <div className="error-banner">{error}</div>}
      {data && (
        <table>
          <thead><tr><th>Name</th><th>Type</th><th>Min score</th><th>Max loan</th><th>Base rate</th></tr></thead>
          <tbody>
            {data.map((l) => (
              <tr key={l.id}>
                <td style={{ fontWeight: 600 }}>{l.name}</td>
                <td className="muted">{l.type}</td>
                <td>{l.min_score_threshold}</td>
                <td>Rs. {l.max_loan_amount.toLocaleString('en-IN')}</td>
                <td>{l.base_interest_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function OwnShgCard({ shgId, token }) {
  const { data, loading, error } = useApi(() => (shgId ? api.getShg(shgId, token) : Promise.resolve(null)), [shgId])
  if (!shgId) {
    return (
      <div className="card">
        <h2>Your SHG</h2>
        <p className="muted small">You're an independent borrower -- not linked to a Self-Help Group.</p>
      </div>
    )
  }
  return (
    <div className="card">
      <h2>Your SHG</h2>
      {loading && <div className="loading">Loading...</div>}
      {error && <div className="error-banner">{error}</div>}
      {data && (
        <>
          <p className="card-sub">{data.village}, {data.district} &middot; formed {data.formed_date}</p>
          <div className="grid cols-4">
            <div className="stat-tile"><p className="label">Members</p><p className="value">{data.n_members_actual}</p></div>
            <div className="stat-tile"><p className="label">Avg score</p><p className="value">{data.avg_member_score ?? '--'}</p></div>
            <div className="stat-tile"><p className="label">Repayment rate</p><p className="value">{data.aggregate_repayment_rate != null ? `${Math.round(data.aggregate_repayment_rate * 100)}%` : '--'}</p></div>
            <div className="stat-tile"><p className="label">Attendance</p><p className="value">{data.aggregate_attendance_rate != null ? `${Math.round(data.aggregate_attendance_rate * 100)}%` : '--'}</p></div>
          </div>
        </>
      )}
    </div>
  )
}

export default function BorrowerDashboard() {
  const { auth } = useAuth()
  const token = auth.token
  const { data: detail, loading, error, reload } = useApi(() => api.getIndividual(auth.id, token), [auth.id])
  const { data: history } = useApi(() => api.scoreHistory(auth.id, token), [auth.id])
  const { data: offers, reload: reloadOffers } = useApi(() => api.listOffers({ individual_id: auth.id }, token), [auth.id])
  const { data: requests, reload: reloadRequests } = useApi(() => api.listLoanRequests({ individual_id: auth.id }, token), [auth.id])
  const [recomputing, setRecomputing] = useState(false)

  const handleDecideOffer = async (offerId, accept) => {
    try {
      await api.decideOffer(offerId, accept, token)
      await Promise.all([reloadOffers(), reload()])
    } catch (e) {
      alert(e.message)
    }
  }

  const handleWithdrawRequest = async (requestId) => {
    try {
      await api.withdrawLoanRequest(requestId, token)
      await reloadRequests()
    } catch (e) {
      alert(e.message)
    }
  }

  const handleRecompute = async () => {
    setRecomputing(true)
    try {
      await api.recomputeScore(auth.id, token)
      await reload()
    } catch (e) {
      alert(e.message)
    } finally {
      setRecomputing(false)
    }
  }

  if (loading) return <div className="loading">Loading your profile...</div>
  if (error) return <div className="error-banner">{error}</div>
  if (!detail) return null

  const shapRows = detail.score_explanation.map((e) => ({
    feature_name: e.feature_name, feature_value: e.feature_value, points: e.points,
  }))

  return (
    <div>
      <Breadcrumb items={[{ label: 'Borrower Dashboard' }]} />
      <h1>Welcome back, {detail.name.split(' ')[0]}.</h1>
      <p className="page-intro">Your own credit history, improvement tips, and matching lenders -- nothing about any other borrower.</p>

      <div className="grid cols-2">
        <div className="card">
          <h2>{detail.name}</h2>
          <p className="card-sub">
            {detail.district} &middot; {detail.occupation} &middot;{' '}
            {detail.is_shg_linked ? `SHG: ${detail.shg_name}` : 'Independent borrower'}
          </p>
          <div className="hero-figure">{detail.latest_score?.score ?? '--'}</div>
          <div style={{ marginTop: 8 }}>
            <ScoreBadge riskCategory={detail.latest_score?.risk_category} />
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>
            Base component: {detail.latest_score?.base_component || 'n/a'} &middot; monthly income Rs.{' '}
            {detail.monthly_income?.toLocaleString('en-IN')} &middot; bank account:{' '}
            {detail.has_bank_account ? 'yes' : 'no'}
          </p>
          <button className="btn primary" onClick={handleRecompute} disabled={recomputing} style={{ marginTop: 8 }}>
            {recomputing ? 'Recomputing...' : 'Recompute my score'}
          </button>
        </div>

        <div className="card">
          <h2>Your score history</h2>
          <p className="card-sub">How your score has moved as your repayment history accumulated.</p>
          <ScoreHistoryChart history={history} />
        </div>
      </div>

      <div className="card">
        <h2>Why you got this score</h2>
        <p className="card-sub">
          Each bar is a SHAP-derived contribution in score points, relative to what a typical borrower in the
          training population would get. Positive helped your score, negative hurt it.
        </p>
        <ShapWaterfall rows={shapRows} />
      </div>

      {detail.improvement_tips?.length > 0 && (
        <div className="card notice-banner">
          <h2>Ways to improve your score</h2>
          <ul>
            {detail.improvement_tips.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </div>
      )}

      <div className="card">
        <h2>Your loan history</h2>
        <LoansTable loans={detail.loans} />
      </div>

      <div className="card">
        <h2>Need a loan?</h2>
        <p className="card-sub">
          Request one directly -- it's broadcast to every lender you're currently eligible for (via your SHG's
          approved links, or independently, if a lender serves those). Any one of them can approve it, which
          creates the loan immediately.
        </p>
        <RequestLoanForm individualId={detail.id} token={token} onCreated={reloadRequests} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Your loan offers</h2>
          <p className="card-sub">Offers a lender has proposed to you directly.</p>
          <OffersTable offers={offers} onDecide={handleDecideOffer} />
        </div>

        <div className="card">
          <h2>Your loan requests</h2>
          <p className="card-sub">Requests you've made, and how lenders responded.</p>
          <RequestsTable requests={requests} onWithdraw={handleWithdrawRequest} />
        </div>
      </div>

      <SuggestedLendersCard individualId={detail.id} token={token} />
      <OwnShgCard shgId={detail.shg_id} token={token} />
      <LenderDirectoryCard token={token} />
    </div>
  )
}
