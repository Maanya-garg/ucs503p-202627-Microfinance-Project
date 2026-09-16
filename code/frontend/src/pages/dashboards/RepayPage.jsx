import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import Breadcrumb from '../../components/Breadcrumb'
import ScoreBadge from '../../components/ScoreBadge'

const GATEWAY_USER = 'abc'
const GATEWAY_PASS = '123'

function LoanRow({ loan, onPay, paying, result }) {
  return (
    <div className="repay-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
        <span className="muted">{loan.lender_name} &middot; {loan.purpose || 'Loan'}</span>
        {loan.will_be_late && <span className="status-chip status-chip-flagged"><span aria-hidden="true">▲</span> LATE</span>}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', width: '100%', marginTop: 4 }}>
        <div>
          <p className="field-label" style={{ margin: 0 }}>Amount due -- EMI #{loan.cycle_number} of {loan.tenure_months_total}</p>
          <p className="repay-amount" style={{ margin: 0 }}>Rs. {loan.amount_due_this_cycle.toLocaleString('en-IN')}</p>
        </div>
        {!result && (
          <button className="btn primary" onClick={() => onPay(loan.loan_id)} disabled={paying}>
            {paying ? 'Paying...' : 'Pay this loan'}
          </button>
        )}
      </div>
      {result && (
        <div className="repay-success-strip">
          <span aria-hidden="true">✓</span> Paid Rs. {result.amount_paid.toLocaleString('en-IN')} -- {result.status === 'On_Time' ? 'On time' : 'Late'}.{' '}
          New score: <ScoreBadge riskCategory={result.new_score.risk_category} score={result.new_score.score} />
        </div>
      )}
    </div>
  )
}

function GatewayLogin({ onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)

  const submit = (e) => {
    e.preventDefault()
    if (username === GATEWAY_USER && password === GATEWAY_PASS) {
      setErr(null)
      onSuccess()
    } else {
      setErr('Incorrect username or password.')
    }
  }

  return (
    <form onSubmit={submit} style={{ maxWidth: 360 }}>
      <p className="card-sub">Sign in to the payment gateway to continue.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label className="field-label" htmlFor="gw-user">Username</label>
        <input id="gw-user" placeholder="Username" value={username}
               onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <label className="field-label" htmlFor="gw-pass">Password</label>
        <input id="gw-pass" type="password" placeholder="Password" value={password}
               onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        {err && <div className="error-banner" style={{ marginBottom: 0 }}>{err}</div>}
        <button type="submit" className="btn primary" disabled={!username || !password}>
          Sign in &amp; continue
        </button>
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>Demo login -- username <code>abc</code>, password <code>123</code>.</p>
    </form>
  )
}

function Buffering() {
  return (
    <div style={{ textAlign: 'center', padding: '32px 0' }}>
      <div className="loading">Connecting to payment gateway...</div>
      <p className="muted small" style={{ marginTop: 8 }}>Please do not refresh this page.</p>
    </div>
  )
}

export default function RepayPage() {
  const { auth } = useAuth()
  const token = auth.token
  const navigate = useNavigate()

  const [stage, setStage] = useState('login') // login -> connecting -> gateway
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [payingId, setPayingId] = useState(null)
  const [results, setResults] = useState({})
  const [blockedInfo, setBlockedInfo] = useState(null)

  const loadSummary = () => {
    setLoading(true)
    setError(null)
    api.dueSummary(auth.id, token)
      .then((d) => setSummary(d))
      .catch((e) => setError(e.message || String(e)))
      .finally(() => setLoading(false))
  }

  const handleLoginSuccess = () => {
    setStage('connecting')
    setTimeout(() => {
      setStage('gateway')
      loadSummary()
    }, 1400)
  }

  const handlePay = async (loanId) => {
    setPayingId(loanId)
    try {
      const res = await api.payLoan(loanId, token)
      setResults((prev) => ({ ...prev, [loanId]: res }))
      setBlockedInfo(null)
      loadSummary()
    } catch (e) {
      // Contract: a live 400 insufficient_funds mid-session drops the whole
      // page into the blocked state, regardless of which loan was clicked.
      if (e.body?.error === 'insufficient_funds') {
        setBlockedInfo(e.body)
      } else {
        alert(e.message)
      }
    } finally {
      setPayingId(null)
    }
  }

  const anySucceeded = Object.keys(results).length > 0
  const blocked = blockedInfo || (summary && !summary.sufficient_funds)

  return (
    <div className="repay-page">
      <Breadcrumb items={[{ label: 'Borrower Dashboard', to: '/borrower' }, { label: 'Repay' }]} />
      <div style={{ marginBottom: 12 }}>
        <Link className="btn" to="/borrower">&larr; Back to Dashboard</Link>
      </div>
      <div className="card">
        <h2>Repay Loan</h2>

        {stage === 'login' && <GatewayLogin onSuccess={handleLoginSuccess} />}
        {stage === 'connecting' && <Buffering />}

        {stage === 'gateway' && (
          <div aria-live="polite">
            {loading && <div className="loading">Loading...</div>}
            {error && <div className="error-banner">{error}</div>}

            {summary && (
              <>
                <p className="card-sub">Wallet balance: Rs. {summary.wallet_balance.toLocaleString('en-IN')}</p>

                {blocked && (
                  <div className="error-banner">
                    <p style={{ fontWeight: 700, margin: '0 0 6px' }}>Insufficient balance to complete this payment.</p>
                    <p style={{ margin: 0 }}>
                      Your wallet balance (Rs. {(blockedInfo?.wallet_balance ?? summary.wallet_balance).toLocaleString('en-IN')}) is
                      less than the Rs. {(blockedInfo?.total_due_this_cycle ?? summary.total_due_this_cycle).toLocaleString('en-IN')} due
                      across your {summary.loans.length} active loan(s) this cycle. Add funds or reduce the amount before retrying.
                    </p>
                  </div>
                )}

                {!blocked && summary.loans.length > 1 && (
                  <p className="muted small">
                    You have Rs. {summary.total_due_this_cycle.toLocaleString('en-IN')} due across {summary.loans.length} active
                    loan(s) this cycle.
                  </p>
                )}

                {summary.loans.length === 0 && <p className="muted small">You have no active loans to repay.</p>}

                {summary.loans.map((loan) => (
                  <LoanRow
                    key={loan.loan_id}
                    loan={loan}
                    onPay={handlePay}
                    paying={payingId === loan.loan_id}
                    result={results[loan.loan_id]}
                  />
                ))}

                {anySucceeded && (
                  <button className="btn primary" style={{ marginTop: 16, width: '100%' }} onClick={() => navigate('/borrower')}>
                    Done
                  </button>
                )}
                {blocked && (
                  <Link className="btn" style={{ marginTop: 16, display: 'block', textAlign: 'center' }} to="/borrower">
                    Back to Dashboard
                  </Link>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
