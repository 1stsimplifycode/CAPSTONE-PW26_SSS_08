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
const PRODUCT_NAV = [
  { href: '/', label: 'Home' },
  { href: '/markets', label: 'Instruments' },
  { href: '/stats', label: 'STATS modules' },
  { href: '/research', label: 'Research' },
];

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
const MOBILE_PRODUCT = ['/', '/markets', '/stats', '/research'].map(
  (href) => PRODUCT_NAV.find((n) => n.href === href)!,
);
const MOBILE_RESEARCH = [
  '/research',
  '/research/statistics',
  '/research/thresholds',
  '/stats',
].map((href) => RESEARCH_NAV.find((n) => n.href === href)!);

export function ModeToggle() {
  const { mode, setMode, modeForcedByRoute } = useMode();
  return (
    <div
      className="modeToggle"
      role="radiogroup"
      aria-label="Experience mode"
      title={
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
          <span className="modeToggle__hint">
            {m === 'product' ? 'understand' : 'verify'}
          </span>
        </button>
      ))}
    </div>
  );
}

export function ThemeControl() {
  const { theme, setTheme } = useMode();
  return (
    <label className="themeControl">
      <span className="visually-hidden">Theme</span>
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value as Theme)}
        aria-label="Theme"
      >
        <option value="system">Auto</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}

export function Masthead({
  capabilities = [],
}: {
  /**
   * Kept in the signature because `app/layout.tsx` is copied verbatim and passes it. The
   * product capability registry is not part of the statistical subsystem, so nothing is
   * exported for it here and this arrives empty.
   */
  capabilities?: { id: string; name: string; href: string }[];
} = {}) {
  void capabilities;
  const { mode } = useMode();
  const pathname = usePathname() ?? '/';

  const nav: NavEntry[] = mode === 'research' ? RESEARCH_NAV : PRODUCT_NAV;
  const mobile = mode === 'research' ? MOBILE_RESEARCH : MOBILE_PRODUCT;

  return (
    <>
      <header className="masthead" data-mode={mode}>
        <div className="masthead__row">
          <Link href="/" className="masthead__title">
            AEGIS<span className="masthead__accent">-Statistics</span>
          </Link>
          <ModeToggle />
          <span className="masthead__market" title="Market covered">
            India · NSE
          </span>
          <ThemeControl />
        </div>
        <p className="masthead__sub">
          {mode === 'product'
            ? 'Understand unusual market behaviour through the evidence behind it.'
            : 'Research workspace — every number traceable to an experiment, a dataset and a seed.'}
        </p>
        <nav className="nav" aria-label="Primary">
          {nav.map((n) => {
            const active =
              n.href === '/' ? pathname === '/' : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={active ? 'nav__link is-active' : 'nav__link'}
                aria-current={active ? 'page' : undefined}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
      </header>

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
