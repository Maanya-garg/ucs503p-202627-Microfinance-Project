import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div
      style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 12,
        boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 2 }}>{d.feature_name}</div>
      <div className="muted">value: {d.feature_value}</div>
      <div style={{ color: d.points >= 0 ? 'var(--diverging-pos)' : 'var(--diverging-neg)', fontWeight: 600 }}>
        {d.points >= 0 ? '+' : ''}
        {d.points.toFixed(1)} pts
      </div>
    </div>
  )
}

/** Diverging horizontal bar chart: why a score is what it is, one bar per
 * feature, positive (helped the score) in blue, negative (hurt it) in red,
 * a neutral gridline at zero. Single measure (points), so no legend needed --
 * the two colors are explained by the chart's own title/caption instead of a
 * swatch box, and every bar still carries its value as a direct label. */
export default function ShapWaterfall({ rows }) {
  if (!rows?.length) return <p className="muted small">No explanation available yet.</p>

  const data = [...rows].sort((a, b) => a.points - b.points)
  const maxAbs = Math.max(...data.map((d) => Math.abs(d.points)), 1)
  const rowHeight = 32
  const height = Math.max(120, data.length * rowHeight + 20)

  return (
    <BarChart
      layout="vertical"
      width={520}
      height={height}
      data={data}
      margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
      barCategoryGap={6}
    >
      <XAxis
        type="number"
        domain={[-maxAbs * 1.15, maxAbs * 1.15]}
        hide
      />
      <YAxis
        type="category"
        dataKey="feature_name"
        width={168}
        tick={{ fontSize: 12, fill: 'var(--text-secondary)' }}
        axisLine={{ stroke: 'var(--baseline)' }}
        tickLine={false}
      />
      <ReferenceLine x={0} stroke="var(--baseline)" />
      <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--page-plane)' }} />
      <Bar dataKey="points" radius={4} maxBarSize={20}>
        {data.map((d, i) => (
          <Cell key={i} fill={d.points >= 0 ? 'var(--diverging-pos)' : 'var(--diverging-neg)'} />
        ))}
        <LabelList
          dataKey="points"
          position="right"
          formatter={(v) => `${v >= 0 ? '+' : ''}${Math.round(v)}`}
          style={{ fontSize: 11, fill: 'var(--text-secondary)' }}
        />
      </Bar>
    </BarChart>
  )
}
