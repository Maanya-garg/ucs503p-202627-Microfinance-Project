const BUILD_DATE = new Date().toISOString().slice(0, 10)

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer-cols">
        <div>
          <h3>About CreditSetu</h3>
          <p className="small muted">
            A microfinance credit-scoring demonstration platform for India, built for self-help-group members and
            independent borrowers to see their own credit standing, and for lenders and groups to match with each
            other transparently.
          </p>
        </div>
        <div>
          <h3>Quick Links</h3>
          <ul className="footer-links">
            <li><a href="/">Home</a></li>
            <li><a href="/">Sitemap</a></li>
            <li><a href="/">Accessibility Statement</a></li>
            <li><a href="/">Contact / Feedback</a></li>
          </ul>
        </div>
        <div>
          <h3>Policies</h3>
          <ul className="footer-links">
            <li><a href="/">Terms of Use</a></li>
            <li><a href="/">Privacy Policy</a></li>
            <li><a href="/">Hyperlinking Policy</a></li>
          </ul>
        </div>
      </div>
      <div className="site-footer-bottom">
        Content owned and maintained by CreditSetu (Demo Project) &middot; Last Updated: {BUILD_DATE} &middot; This
        is a private demonstration platform and is not affiliated with the Government of India.
      </div>
    </footer>
  )
}
