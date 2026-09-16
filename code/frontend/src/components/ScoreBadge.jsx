const COLORS = {
  'Very Low': 'var(--status-approved)',
  Low: 'var(--status-approved)',
  Medium: 'var(--status-pending)',
  High: 'var(--status-flagged)',
  'Very High': 'var(--status-rejected)',
}

export default function ScoreBadge({ riskCategory, score }) {
  const color = COLORS[riskCategory] || 'var(--text-muted)'
  return (
    <span className="badge">
      <span className="dot" style={{ background: color }} />
      {score != null ? `${score} · ` : ''}
      {riskCategory || 'Not scored'}
    </span>
  )
}
