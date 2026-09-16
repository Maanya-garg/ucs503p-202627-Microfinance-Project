import { Link } from 'react-router-dom'

/** `Home / Section / Current Page` trail, required on every non-home page
 * per docs/DESIGN_SYSTEM.md §3.2 (GIGW convention). `items` is a list of
 * { label, to? } -- the last item is rendered as plain text (current page),
 * earlier ones as links if `to` is given. */
export default function Breadcrumb({ items }) {
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <Link to="/">Home</Link>
      {items.map((it, i) => (
        <span key={i}>
          {' '}/{' '}
          {it.to ? <Link to={it.to}>{it.label}</Link> : <span className="breadcrumb-current">{it.label}</span>}
        </span>
      ))}
    </nav>
  )
}
