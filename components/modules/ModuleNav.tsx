// Runs in the browser: it needs to know which page you are on and which mode you are in.
'use client';

/**
 * The module sidebar.
 *
 * All 16 modules are listed rather than paginated or grouped behind a menu, because a
 * researcher's most common navigation is "the one next to the one I am reading" and a
 * product user's is "what else is here". Every link carries the current mode so the
 * chosen depth survives navigation as well as the toggle.
 *
 * It is a `<nav>` with real links, not a client-side router shim: every module page is
 * prerendered, so following one is a document load that works without JavaScript.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE LIST DOWN THE SIDE.
 *
 * DESIGN DECISION 1: SHOW ALL SIXTEEN AT ONCE.
 * Sixteen is a lot for a sidebar, and the temptation is to hide most of them behind a menu.
 * The argument against is based on what people actually do:
 *   a RESEARCHER usually wants "the one next to this one" -- which requires seeing it;
 *   a PRODUCT USER usually wants "what else is here" -- which requires seeing everything.
 * Both are answered by a full list and defeated by a collapsed menu. The decision comes
 * from observing behaviour rather than from tidiness.
 *
 * DESIGN DECISION 2: EVERY LINK CARRIES THE MODE.
 * Browsing in research mode and clicking a module gets you the research view of it. Without
 * this the mode would reset on every navigation, and you would have to re-select it
 * constantly -- a small friction repeated endlessly.
 *
 * DESIGN DECISION 3: REAL LINKS.
 * These are ordinary web links, not JavaScript-powered fake ones. So they work with
 * JavaScript disabled, they can be opened in a new tab, they can be copied, and the browser
 * treats them as real navigation. Every page is built in advance, so nothing is lost by
 * doing it the plain way.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useMode } from '@/lib/mode';
import type { ResearchModule } from '@/lib/moduleTypes';

// The research lab sections, which are pages rather than modules -- hence a fixed list
// rather than something read from the module registry.
const RESEARCH_LAB = [
  { href: '/research/datasets', label: 'Datasets' },
  { href: '/research/experiments', label: 'Experiments' },
  { href: '/research/figures', label: 'Figures' },
  { href: '/research/tables', label: 'Tables' },
  { href: '/research/artifacts', label: 'Artifacts' },
  // The claim ledger, the limitations and the reproducibility record -- the three pages
  // that hold the project to account, given the same prominence as the results.
  { href: '/research/claims', label: 'Claim ledger' },
  { href: '/research/limitations', label: 'Limitations' },
  { href: '/research/reproducibility', label: 'Reproducibility' },
];

export function ModuleNav({ modules }: { modules: ResearchModule[] }) {
  const pathname = usePathname() ?? '';
  const { mode } = useMode();
  // Split into the two families.
  const stats = modules.filter((m) => m.category === 'STATS');
  const scenario = modules.filter((m) => m.category === 'SCENARIO');

  // A small helper that builds one section. Written once and used twice, so the two
  // sections cannot drift apart in appearance or behaviour.
  const section = (title: string, base: string, list: ResearchModule[]) => (
    <div className="moduleNav__section">
      {/* The heading is itself a link to the section's index page -- so the obvious click
          does something useful rather than nothing. */}
      <Link href={`${base}?mode=${mode}`} className="moduleNav__heading">
        {title}
        {/* How many there are, so a reader knows the extent of the list at a glance. */}
        <span className="moduleNav__count">{list.length}</span>
      </Link>
      <ul>
        {list.map((m) => {
          // Is this the page currently being read?
          const active = pathname === m.route;
          return (
            // `key` lets React tell the items apart when the list changes. Using the
            // module's own id rather than its position means reordering the list does not
            // confuse it.
            <li key={m.id}>
              <Link
                // The mode carried through -- design decision 2.
                href={`${m.route}?mode=${mode}`}
                className={active ? 'moduleNav__link is-active' : 'moduleNav__link'}
                // `aria-current="page"` tells screen-reader software which item is the
                // current one. Without it, a listening reader gets the highlight colour
                // and nothing else -- which is to say, nothing.
                aria-current={active ? 'page' : undefined}
              >
                {/* The number, padded so 1 shows as "01" and the list aligns neatly. */}
                <span className="moduleNav__index">
                  {String(m.index).padStart(2, '0')}
                </span>
                <span className="moduleNav__label">{m.name}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    // `<nav>` with a label, so screen-reader software can announce it as the module
    // navigation and let a listener skip past it -- which matters a great deal when the
    // list is deliberately sixteen items long.
    <nav className="moduleNav" aria-label="Research modules">
      {section('STATS', '/stats', stats)}
      {section('SCENARIO LAB', '/scenario', scenario)}
      <div className="moduleNav__section">
        {/* This heading is plain text rather than a link, because there is no single
            research-lab index page to send anybody to. Better an unclickable heading than
            a link that goes nowhere useful. */}
        <span className="moduleNav__heading">Research lab</span>
        <ul>
          {RESEARCH_LAB.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                className={
                  // `startsWith` rather than an exact match, so a deeper page such as
                  // /research/limitations/L-04 still highlights its parent section.
                  pathname.startsWith(l.href)
                    ? 'moduleNav__link is-active'
                    : 'moduleNav__link'
                }
              >
                <span className="moduleNav__label">{l.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
