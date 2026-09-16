const COLORS = {
  'Very Low': 'var(--status-approved)',
  Low: 'var(--status-approved)',
  Medium: 'var(--status-pending)',
  High: 'var(--status-flagged)',
  'Very High': 'var(--status-rejected)',
}

// The backend's risk_category ("Very Low", "Very High", ...) names the risk
// of default, not the score quality -- shown bare under a borrower's own
// score, "Very Low" reads as if the score itself is bad, when a low default
// risk is actually the best outcome. Translate to the same Excellent/Good/
// Fair/Poor band language real credit bureaus use, so the label always
// reads the right direction relative to the number above it.
const SCORE_LABELS = {
  'Very Low': 'Excellent',
  Low: 'Good',
  Medium: 'Fair',
  High: 'Poor',
  'Very High': 'Very Poor',
}

export default function ScoreBadge({ riskCategory, score }) {
  const color = COLORS[riskCategory] || 'var(--text-muted)'
  const label = SCORE_LABELS[riskCategory] || riskCategory || 'Not scored'
  return (
    <span className="badge">
      <span className="dot" style={{ background: color }} />
      {score != null ? `${score} · ` : ''}
      {label}
    </span>
  )
}
