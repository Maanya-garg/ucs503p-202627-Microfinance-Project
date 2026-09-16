import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div
      style={{
        background: 'var(--surface-1)', border: '1px solid var(--border)', borderRadius: 8,
        padding: '6px 10px', fontSize: 12,
      }}
    >
      <div className="muted">{fmtDate(label)}</div>
      <div style={{ fontWeight: 600 }}>{payload[0].value}</div>
    </div>
  )
}

/** Score over time, single series -- no legend box (the card title already
 * says what's plotted). Recomputations happen as new repayment events land,
 * so this is the "did this person's score improve" story. */
export default function ScoreHistoryChart({ history }) {
  if (!history?.length) return <p className="muted small">No score history yet.</p>
  const data = history.map((h) => ({ date: h.calculated_date, score: h.score })).reverse()

  if (data.length === 1) {
    return <p className="muted small">Only one score on record so far -- {data[0].score}.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <XAxis
          dataKey="date"
          tickFormatter={fmtDate}
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          axisLine={{ stroke: 'var(--baseline)' }}
          tickLine={false}
        />
        <YAxis
          domain={[300, 900]}
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <Tooltip content={<CustomTooltip />} />
        <Line
          type="monotone"
          dataKey="score"
          stroke="var(--series-blue)"
          strokeWidth={2}
          dot={{ r: 4, fill: 'var(--series-blue)', stroke: 'var(--surface-1)', strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
