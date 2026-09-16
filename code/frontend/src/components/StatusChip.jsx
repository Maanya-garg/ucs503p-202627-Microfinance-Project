// Design-system status chip (docs/DESIGN_SYSTEM.md §4.2): fixed rectangular
// shape, never color alone -- always a leading glyph + uppercase label.
const CONFIG = {
  Approved: { cls: 'approved', glyph: '✓' },
  Accepted: { cls: 'approved', glyph: '✓' },
  Closed: { cls: 'approved', glyph: '✓' },
  Pending: { cls: 'pending', glyph: '●' },
  Proposed: { cls: 'pending', glyph: '●' },
  Active: { cls: 'info', glyph: '●' },
  Rejected: { cls: 'rejected', glyph: '✕' },
  Declined: { cls: 'rejected', glyph: '✕' },
  Withdrawn: { cls: 'rejected', glyph: '✕' },
  Defaulted: { cls: 'rejected', glyph: '✕' },
  Flagged: { cls: 'flagged', glyph: '▲' },
}

export default function StatusChip({ status }) {
  const c = CONFIG[status] || { cls: 'info', glyph: '●' }
  return (
    <span className={`status-chip status-chip-${c.cls}`}>
      <span aria-hidden="true">{c.glyph}</span> {status}
    </span>
  )
}
