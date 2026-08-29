import type { Metadata } from 'next';

import { Masthead } from '@/components/ui/Chrome';
import { getCapabilities } from '@/lib/capabilities';
import { NonAdvisoryNotice } from '@/components/ui/NonAdvisoryNotice';
import { ModeProvider } from '@/lib/mode';
import './globals.css';

export const metadata: Metadata = {
  title: 'AEGIS-Market',
  description:
    'Adaptive Evidence-Gated Integrity System for Rare-Event Market Risk. ' +
    'Research-oriented market-integrity risk analysis for Indian large-cap equities.',
};

/**
 * Applies the stored theme and mode before first paint.
 *
 * Without this the page renders in the default theme and then snaps to the stored one,
 * which is worse than a slightly larger document. The script is inline, tiny, and only
 * touches dataset attributes.
 *
 * On a module route it also honours `?mode=` from the query string, ahead of the stored
 * preference. Both experiences are in the prerendered HTML and CSS hides one of them, so
 * setting the attribute here is what makes a shared research link paint research mode on
 * the first frame instead of painting product mode and swapping after hydration.
 *
 * `String.raw` is load-bearing. A plain template literal eats the backslash in `\/`, so the
 * regex below reaches the browser as `/^/(stats|...)(/|$)/` — a syntax error, and a syntax
 * error in an inline script is thrown while parsing, before the `try` around it exists. The
 * whole function silently never runs, and the flash this script is here to prevent comes
 * back. `tests/unit/test_boot_script.py` parses the emitted text to keep that from
 * recurring.
 */
const BOOT = String.raw`(function(){try{
var m=localStorage.getItem('aegis.experienceMode')||'product';
var t=localStorage.getItem('aegis.theme')||'system';
var d=document.documentElement;
var p=location.pathname;
if(p.indexOf('/research')===0)m='research';
if(/^\/(stats|scenario|weeks)(\/|$)/.test(p)){
var q=new URLSearchParams(location.search).get('mode');
if(q==='product'||q==='research')m=q;
}
d.dataset.mode=m;
d.dataset.theme=t==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t;
}catch(e){}})();`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Read here, once, and handed down. The list is static — names and unlock weeks come
  // from the manifest — so this does not make the layout dynamic; only which of them are
  // locked varies per request, and the navigation decides that from the cookie.
  const capabilities = await getCapabilities();
  return (
    <html lang="en" data-mode="product" data-theme="light" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <ModeProvider>
          <Masthead capabilities={capabilities} />
          <NonAdvisoryNotice />
          <main className="main" id="main">
            {children}
          </main>
        </ModeProvider>

        <footer className="footer">
          <div className="footer__inner">
            <p>
              AEGIS-Market is a research platform. Integrity-risk estimates describe
              evidence about market integrity over time. They are not statements about the
              merits of any security and not a basis for any transaction.
            </p>
            <p>
              Active universe: a point-in-time liquidity proxy over NSE large-cap equities
              — <strong>not the Nifty 50</strong>, for which no licence-clear constituent
              history was available. Episode labels in this release are synthetic. Every
              boundary is documented under Research → Limitations &amp; Opportunities.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
