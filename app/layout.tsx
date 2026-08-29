import type { Metadata } from 'next';

import { Masthead } from '@/components/ui/Chrome';
import { getCapabilities } from '@/lib/capabilities';
import { NonAdvisoryNotice } from '@/components/ui/NonAdvisoryNotice';
import { ModeProvider } from '@/lib/mode';
import './globals.css';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE OUTERMOST FRAME. Every single page on the site sits inside this.
 *
 * Which means three things appear on every page without any page having to ask:
 *   * the masthead and menu,
 *   * THE NON-ADVISORY NOTICE -- placed here so it is structurally impossible for a page
 *     to omit it,
 *   * and the footer, which carries the project's standing caveats.
 *
 * And the odd-looking BOOT script in the middle is one of the more interesting pieces of
 * engineering in the project. It is explained at length where it appears.
 */

export const metadata: Metadata = {
  title: 'AEGIS-Market',
  description:
    // The full name spelled out, then what it actually is -- "research-oriented", stated
    // in the site's own description rather than only in the notice.
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
// PLAIN ENGLISH: THE ANTI-FLASH SCRIPT, and it solves a real and very visible problem.
//
// THE PROBLEM. The server builds the page before it has ever met your browser. So it cannot
// know you prefer dark mode. It sends a light page. Your browser then reads your preference
// and switches. You see a white flash on every single page load. Everybody has experienced
// this on some website and found it unpleasant.
//
// THE FIX. This tiny script runs FIRST, before anything is drawn. It reads your preference
// and sets the theme immediately -- so the very first thing painted is already correct.
//
// AND THEN THE THIRD PARAGRAPH DESCRIBES A GENUINELY NASTY BUG, worth reading twice.
// `String.raw` keeps backslashes exactly as written. Without it, the backslash inside the
// pattern below would be swallowed, and the script arriving at the browser would contain a
// syntax error.
// Now the sting: a syntax error in a script is detected while READING it -- before any of
// it runs. So the `try...catch` wrapped around the whole thing never gets the chance to
// exist, let alone catch anything. The script silently does nothing at all.
// No error in the console. No broken page. Just the flash quietly coming back, with nothing
// anywhere to explain why.
// So there is now a test that reads the emitted text and checks it is valid. A bug this
// invisible deserves a permanent guard.
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
// Line by line, that script:
//   reads the saved mode, defaulting to product;
//   reads the saved theme, defaulting to follow-the-system;
//   forces research mode on any /research address;
//   on a module address, lets ?mode= in the link override the saved preference -- which is
//     what makes a shared research link open in research mode on the very first frame;
//   writes both onto the page's root element, where the styling picks them up;
//   and asks the computer whether it prefers dark, for the "system" setting.
// The `try...catch` around everything means that if saved settings are switched off, the
// page still appears -- just in the default theme.

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Read here, once, and handed down. The list is static — names and unlock weeks come
  // from the manifest — so this does not make the layout dynamic; only which of them are
  // locked varies per request, and the navigation decides that from the cookie.
  // PLAIN ENGLISH: fetched ONCE for the whole site rather than by each page. And the note
  // explains why this does not force every page to be rebuilt per visitor: the LIST never
  // changes, only which entries are locked -- and that is decided further down.
  const capabilities = await getCapabilities();
  return (
    <html lang="en" data-mode="product" data-theme="light"
          // `suppressHydrationWarning` because the boot script above deliberately changes
          // these two attributes before React looks. React would otherwise report the
          // mismatch as an error -- here it is the intended behaviour.
          suppressHydrationWarning>
      <head>
        {/* The script, inline in the page. `dangerouslySetInnerHTML` has an alarming name
            because inserting raw markup is usually risky -- but this content is a fixed
            string written above, containing nothing from any user. */}
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body>
        {/* A SKIP LINK, invisible until focused. Somebody navigating by keyboard can press
            Tab once and jump straight past the whole menu to the content -- instead of
            tabbing through every navigation entry on every page. A small courtesy that
            makes an enormous difference to anybody who relies on it. */}
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <ModeProvider>
          <Masthead capabilities={capabilities} />
          {/* THE NON-ADVISORY NOTICE, IN THE ROOT LAYOUT. This is why the automatic test can
              guarantee it appears on every page: it is not added page by page, it is part of
              the frame every page sits inside. A page cannot forget it. */}
          <NonAdvisoryNotice />
          <main className="main" id="main">
            {children}
          </main>
        </ModeProvider>

        <footer className="footer">
          <div className="footer__inner">
            <p>
              {/* THE STANDING CAVEAT, on every page of the site. And read the second
                  sentence: not merely "this is not advice" but a precise statement of what
                  the estimates ARE -- descriptions of evidence over time -- followed by what
                  they are not: statements about the merits of a security, or a basis for a
                  transaction. */}
              AEGIS-Market is a research platform. Integrity-risk estimates describe
              evidence about market integrity over time. They are not statements about the
              merits of any security and not a basis for any transaction.
            </p>
            <p>
              {/* AND THE THREE BIGGEST LIMITATIONS, IN THE FOOTER OF EVERY PAGE:
                  1. The company list is our own stand-in -- and "NOT THE NIFTY 50" is in
                     bold, because that is the specific misreading to prevent.
                  2. The trouble episodes are synthetic. Stated plainly, on every page.
                  3. And a pointer to where every other boundary is documented.
                  Most projects put this in a document nobody opens. This one puts it at the
                  bottom of every single page. */}
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
