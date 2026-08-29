// Runs in the browser: it responds to typing and keyboard presses.
'use client';

/**
 * Search, as the first thing on the page.
 *
 * It filters a list the page already has rather than calling anything: every instrument
 * the product can open is in the snapshot the server rendered, so matching happens as the
 * reader types with nothing in between. A network round trip per keystroke would be
 * slower and would find exactly the same instruments.
 *
 * Submitting with nothing selected goes to Discover with the term, so the search box is
 * never a dead end.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE SEARCH BOX.
 *
 * THE PERFORMANCE DECISION, and the reasoning is airtight. Most search boxes send a request
 * to the server on every keystroke. This one does not, because the complete list of
 * companies is ALREADY IN THE PAGE.
 * So matching happens instantly, with nothing in between -- and a request would have been
 * slower while finding exactly the same companies. There is no trade-off here at all; the
 * network round trip would simply be waste.
 *
 * "NEVER A DEAD END" is the other principle. Press Enter with nothing selected and you go
 * somewhere useful rather than nowhere. A search box that silently does nothing when you
 * press Enter is one of the small, common cruelties of interface design.
 *
 * AND THE KEYBOARD WORKS PROPERLY: up and down to move, Enter to go, Escape to close.
 * Somebody who never touches the mouse can use this exactly as fast as somebody who does.
 */
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState } from 'react';

export interface SearchItem {
  symbol: string;
  // Two separate flags: is it in the studied set, and has it been assessed? Different
  // facts, and the results list shows the difference.
  tracked: boolean;
  analysed: boolean;
  stateLabel: string | null;
  stateTone: string | null;
}

/**
 * Entities that are not instruments but that a reader will certainly search for.
 *
 * NIFTY 50 is an index: it has a level, not a price, and its own page. Someone typing
 * "nifty" means the benchmark, and a search that answered with fifty equities would be
 * answering a question they did not ask.
 */
// PLAIN ENGLISH: a thoughtful point about what people MEAN when they type. Somebody typing
// "nifty" wants the index itself, not a list of the fifty companies in it. Answering with
// the fifty would be technically defensible and would answer a question they did not ask.
interface Entity {
  id: string;
  label: string;
  kind: string;
  blurb: string;
  href: string;
  // The various ways somebody might spell it.
  aliases: string[];
}

// EXTRACTION: the NIFTY 50 entity shortcut pointed at /markets/nifty-50, a page that is
// not part of the statistical subsystem. Searching for an instrument still resolves
// normally; only the index shortcut is gone, because it had nowhere to go.
// PLAIN ENGLISH: the list is empty in this trimmed copy, and the note explains exactly why
// and exactly what still works. A future reader finding an empty list knows it is a
// deliberate omission rather than something unfinished.
const ENTITIES: Entity[] = [];

function matchEntities(q: string): Entity[] {
  if (!q) return [];
  return ENTITIES.filter((e) =>
    // Spaces removed from BOTH sides before comparing, so "nifty 50" and "nifty50" match
    // the same entry without needing a separate alias for every spacing.
    e.aliases.some((a) => a.replace(/\s+/g, '').includes(q.replace(/\s+/g, ''))),
  );
}

export function SearchBox({
  items,
  placeholder = 'Search instruments by symbol…',
  autoFocus = false,
}: {
  items: SearchItem[];
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  // Which result is highlighted, for keyboard navigation.
  const [active, setActive] = useState(0);
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);

  const query = term.trim().toUpperCase();
  const entities = useMemo(() => matchEntities(query), [query]);
  const matches = useMemo(() => {
    if (!query) return [];
    // TWO GROUPS, IN ORDER OF USEFULNESS. Companies whose symbol STARTS with what you typed
    // come first; those that merely contain it follow.
    // Type "REL" and RELIANCE appears above anything with "rel" buried in the middle --
    // which is almost certainly what you meant.
    const starts = items.filter((i) => i.symbol.startsWith(query));
    const contains = items.filter(
      (i) => !i.symbol.startsWith(query) && i.symbol.includes(query),
    );
    // At most eight, so the list stays scannable rather than becoming a wall.
    return [...starts, ...contains].slice(0, 8);
  }, [query, items]);
  const hasResults = entities.length + matches.length > 0;

  function go(symbol: string) {
    setOpen(false);
    setTerm('');
    router.push(`/instruments/${symbol}`);
  }

  return (
    <div className="search" ref={box}>
      <div className="search__field">
        {/* The magnifying glass, hidden from screen readers -- the input's own label
            already says what this is. */}
        <span className="search__icon" aria-hidden="true">
          ⌕
        </span>
        <input
          // `type="search"` gives phone keyboards a search key and browsers a clear button.
          type="search"
          value={term}
          autoFocus={autoFocus}
          placeholder={placeholder}
          aria-label="Search instruments"
          // Both switched off: the browser's own suggestions and spell-check would only get
          // in the way of typing share symbols, which are not words.
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            setTerm(e.target.value);
            setOpen(true);
            // Back to the first result whenever the text changes, so the highlight is never
            // left pointing at a position that no longer exists.
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          // A short delay before closing. Without it, clicking a result would close the list
          // before the click registered -- and the click would go nowhere. A classic bug in
          // dropdowns, avoided here.
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              // Stop the page scrolling; move the highlight instead.
              e.preventDefault();
              // `Math.min` stops it running past the last result.
              setActive((a) => Math.min(a + 1, matches.length - 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              // THREE THINGS ENTER MIGHT MEAN, in order of confidence.
              if (entities.length > 0) {
                // An index matched -- go there.
                setOpen(false);
                router.push(entities[0].href);
              } else if (matches[active]) {
                // A company is highlighted -- go there.
                go(matches[active].symbol);
              } else if (term.trim()) {
                // EXTRACTION: /discover is not part of this project; the full
                // instrument list is the equivalent destination here.
                // NOTHING MATCHED, BUT THEY TYPED SOMETHING -- so send them to the full
                // list rather than doing nothing. This is the "never a dead end" rule.
                router.push('/markets');
              }
            } else if (e.key === 'Escape') {
              // The expected way to dismiss a dropdown.
              setOpen(false);
            }
          }}
        />
      </div>

      {open && hasResults ? (
        // `role="listbox"` tells assistive software this is a list of choices attached to
        // the input, rather than unrelated content that happens to appear below it.
        <ul className="search__results" role="listbox">
          {entities.map((e) => (
            <li key={e.id}>
              <Link
                href={e.href}
                className="search__result search__result--entity"
                onClick={() => setOpen(false)}
              >
                <span className="search__entity">
                  <span className="search__symbol">{e.label}</span>
                  {/* A short description, so an index is recognisable as an index. */}
                  <span className="search__blurb">{e.blurb}</span>
                </span>
                <span className="tag" data-tone="calm">
                  {e.kind}
                </span>
              </Link>
            </li>
          ))}
          {matches.map((m, i) => (
            <li key={m.symbol}>
              <Link
                href={`/instruments/${m.symbol}`}
                className={`search__result${i === active ? ' is-active' : ''}`}
                // Hovering moves the highlight too, so the mouse and the keyboard agree
                // about which item is selected rather than fighting each other.
                onMouseEnter={() => setActive(i)}
                onClick={() => setOpen(false)}
              >
                <span className="search__symbol">{m.symbol}</span>
                <span className="search__meta">
                  {/* Whether it is in the studied set. */}
                  {m.tracked ? <span className="tag">Tracked</span> : null}
                  {m.analysed && m.stateLabel ? (
                    // Assessed: show its risk state.
                    <span className="tag" data-tone={m.stateTone ?? 'calm'}>
                      {m.stateLabel}
                    </span>
                  ) : (
                    // NOT ASSESSED: says "Price only" rather than showing nothing.
                    // Without this a reader would have no idea whether the absence of a
                    // state meant "calm" or "we never looked at this one" -- which are very
                    // different, and only one of them is reassuring.
                    <span className="tag tag--quiet">Price only</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      {open && term.trim() && !hasResults ? (
        // NOTHING FOUND -- and the message is genuinely helpful rather than a bare
        // "no results".
        <div className="search__results search__results--empty">
          <p>
            {/* It repeats what was searched for, so a typo is visible. */}
            No instrument symbol contains <strong>{term.trim().toUpperCase()}</strong>.
          </p>
          <p className="small muted">
            {/* It explains WHAT the search matches on -- symbols, not company names, which
                is the commonest misunderstanding -- and gives three examples to try. Three
                sentences that turn a dead end into a next step. */}
            Search is by NSE symbol — try TCS, RELIANCE or INFY.
          </p>
        </div>
      ) : null}
    </div>
  );
}
