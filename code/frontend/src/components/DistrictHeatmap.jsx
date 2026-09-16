const SEQ_STEPS = [
  '#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec',
  '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b',
]

function seqColor(value, min, max) {
  if (max === min) return SEQ_STEPS[Math.floor(SEQ_STEPS.length / 2)]
  const t = Math.min(1, Math.max(0, (value - min) / (max - min)))
  return SEQ_STEPS[Math.round(t * (SEQ_STEPS.length - 1))]
}

// Rough luminance check so cell text stays legible on both light and dark fills.
function textColorFor(hex) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#0b0b0b' : '#ffffff'
}

/** Sequential (one hue, light->dark) heatmap over avg credit score per
 * district -- magnitude encoding, per the districts-are-a-continuum story
 * this feeds (branch-placement priority). Cluster label rides alongside as
 * plain text, not re-encoded in color, so the two channels don't compete. */
export default function DistrictHeatmap({ rows }) {
  if (!rows?.length) return <p className="muted small">No district data yet.</p>
  const scores = rows.map((r) => r.avg_score)
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  const sorted = [...rows].sort((a, b) => b.avg_score - a.avg_score)

  return (
    <table>
      <thead>
        <tr>
          <th>District</th>
          <th>State</th>
          <th>Borrowers</th>
          <th>SHG density</th>
          <th>Avg score</th>
          <th>Default rate</th>
          <th>Cluster</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => {
          const fill = seqColor(r.avg_score, min, max)
          return (
            <tr key={r.district_id}>
              <td style={{ fontWeight: 600 }}>{r.name}</td>
              <td className="muted">{r.state}</td>
              <td>{r.n_borrowers}</td>
              <td>{Math.round(r.shg_density * 100)}%</td>
              <td>
                <span
                  style={{
                    display: 'inline-block', minWidth: 52, textAlign: 'center',
                    background: fill, color: textColorFor(fill),
                    borderRadius: 6, padding: '3px 8px', fontWeight: 700, fontSize: 12,
                  }}
                >
                  {r.avg_score}
                </span>
              </td>
              <td>{(r.default_rate * 100).toFixed(1)}%</td>
              <td className="muted small">{r.cluster_label}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
