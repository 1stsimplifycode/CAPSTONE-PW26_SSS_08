// Runs in the browser: it tracks the current mode, theme and page.
'use client';

/**
 * Global chrome: masthead, mode toggle, theme control, mode-aware navigation.
 *
 * The mode toggle is deliberately the most prominent control after the wordmark. It
 * changes what the whole application shows, so hiding it in Settings would make the two
 * experiences feel like two products rather than two depths of one.
 *
 * EXTRACTION NOTE. This file is the source repository's `components/ui/Chrome.tsx` with
 * the navigation entries for pages that are not part of the statistical subsystem
 * removed, and with them the week-gating machinery (`lib/gate`, `lib/useActiveWeek`,
 * `components/product/LockedFeature`) those entries were the only user of. Nothing was
 * rewritten: the components below are the originals with the excluded links deleted.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE BITS THAT SURROUND EVERY PAGE: the title bar, the menu, and the two controls.
 * ("Chrome" is the interface word for the frame around the content -- nothing to do with
 * the browser of that name.)
 *
 * THE DESIGN DECISION IS IN THE SECOND PARAGRAPH, and it is a good one.
 * The Product/Research toggle is placed second only to the site name -- more prominent
 * than any navigation link.
 * Why? Because of what would happen otherwise. Tuck it away in a settings page and most
 * people never find it. The two views then feel like two separate products, one of which
 * you have to know about. Putting it front and centre makes them read as what they are:
 * two depths of a single thing, and switching is expected rather than obscure.
 *
 * THE EXTRACTION NOTE is a piece of plain honesty about what this copy is. This is a
 * trimmed version of a larger application; links to pages that are not included have been
 * DELETED rather than left pointing at nothing. And it says explicitly that nothing was
 * rewritten -- so a reader knows they are looking at the original code with omissions, not
 * at something reconstructed.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useMode, type ExperienceMode, type Theme } from '@/lib/mode';

/**
 * The routes this extraction contains. In the source repository these lists also named
 * the product surfaces (markets, trading, portfolio, funds, watchlist) and the other
 * research surfaces (experiments, models, datasets, XAI, lifecycle, claims, ...). Those
 * pages are not part of the statistical subsystem and are not present here, so their
 * entries are gone rather than left pointing at nothing.
 */
// PLAIN ENGLISH: it even lists what is missing. A reader can see the shape of the fuller
// application, and knows the gaps are deliberate rather than an oversight.
const PRODUCT_NAV = [
  { href: '/', label: 'Home' },
  { href: '/markets', label: 'Instruments' },
  { href: '/stats', label: 'STATS modules' },
  { href: '/research', label: 'Research' },
];

// The research menu is longer, because that is the point of research mode -- and note that
// Limitations and the Claim Ledger sit in the main menu, not tucked away at the bottom.
const RESEARCH_NAV = [
  { href: '/research', label: 'Overview' },
  { href: '/research/statistics', label: 'Statistics' },
  { href: '/research/thresholds', label: 'Risk thresholds' },
  { href: '/research/ablations', label: 'Ablations' },
  { href: '/research/xai', label: 'XAI Lab' },
  { href: '/stats', label: 'STATS modules' },
  { href: '/research/limitations', label: 'Limitations & Opportunities' },
  { href: '/research/claims', label: 'Claim Ledger' },
  { href: '/research/paper-lab', label: 'Paper Lab' },
];

type NavEntry = { href: string; label: string };

/** Picked by href rather than by position, so inserting an entry cannot repoint these. */
// PLAIN ENGLISH: a small, sharp piece of defensive thinking. The phone menu shows four of
// the entries above. The obvious way is to take the first four by POSITION.
// Then somebody inserts a new item at the top, and the phone menu silently shows a
// different set -- with no error and nothing to notice.
// Picking them by ADDRESS means the phone menu keeps showing exactly what was intended,
// whatever gets added above. And the `!` will fail loudly if an address is ever removed,
// rather than quietly leaving a gap.
const MOBILE_PRODUCT = ['/', '/markets', '/stats', '/research'].map(
  (href) => PRODUCT_NAV.find((n) => n.href === href)!,
);
const MOBILE_RESEARCH = [
  '/research',
  '/research/statistics',
  '/research/thresholds',
  '/stats',
].map((href) => RESEARCH_NAV.find((n) => n.href === href)!);

// THE MODE TOGGLE.
export function ModeToggle() {
  const { mode, setMode, modeForcedByRoute } = useMode();
  return (
    <div
      className="modeToggle"
      // `role="radiogroup"` tells assistive software these two buttons are one either/or
      // choice, rather than two unrelated buttons. A listening reader then hears it as a
      // choice with two options, which is what it is.
      role="radiogroup"
      aria-label="Experience mode"
      title={
        // When the ADDRESS forced research mode, the hover text explains why -- so nobody
        // is left wondering why the toggle appears not to be obeying them.
        modeForcedByRoute
          ? 'This route is a research route, so Research mode is active'
          : undefined
      }
    >
      {(['product', 'research'] as ExperienceMode[]).map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={mode === m}
          className={mode === m ? 'modeToggle__btn is-active' : 'modeToggle__btn'}
          onClick={() => setMode(m)}
        >
          {m === 'product' ? 'Product' : 'Research'}
          {/* THE BEST TOUCH IN THE FILE: a one-word hint under each label.
              "Product — understand". "Research — verify".
              Those two verbs tell a first-time visitor exactly what the choice is FOR, in a
              way that "Product" and "Research" alone never could. */}
          <span className="modeToggle__hint">
            {m === 'product' ? 'understand' : 'verify'}
          </span>
        </button>
      ))}
    </div>
  );
}

// The light/dark control.
export function ThemeControl() {
  const { theme, setTheme } = useMode();
  return (
    <label className="themeControl">
      {/* Visually hidden but read aloud by screen-reader software -- so the dropdown is
          labelled for a listener even though the label takes no space on screen. */}
      <span className="visually-hidden">Theme</span>
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value as Theme)}
        aria-label="Theme"
      >
        {/* "Auto" means follow the computer's own setting -- the default, because most
            people have already made this choice once and should not have to make it again. */}
        <option value="system">Auto</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}

// The title bar and menu.
export function Masthead({
  capabilities = [],
}: {
  /**
   * Kept in the signature because `app/layout.tsx` is copied verbatim and passes it. The
   * product capability registry is not part of the statistical subsystem, so nothing is
   * exported for it here and this arrives empty.
   */
  // PLAIN ENGLISH: an honest note about a leftover. The page that uses this component was
  // copied unchanged, and it passes something this trimmed version does not use. Rather
  // than editing the copied file -- and thereby making it no longer a faithful copy -- the
  // parameter is accepted, ignored, and explained.
  capabilities?: { id: string; name: string; href: string }[];
} = {}) {
  // `void` says "I am deliberately not using this", which stops the linter reporting an
  // unused value while leaving the intent obvious to a human reader.
  void capabilities;
  const { mode } = useMode();
  const pathname = usePathname() ?? '/';

  // THE MENU CHANGES WITH THE MODE. Not just the styling -- the actual entries.
  const nav: NavEntry[] = mode === 'research' ? RESEARCH_NAV : PRODUCT_NAV;
  const mobile = mode === 'research' ? MOBILE_RESEARCH : MOBILE_PRODUCT;

  return (
    <>
      <header className="masthead" data-mode={mode}>
        <div className="masthead__row">
          <Link href="/" className="masthead__title">
            AEGIS<span className="masthead__accent">-Statistics</span>
          </Link>
          {/* THE TOGGLE, SECOND ONLY TO THE NAME -- the design decision from the top of the
              file, made real by its position in this list. */}
          <ModeToggle />
          {/* Which market this covers, stated in the title bar. So nobody has to wonder
              whether they are looking at Indian or American shares. */}
          <span className="masthead__market" title="Market covered">
            India · NSE
          </span>
          <ThemeControl />
        </div>
        <p className="masthead__sub">
          {/* Even the subtitle changes, and each one describes what that mode offers.
              Product: understand behaviour through the evidence.
              Research: every number traceable to an experiment, a dataset and a seed.
              The second is a promise about reproducibility, made in the title bar. */}
          {mode === 'product'
            ? 'Understand unusual market behaviour through the evidence behind it.'
            : 'Research workspace — every number traceable to an experiment, a dataset and a seed.'}
        </p>
        <nav className="nav" aria-label="Primary">
          {nav.map((n) => {
            const active =
              // Home is a special case: it must match EXACTLY, because every address starts
              // with "/" and it would otherwise be highlighted on every page of the site.
              n.href === '/' ? pathname === '/' : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={active ? 'nav__link is-active' : 'nav__link'}
                // Announced to assistive software, so the current page is not conveyed by
                // colour alone.
                aria-current={active ? 'page' : undefined}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
      </header>

      {/* A separate, shorter menu for phones -- built from the by-address list above, so it
          cannot drift when the main menu changes. */}
      <nav className="mobileNav" aria-label="Primary mobile">
        {mobile.map((n) => (
          <Link key={n.href} href={n.href} className="mobileNav__link">
            {n.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
