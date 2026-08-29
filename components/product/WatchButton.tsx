// Runs in the browser: it responds to clicks and remembers things per visitor.
'use client';

/**
 * Follow something for analysis.
 *
 * "Follow" is the whole verb. It records that someone wants to come back and look, and it
 * carries no quantity, no cost and no position — a control that implied any of those would
 * be the first step toward a portfolio, and a portfolio implies the one thing this product
 * does not do.
 *
 * An index and an instrument can both be followed and are stored with their kind, so the
 * watchlist can send each to the page that exists for it.
 *
 * Kept on the server. A watchlist held only in `localStorage` disappears with the tab, is
 * invisible to the backend that might act on it, and is not something a product can
 * honestly describe as saved. Every change writes a row and an audit event; the local
 * copy below survives only as the reader for a browser that cannot reach the backend, so
 * the control degrades rather than breaking.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * A "FOLLOW" BUTTON -- AND THE CAREFUL REASONING ABOUT WHAT IT MUST NOT BECOME.
 *
 * THE FIRST PARAGRAPH IS THE MOST INTERESTING THING HERE.
 * The button records one thing: "I want to look at this again". No quantity. No price. No
 * holding.
 * Why so strict about such a small control? Because of where it would lead. Add a
 * quantity, and it becomes a position. Add a few positions, and it is a portfolio. And a
 * portfolio is a thing you manage -- which means buying and selling -- which is the one
 * activity this entire project is built not to touch.
 * So the line is drawn at the very first step, where it is easy to hold, rather than three
 * reasonable-seeming steps later where it would not be.
 * That is why the verb is "Follow" and not "Add to portfolio".
 *
 * THE SECOND IDEA: "SAVED" MUST MEAN SAVED.
 * The easy way to build this is to store it in the browser. It works instantly and needs
 * no server. And it is not really saving: it vanishes when the browser is cleared, it does
 * not follow you to another device, and no other part of the system can see it.
 * A product that says "saved" and means "until you close this tab" is misleading its user.
 * So it is stored on the server -- and the browser copy exists ONLY as a fallback for when
 * the server cannot be reached, so the button degrades gracefully instead of breaking.
 * And when it is in that fallback state, it SAYS SO, right beside itself.
 */
import { useEffect, useState } from 'react';

export const WATCHLIST_KEY = 'aegis.watchlist';

// What is stored about one followed thing. Note what is ABSENT: no quantity, no price, no
// value. The shape itself makes a position impossible to express.
export interface Followed {
  symbol: string;
  addedAt: string;
  // Which kind it is, so the watchlist can link each to the right sort of page -- an index
  // and a company have different pages.
  kind?: 'instrument' | 'index';
  label?: string;
}

// Read the browser's own copy.
export function readWatchlist(): Followed[] {
  // No browser (running on the server): hand back nothing.
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(WATCHLIST_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    // Every entry checked before being trusted. Stored data can be corrupted or edited by
    // hand, and an entry with no symbol would break whatever tried to display it. Filtering
    // here means the rest of the code can rely on the shape.
    return parsed.filter(
      (r): r is Followed =>
        typeof r === 'object' && r !== null && typeof (r as Followed).symbol === 'string',
    );
  } catch {
    // Storage switched off, or nonsense stored. An empty list, and the site works.
    return [];
  }
}

// Write the browser's own copy.
export function writeWatchlist(items: Followed[]): void {
  try {
    window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable: the list still applies for this session */
  }
}

export function WatchButton({
  symbol,
  label,
  kind = 'instrument',
}: {
  symbol: string;
  label?: string;
  kind?: 'instrument' | 'index';
}) {
  const [following, setFollowing] = useState(false);
  // Whether we have found out yet. The button stays disabled until we know, so it cannot
  // briefly show the wrong state and be clicked in that moment.
  const [ready, setReady] = useState(false);

  const [busy, setBusy] = useState(false);
  // Whether we are in the degraded, browser-only mode.
  const [offline, setOffline] = useState(false);

  // On first appearance, find out whether this is already followed.
  useEffect(() => {
    // A guard against a race: if this component disappears while the request is in the
    // air, the answer must not be applied to something that is no longer there.
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/api/aegis/watchlists', { cache: 'no-store' });
        const payload = await response.json();
        if (cancelled) return;
        if (Array.isArray(payload?.symbols)) {
          setFollowing(payload.symbols.includes(symbol.toUpperCase()));
          setOffline(false);
        } else {
          throw new Error('no watchlist');
        }
      } catch {
        // The backend is not answering. Fall back to what this browser remembers rather
        // than showing an empty list as though nothing were followed.
        // PLAIN ENGLISH: the important half is the second clause. Showing an empty list
        // would be a claim -- "you follow nothing" -- and it might be false. Falling back
        // to the browser's memory shows the best available truth, and flags that it is a
        // fallback.
        if (cancelled) return;
        setFollowing(readWatchlist().some((i) => i.symbol === symbol));
        setOffline(true);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    // The cleanup, which sets the flag when this component goes away.
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  // Follow or unfollow.
  async function toggle() {
    const next = !following;
    setBusy(true);
    try {
      const response = await fetch(
        `/api/aegis/watchlists/${next ? 'watch' : 'unwatch'}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: symbol.toUpperCase() }),
        },
      );
      const payload = await response.json();
      if (!Array.isArray(payload?.symbols)) throw new Error('refused');
      // The state is set from the SERVER'S reply, not from what we assumed. So if the
      // server disagreed for any reason, the button shows the truth rather than our guess.
      setFollowing(payload.symbols.includes(symbol.toUpperCase()));
      setOffline(false);
      // Mirror locally so a later reload without the backend still shows the truth.
      // PLAIN ENGLISH: the browser copy is kept in step with the server, purely so that if
      // the backend is unreachable later, the fallback shows something accurate rather than
      // something stale.
      writeWatchlist(
        payload.symbols.map((s: string) => ({
          symbol: s,
          // The kind and label are only known for the one just changed; the others keep
          // theirs as undefined rather than being guessed at.
          kind: s === symbol.toUpperCase() ? kind : undefined,
          label: s === symbol.toUpperCase() ? label : undefined,
          addedAt: new Date().toISOString(),
        })),
      );
    } catch {
      // It did not save. The button does NOT flip to look successful.
      setOffline(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="watchBtnWrap">
      <button
        type="button"
        className={following ? 'watchBtn is-following' : 'watchBtn'}
        onClick={() => void toggle()}
        // Disabled until we know the truth, and while a change is in flight.
        disabled={!ready || busy}
        // `aria-pressed` tells assistive software this is a toggle and which way it is set.
        // Without it, a listening reader hears a button and cannot tell whether it is on.
        aria-pressed={following}
      >
        {/* A filled or hollow star. Hidden from screen readers, because the word beside it
            already says the same thing and hearing "black star" would only get in the way. */}
        <span aria-hidden="true">{following ? '★' : '☆'}</span>
        {/* THE WORDS. "Follow for analysis" -- naming the purpose, and pointedly not
            "Add to watchlist" or anything suggesting a holding. */}
        {following ? 'Following' : 'Follow for analysis'}
      </button>
      {offline ? (
        // THE HONEST WARNING. When the change could not be saved, it says so plainly and
        // immediately, rather than letting a filled-in star imply something was stored.
        <span className="watchBtn__offline small muted" role="status">
          Not saved — the backend is not answering.
        </span>
      ) : null}
    </span>
  );
}
