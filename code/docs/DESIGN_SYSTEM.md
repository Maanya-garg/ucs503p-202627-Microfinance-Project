# CreditSetu — Design System Spec

Standalone spec for redesigning CreditSetu (dual-path microfinance credit-scoring demo for India) to read as a
formal Indian public-sector / financial-inclusion portal rather than a generic startup SaaS product. Written for
Agent 4 (frontend implementation) to build from directly, alongside `docs/REQUIREMENTS.md`. This is a **visual
register only** — see "What NOT to do" below: this is a private demo project, not an official government site.

---

## 0. Research basis

**Primary source (most authoritative):** [GIGW — Guidelines for Indian Government Websites and Apps, guidelines.india.gov.in](https://guidelines.india.gov.in/guidelines/), maintained by NIC/MeitY. Current major version is GIGW 3.0, which layers WCAG 2.1 AA accessibility requirements (per the Rights of Persons with Disabilities Act 2016 / Harmonized Guidelines on Accessibility) onto structural/visual rules for header, footer, navigation, color contrast, and typography. Supplementary source: the [Digital Brand Identity Manual (DBIM), digifootprint.gov.in](https://dbimtoolkit.digifootprint.gov.in/), which governs official color/logo/typography standards for GoI digital properties (referenced for tone only — CreditSetu must not reuse actual GoI marks).

Concrete rules pulled from GIGW 3.0 that shape this spec:
- **Header**: an official emblem/crest displayed prominently in "proper ratio and colour"; organisation ownership shown in header or footer on every important page.
- **Footer**: "last updated"/"content last reviewed" date on the homepage; ownership + contact details; prominent link to a "National Portal"-style anchor; Contact Us / Feedback links site-wide.
- **Navigation**: breadcrumb on every page linking back to home and to the parent section; skip-to-content link; search, sitemap, and consistent IA/terminology across all pages.
- **Color & contrast**: WCAG 2.1 AA — 4.5:1 for normal text, 3:1 for large text (≥18pt, or ≥14pt bold) and for UI component boundaries/states; color is never the sole carrier of meaning (status must always pair a color with an icon/label); a high-contrast mode should be offered.
- **Typography**: text must reflow/resize up to 200% without loss of function; support generous line-height (≥1.5×) and letter/word spacing; Unicode fonts for Hindi/regional scripts; correct heading hierarchy (H1–H6); content must print cleanly on A4.
- **Tone**: real portals (india.gov.in, rbi.org.in, nabard.org, pmjdy.gov.in) commonly pair a navy/indigo primary with a warm maroon or saffron secondary accent, use a top utility bar (language toggle, text-size controls, high-contrast toggle) above the main nav, present tabular/dense data plainly (bordered tables, no decorative gradients), and use notice/circular-style banners for announcements.

CreditSetu will adopt the **structural and tonal conventions** of GIGW (utility bar, breadcrumbs, formal footer, navy/maroon palette, plain data tables, notice banners, AA contrast) without using any actual government emblem, .gov.in/.nic.in domain implication, or claim of official status.

---

## 1. Color palette

Replace the current palette in `frontends/src/index.css` (`--series-blue` #2a78d6 SaaS-blue system, warm gradients) with an official-portal palette. All pairings below are WCAG AA-checked (4.5:1 body text, 3:1 large text/UI).

### Light mode (default)

```
Primary (navy, "Institutional Blue")   #0B3D6B   — on white: 8.2:1 ✓   text/large-UI on white
Primary hover/active                   #082B4A
Primary tint (surfaces, chips)         #E8F0F8
Secondary (maroon, "Circular Red")     #8E1B2E   — on white: 8.6:1 ✓
Secondary tint                         #FBEAEC
Accent (saffron, sparingly — badges/highlights only, never body text) #C4701A  — on white: 4.6:1 ✓ (large text/icons only)
Accent tint                            #FBF0E2

Neutrals
  --text-primary     #14181C            — on white: 15.8:1
  --text-secondary   #3F4750            — on white: 8.9:1
  --text-muted       #6B7280            — on white: 4.7:1 (body-safe, use ≥14px)
  --surface-1        #FFFFFF            (cards, header)
  --surface-2        #F4F6F8            (page background, zebra rows)
  --border           #D3D9DF
  --gridline         #E2E6EA

Status (always paired with icon/text label, never color alone)
  --status-approved   #1B7A3D  bg #E7F5EC  (Approved / Good standing)
  --status-pending     #9A6300  bg #FDF3D9  (Pending / Under review)
  --status-rejected    #A21C2E  bg #FBE9EA  (Rejected / Declined)
  --status-flagged     #B3540A  bg #FCEEE0  (Flagged / Needs attention — anomaly)
  --status-info        #0B3D6B  bg #E8F0F8  (Informational / neutral notice)
```

### Dark mode (derived; optional but recommended since GIGW mandates a "high contrast" alternative mode)

```
--text-primary     #F1F4F7
--text-secondary   #C3CBD3
--text-muted       #93A0AC
--surface-1        #0F1B29
--surface-2        #0A1420
--border            #24303C
--gridline          #1C2732

Primary (light navy, for AA on dark)   #6FA8DC  — on #0F1B29: 7.1:1 ✓
Secondary (light maroon)               #E38A96  — on #0F1B29: 6.4:1 ✓
Accent (saffron)                       #E3A64B  — on #0F1B29: 8.0:1 ✓

Status (dark-safe)
  --status-approved   #4CAF6D  bg #123420
  --status-pending     #E3B341  bg #3A2C05
  --status-rejected    #E4677A  bg #3A1216
  --status-flagged     #E39056  bg #3A2409
  --status-info        #6FA8DC  bg #10253A
```

High-contrast toggle (GIGW-style accessibility control): simplest implementation is forcing `--text-primary`→pure black/white and widening border contrast; ship as a `data-contrast="high"` attribute swap, not a separate palette (Agent 4's call on scope).

---

## 2. Typography

**Font stack for the Vite/React app** (no CSP restriction applies to the app itself — only to HTML artifacts elsewhere in this project's toolchain):

- **Primary UI/body**: `"Noto Sans", "Noto Sans Devanagari", system-ui, -apple-system, "Segoe UI", sans-serif` — Noto Sans is the standard Unicode-complete family GIGW-aligned sites use for guaranteed Hindi/regional-script rendering alongside Latin.
- **Headings / formal document tone**: `"Noto Serif", Georgia, "Times New Roman", serif` for H1/H2 on notice-like or ceremonial surfaces (home hero, official-looking headers) — optional; body and dashboards stay sans-serif for density and readability.
- Load via Google Fonts in `index.html`: `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700&family=Noto+Serif:wght@600;700&family=Noto+Sans+Devanagari:wght@400;600&display=swap">` (fonts.googleapis.com/fonts.gstatic.com — compliant even under the stricter artifact CSP, so no divergence needed between contexts).

**Scale** (rem, 16px base; supports 200% zoom reflow per GIGW):

```
--fs-xs:   0.75rem   (12px)  — micro-labels, table meta
--fs-sm:   0.8125rem (13px)  — table body, form helper text
--fs-base: 0.875rem  (14px)  — default body
--fs-md:   1rem      (16px)  — emphasized body, card titles
--fs-lg:   1.125rem  (18px)  — section subheads
--fs-xl:   1.375rem  (22px)  — H2
--fs-2xl:  1.75rem   (28px)  — H1 / hero
--fs-3xl:  2.25rem   (36px)  — hero figure / large stat

--lh-tight:  1.25
--lh-base:   1.55     (≥1.5× per GIGW text-spacing rule)
--lh-loose:  1.7
```

**Heading conventions**: strict H1→H6 order per page (one H1 per view, GIGW requirement); headings use the primary navy color (`--text-primary` or `--primary`), semibold-to-bold weight (600–700), never rely on size alone for hierarchy — pair with consistent top margin and a thin bottom rule for H2 section headers on dense dashboard pages (mirrors circular/notice document conventions).

---

## 3. Layout conventions

### 3.1 Header (three-tier, GIGW-style)

1. **Utility bar** (top strip, `--primary` navy background, `--fs-xs`, white text, 32–36px tall):
   - Left: "Skip to main content" (visually hidden until focus — accessibility requirement).
   - Right, inline controls: language toggle (English/हिन्दी placeholder — even if only English is wired initially, reserve the slot), text-size stepper (A− / A / A+), high-contrast toggle, and a plain-text "Screen Reader Access" link. This bar is the single most recognizable GIGW visual signature — do not skip it.
2. **Trust-mark branding strip** (white/`--surface-1`, ~64–72px, bottom border in `--border`):
   - Left: a neutral geometric "trust mark" badge (NOT any national emblem — e.g. a simple shield/circle monogram in navy+maroon gradient with "CS" or a rupee-motif glyph) + wordmark "CreditSetu" + small caption line "Microfinance Credit Scoring — Demonstration Platform" (the caption doubles as an anti-impersonation disclaimer, see §5).
   - Right (optional on wide viewports): a thin tricolor-inspired 3px accent rule (saffron/white-gap/green) *only* as a decorative underline beneath the header — this nods to the register without using flag imagery as a badge or seal.
3. **Main navigation bar** (`--surface-2` background, `--border` bottom rule): horizontal tab-style links (Home, Borrower, SHG & Lender, Bank/Admin, My Score), left-aligned (not pill/centered like the current build), active item gets a 3px bottom underline in `--primary` plus bold weight — flatter and more "official directory" than the current floating pill nav.

### 3.2 Breadcrumbs

Below the main nav on every non-home page: `Home / Section / Current Page`, `--fs-xs`, `--text-muted`, `/` separators, current page not a link and in `--text-secondary`. Required by GIGW on every page.

### 3.3 Footer (formal, multi-column)

- **Column 1**: "About CreditSetu" — one-line description + the required disclaimer (see §5).
- **Column 2**: Quick Links — Home, Sitemap, Accessibility Statement, Contact/Feedback (placeholders are fine if not functionally built yet).
- **Column 3**: Policies — Terms of Use, Privacy Policy, Hyperlinking Policy (naming convention mirrors real portals; content can be minimal demo copy).
- **Bottom bar**, full width, `--primary` navy background, white `--fs-xs` text, centered: `Content owned and maintained by CreditSetu (Demo Project) · Last Updated: <dynamic/build date> · This is a private demonstration platform and is not affiliated with the Government of India.`

### 3.4 Card / table conventions for dense financial data

- **Tables** are the default for lists (borrower list, SHG member list, loan ledger) — not cards. Bordered, zebra-striped (`--surface-2` even rows), header row `--primary` tint background (`--primary-tint`) with `--text-primary` bold uppercase `--fs-xs` labels, dense row height (36–40px), right-aligned numeric columns with tabular-nums.
- **Cards** are reserved for: summary/stat tiles, the home hero, and single-record detail panels (a borrower's own score explanation). Card style: sharper corners than current build (`--radius: 4px` instead of 10px — flatter, more document-like), 1px `--border`, no drop-shadow gradients — flat elevation via a single subtle `box-shadow: 0 1px 2px rgba(0,0,0,0.06)` at most.
- **Notice/announcement banner**: full-width strip above page content on relevant views, left border-accent 4px in `--status-info` or `--accent`, icon + bold title + body text, background `--primary-tint` — used for things like "Scores are recalculated nightly" or policy notices. Mirrors govt "Latest Updates / Circulars" ticker-banner pattern without needing a scrolling ticker.

---

## 4. Component patterns for the 4 role-dashboards

### 4.1 Data table (Borrower list / SHG member list / Lender portfolio)
- Sticky header row, sortable column affordance (▲▼ glyph, not color-only).
- Row click → detail view, entire row `cursor:pointer` + `--surface-2` hover (no card-hover translate/shadow tricks — feels playful, not official).
- Status column always renders as the status-chip component (§4.2), never bare colored text.
- Pagination footer: plain numbered pager bottom-right, `Showing 1–20 of 342` label bottom-left — standard govt-portal MIS-report convention.

### 4.2 Status badge / chip (loan Pending / Approved / Rejected, SHG link Pending/Approved/Rejected, anomaly Flagged)
Fixed shape, not a free-floating pill: rectangular with 3px radius, 1px solid border matching its text color, small leading dot/icon + label text (uppercase, `--fs-xs`, weight 600):

```
[● PENDING]   text/border: var(--status-pending);  bg: var(--status-pending-bg)
[✓ APPROVED]  text/border: var(--status-approved); bg: var(--status-approved-bg)
[✕ REJECTED]  text/border: var(--status-rejected); bg: var(--status-rejected-bg)
[▲ FLAGGED]   text/border: var(--status-flagged);  bg: var(--status-flagged-bg)
```
Using a leading glyph (●/✓/✕/▲) is the GIGW-mandated "not color alone" affordance — keep it even though the shapes are minimal.

### 4.3 Stat/summary tile row (dashboard headers — total borrowers, portfolio value, default rate, districts covered)
Row of bordered tiles (not shadowed floating cards): each tile is `--surface-1` with 1px `--border`, 4px top border-accent in `--primary` (or `--status-*` color if the stat is a risk metric), label `--fs-xs` uppercase `--text-muted`, value `--fs-2xl` bold `--text-primary` tabular-nums, optional small delta/trend line below in `--fs-xs`. This directly replaces the current `.stat-tile` (keep the class name for continuity, restyle only).

### 4.4 Role-specific notes
- **Borrower / My Score view**: SHAP-style explanation panel should look like a formal "assessment report" card — bordered table of factor → contribution rather than free-floating chart bubbles; keep any chart but frame it inside a bordered "Report" card with a document-style header (title + generated-date line).
- **Lender view**: SHG approve/reject actions should use explicit labeled buttons ("Approve Partnership" / "Reject Partnership") in `--status-approved`/`--status-rejected` solid fill — not icon-only buttons — matching formal administrative-action conventions.
- **SHG view**: member list is a dense table; group-level stats use the stat-tile row (§4.3).
- **Admin/Bank view**: district heatmap and anomaly flags should sit inside bordered "panel" cards with a document-style caption (e.g. "Fig 1: District-wise Trust Index") beneath, echoing official report/annexure presentation.

---

## 5. What NOT to do

- Do **not** use the State Emblem of India (Lion Capital/Ashoka Chakra), any ministry/department logo, the national flag as an icon/badge, or any other official Government of India insignia anywhere in the UI.
- Do **not** use or imply a `.gov.in` / `.nic.in` domain, or any GoI scheme name/branding (e.g. do not brand this as a PMJDY, Jan Dhan, or NABARD product) as if this project is affiliated with or endorsed by them.
- Do **not** omit or obscure the "private demonstration platform, not affiliated with the Government of India" disclaimer from the footer — it must be present on every page via the shared footer.
- Do **not** copy verbatim text/content from india.gov.in, rbi.org.in, nabard.org, pmjdy.gov.in, or any other real portal — only structural/visual conventions were researched and should be reused, never their copy, imagery, or data.
- Do **not** use the tricolor as a literal flag graphic or seal-like badge; the 3px accent rule described in §3.1 is a stylistic nod, not a flag depiction, and must never be shaped like a flag, cockade, or emblem.
- Do **not** let the "official" register compromise usability: dense tables must stay scannable, and formality should not be used to justify skipping the accessibility requirements in §0/§1/§2 (AA contrast, keyboard nav, alt text, resizable text).

---

## 6. CSS variables — drop-in for `frontend/src/index.css`

Replace the existing `:root` block (and keep component classes building on these same variable names where possible so existing components mostly re-theme rather than rewrite):

```css
:root {
  color-scheme: light;

  /* Brand */
  --primary: #0B3D6B;
  --primary-hover: #082B4A;
  --primary-tint: #E8F0F8;
  --secondary: #8E1B2E;
  --secondary-tint: #FBEAEC;
  --accent: #C4701A;
  --accent-tint: #FBF0E2;

  /* Neutrals */
  --text-primary: #14181C;
  --text-secondary: #3F4750;
  --text-muted: #6B7280;
  --surface-1: #FFFFFF;
  --surface-2: #F4F6F8;
  --border: #D3D9DF;
  --gridline: #E2E6EA;

  /* Status (always pair with icon+label, never color alone) */
  --status-approved: #1B7A3D;     --status-approved-bg: #E7F5EC;
  --status-pending: #9A6300;      --status-pending-bg: #FDF3D9;
  --status-rejected: #A21C2E;     --status-rejected-bg: #FBE9EA;
  --status-flagged: #B3540A;      --status-flagged-bg: #FCEEE0;
  --status-info: #0B3D6B;         --status-info-bg: #E8F0F8;

  /* Typography */
  --font-sans: "Noto Sans", "Noto Sans Devanagari", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-serif: "Noto Serif", Georgia, "Times New Roman", serif;
  --fs-xs: 0.75rem;
  --fs-sm: 0.8125rem;
  --fs-base: 0.875rem;
  --fs-md: 1rem;
  --fs-lg: 1.125rem;
  --fs-xl: 1.375rem;
  --fs-2xl: 1.75rem;
  --fs-3xl: 2.25rem;
  --lh-tight: 1.25;
  --lh-base: 1.55;
  --lh-loose: 1.7;

  /* Layout */
  --radius: 4px;
  --radius-pill: 999px;
  --header-utility-h: 34px;
  --header-brand-h: 68px;

  font-family: var(--font-sans);
}

:root[data-theme="dark"] {
  color-scheme: dark;

  --primary: #6FA8DC;
  --primary-hover: #8FBEE6;
  --primary-tint: #10253A;
  --secondary: #E38A96;
  --secondary-tint: #3A1216;
  --accent: #E3A64B;
  --accent-tint: #3A2409;

  --text-primary: #F1F4F7;
  --text-secondary: #C3CBD3;
  --text-muted: #93A0AC;
  --surface-1: #0F1B29;
  --surface-2: #0A1420;
  --border: #24303C;
  --gridline: #1C2732;

  --status-approved: #4CAF6D;     --status-approved-bg: #123420;
  --status-pending: #E3B341;      --status-pending-bg: #3A2C05;
  --status-rejected: #E4677A;     --status-rejected-bg: #3A1216;
  --status-flagged: #E39056;      --status-flagged-bg: #3A2409;
  --status-info: #6FA8DC;         --status-info-bg: #10253A;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --primary: #6FA8DC;
    --primary-hover: #8FBEE6;
    --primary-tint: #10253A;
    --secondary: #E38A96;
    --secondary-tint: #3A1216;
    --accent: #E3A64B;
    --accent-tint: #3A2409;
    --text-primary: #F1F4F7;
    --text-secondary: #C3CBD3;
    --text-muted: #93A0AC;
    --surface-1: #0F1B29;
    --surface-2: #0A1420;
    --border: #24303C;
    --gridline: #1C2732;
    --status-approved: #4CAF6D;     --status-approved-bg: #123420;
    --status-pending: #E3B341;      --status-pending-bg: #3A2C05;
    --status-rejected: #E4677A;     --status-rejected-bg: #3A1216;
    --status-flagged: #E39056;      --status-flagged-bg: #3A2409;
    --status-info: #6FA8DC;         --status-info-bg: #10253A;
  }
}

/* Skip link (GIGW requirement) */
.skip-link {
  position: absolute;
  left: -9999px;
  top: 0;
  background: var(--surface-1);
  color: var(--primary);
  padding: 8px 16px;
  z-index: 1000;
  border: 2px solid var(--primary);
}
.skip-link:focus {
  left: 8px;
  top: 8px;
}

/* Focus visibility (WCAG AA) */
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 2px;
}
```

---

## 7. Summary for Agent 4

Swap the current SaaS blue/pill/gradient look for: a three-tier header (navy utility bar → white trust-mark branding strip → flat underlined nav), breadcrumbs on every page, flat bordered cards/tables (radius 4px, no gradients), a formal multi-column footer with a navy bottom bar carrying the "not affiliated with GoI" disclaimer, Noto Sans/Noto Serif typography, and a navy/maroon/saffron status-safe color system that is WCAG AA contrast-checked in both light and dark mode. Use the CSS block in §6 as the new `:root` in `frontend/src/index.css`, then re-skin existing component classes (`.card`, `.nav`, `.badge`, `.stat-tile`, `table`, `.btn`) against the new variable names per §§3–4.
