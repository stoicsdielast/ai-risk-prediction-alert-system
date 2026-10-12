import { Link } from 'react-router-dom'
import { Brand } from '../components/Brand'

export function NotFoundPage() {
  return (
    <main className="not-found">
      <Brand />
      <span className="not-found__code">404</span>
      <h1>That page is not here.</h1>
      <p>The address may be incorrect or the page may have moved.</p>
      <Link className="button button--primary" to="/">
        Return home
      </Link>
    </main>
  )
}
