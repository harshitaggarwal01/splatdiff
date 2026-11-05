# Shared site nav (same on /, /app, /family, /glasses)

Markup (replace each page's existing top bar with this; keep page-specific controls inside .site-nav__actions):

<header class="site-nav">
  <div class="site-nav__inner">
    <a class="site-nav__brand" href="/">Second Look</a>
    <nav class="site-nav__links" aria-label="Main">
      <a class="site-nav__link" href="/app">Room check</a>
      <a class="site-nav__link" href="/family">Family feed</a>
      <a class="site-nav__link" href="/glasses">In his glasses</a>
    </nav>
    <div class="site-nav__actions">
      <!-- page-specific controls (e.g. Past checks button, live indicator) go here -->
      <a class="site-nav__cta" href="/app?sample=1">Try it now</a>
    </div>
  </div>
</header>

The link for the current page gets aria-current="page". On /app the CTA stays (it loads the sample).
Styles live in web/app.css (every page links it first): sticky top:0, z-index 50, paper background (--paper) with a 1px
bottom rule (--rule); inner max-width 1120px, centred, 16px side padding, height 60px, flex, align centre, gap 28px.
Brand: Literata 600 ~1.25rem, ink. Links: Public Sans 500 .95rem, --ink-2, no underline; hover ink; aria-current ink with a
2px green (#1F5546) underline offset 6px. CTA: solid green button (paper text), 36px tall, 8px radius. Actions pushed right
(margin-left:auto). Focus-visible ring as elsewhere. Below 760px: brand + CTA on the first row, the three links on a second
row that scrolls horizontally inside itself (overflow-x:auto, no page overflow, no wrapping), height auto.
No icons needed; no emoji; no eyebrows.
