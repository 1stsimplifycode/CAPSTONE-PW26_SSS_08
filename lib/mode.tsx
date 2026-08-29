// This line tells Next.js that this file runs in the visitor's BROWSER, not on the server.
// It has to, because it deals with clicks, saved preferences and the current web address --
// all things that only exist once a person is actually looking at the page.
'use client';

/**
 * Experience mode: PRODUCT answers "what is happening", RESEARCH answers "how do we know".
 *
 * Four properties the brief calls for, and the reasons they are separate concerns:
 *
 * 1. **Mode is independent of theme.** Light/dark is a rendering preference; product/
 *    research changes what information is shown. Storing them in one key would couple two
 *    unrelated decisions and make each harder to reason about.
 * 2. **Mode persists, and a research URL activates research mode.** Someone who lands on
 *    `/research/...` from a link is a researcher for that visit, whatever their stored
 *    preference says; the preference is not overwritten by that inference.
 * 3. **Context survives the switch.** Switching mode while viewing an instrument keeps the
 *    instrument, the date and the event, because sending a user back to Home to punish
 *    them for wanting more depth is the opposite of the intent.
 * 4. **A module route never navigates on a mode switch.** Every module page — the 32
 *    STATS modules, the 8 Scenario Lab modules and the 16 weekly
 *    pages — carries both
 *    experiences in one page, so switching depth there changes the section that
 *    renders and nothing else. The mode is written into the query string as well, so
 *    a module URL reproduces the exact view someone was looking at.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * TWO WAYS TO READ THE SAME SITE.
 *
 *   PRODUCT MODE  -- "what is happening?" Plain, direct, for a general reader.
 *   RESEARCH MODE -- "how do we know?" The evidence, the caveats, the workings.
 *
 * Same site, same pages, different depth. And the four rules below are all really about
 * one thing: NEVER PUNISH SOMEBODY FOR WANTING MORE DETAIL.
 *
 * RULE 1 -- MODE IS NOT THEME.
 * Dark mode changes how the page LOOKS. Research mode changes what it SAYS. Two completely
 * different decisions, so they are stored separately. Bundle them together and one day
 * somebody switching to dark mode would find the content had changed too.
 *
 * RULE 2 -- A RESEARCH LINK OPENS IN RESEARCH MODE.
 * Follow a link to a research page and you get research mode, whatever you normally use.
 * And note the careful bit: your saved preference is NOT overwritten by that. Following one
 * link is not the same as changing your mind, and the code respects the difference.
 *
 * RULE 3 -- SWITCHING KEEPS YOUR PLACE.
 * You are looking at one company on one date, and you want more depth. You should get more
 * depth ABOUT THAT COMPANY -- not be dumped back at the front page. The docstring names
 * this exactly: doing otherwise "is the opposite of the intent".
 *
 * RULE 4 -- ON A MODULE PAGE, SWITCHING DOES NOT MOVE YOU AT ALL.
 * Those pages contain both versions already. Switching just reveals a different section --
 * no page load, no waiting, nothing jumping about. And the choice is written into the web
 * address, so if you share the link, the person receiving it sees exactly what you saw.
 */
// Next.js tools for reading the current address and moving between pages.
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

// The two modes and the three theme choices, written as fixed lists so a typo is caught
// while writing rather than at midnight by a visitor.
export type ExperienceMode = 'product' | 'research';
export type Theme = 'light' | 'dark' | 'system';

// The names under which the two preferences are saved in the browser. SEPARATE names --
// this is rule 1, made real in two lines.
const MODE_KEY = 'aegis.experienceMode';
const THEME_KEY = 'aegis.theme';

/** Routes that render both experiences in one page and must not navigate on a switch. */
// A pattern matching any address starting /stats, /scenario or /weeks. Those pages hold
// both versions at once, so switching there must not move anybody.
export const MODULE_ROUTE = /^\/(stats|scenario|weeks)(\/|$)/;

export function isModuleRoute(pathname: string): boolean {
  return MODULE_ROUTE.test(pathname);
}

/** Context carried across a mode switch so depth never costs the user their place. */
export interface ModeContextValue {
  mode: ExperienceMode;
  setMode: (m: ExperienceMode) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** Instrument, event and date the user is currently looking at, if any. */
  // THE "WHERE YOU ARE" MEMORY. This is what makes rule 3 possible.
  context: { instrument?: string; event?: string; date?: string };
  setContext: (c: { instrument?: string; event?: string; date?: string }) => void;
  /** True when the current route forced the mode, rather than the stored preference. */
  // So the interface can explain WHY it is in research mode -- "because of this link",
  // rather than leaving somebody puzzled that their preference appears to have changed.
  modeForcedByRoute: boolean;
}

// A "context" is React's way of making a value available to every part of the page without
// passing it down by hand through every layer in between.
const Ctx = createContext<ModeContextValue | null>(null);

// Read a saved preference from the browser.
function readStored<T extends string>(key: string, fallback: T): T {
  // On the server there is no browser and no `window`, so return the default. Without this
  // check the whole page would fail to build.
  if (typeof window === 'undefined') return fallback;
  try {
    const v = window.localStorage.getItem(key);
    return (v as T) ?? fallback;
  } catch {
    // Saved settings can be switched off entirely -- a private window, or a strict browser
    // setting. Then we simply use the default. The site works; it just does not remember.
    return fallback;
  }
}

// Does the current address demand a particular mode?
export function routeMode(pathname: string): ExperienceMode | null {
  if (pathname.startsWith('/research')) return 'research';
  // null means "the address does not care -- use whatever the person prefers".
  return null;
}

// The component that holds all this state for the whole site.
export function ModeProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/';
  const router = useRouter();

  const forced = routeMode(pathname);
  // First render must match the server output, so start from the default and adopt the
  // stored preference in an effect. Reading localStorage during render would produce a
  // hydration mismatch on every visit by a returning user.
  // PLAIN ENGLISH: a classic and genuinely tricky web problem, handled correctly.
  // The page is built on the server first, then the browser takes over. Both must produce
  // the SAME first version, or React complains loudly and the page can flicker.
  // The server cannot know your saved preference -- it has never met your browser. So if
  // the browser read the preference immediately, it would produce a different first version
  // and mismatch every single time a returning visitor arrived.
  // The fix: start with the default (matching the server), then apply the saved preference
  // a moment later, once the page is safely up.
  const [stored, setStored] = useState<ExperienceMode>('product');
  const [theme, setThemeState] = useState<Theme>('system');
  const [context, setContextState] = useState<ModeContextValue['context']>({});
  const [hydrated, setHydrated] = useState(false);

  // This runs AFTER the first render -- the safe moment to read saved preferences.
  // The empty `[]` at the end means "only once, when the page first appears".
  useEffect(() => {
    setStored(readStored<ExperienceMode>(MODE_KEY, 'product'));
    setThemeState(readStored<Theme>(THEME_KEY, 'system'));
    setHydrated(true);
  }, []);

  // The address wins if it demands a mode; otherwise the person's preference does. This
  // one line is rule 2.
  const mode: ExperienceMode = forced ?? stored;

  // Apply the mode and theme to the page itself.
  useEffect(() => {
    if (!hydrated) return;
    const root = document.documentElement;
    // Written onto the page's root element, so the styling can respond to them without any
    // further code.
    root.dataset.mode = mode;
    const resolved =
      theme === 'system'
        // "system" means "whatever this person's computer is set to" -- which is asked here.
        ? window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light'
        : theme;
    root.dataset.theme = resolved;
    // The list at the end says "redo this whenever any of these change".
  }, [mode, theme, hydrated]);

  // Remember a mode choice.
  const persist = useCallback((m: ExperienceMode) => {
    setStored(m);
    try {
      window.localStorage.setItem(MODE_KEY, m);
    } catch {
      /* storage unavailable: the mode still applies for this session */
      // PLAIN ENGLISH: saving failed, and that is survivable. The choice still works for
      // this visit; it just will not be remembered next time. Far better than an error.
    }
  }, []);

  // WHAT HAPPENS WHEN SOMEBODY SWITCHES MODE.
  const setMode = useCallback(
    (m: ExperienceMode) => {
      persist(m);

      // A module page holds both experiences. Switching there is a change of depth, not
      // of place, so the route stays and only the query records which depth is showing.
      // RULE 4. `router.replace` changes the address WITHOUT adding a history entry, so the
      // back button still goes where the visitor expects rather than stepping back through
      // every mode toggle. And `scroll: false` keeps the page exactly where it was -- no
      // jump to the top, which would be maddening halfway down a long page.
      if (isModuleRoute(pathname)) {
        router.replace(`${pathname}?mode=${m}`, { scroll: false });
        return;
      }

      // Carry the current subject across the switch rather than resetting to Home.
      // RULE 3. Whatever you were looking at is packed into the new address.
      const params = new URLSearchParams();
      if (context.instrument) params.set('instrument', context.instrument);
      if (context.event) params.set('event', context.event);
      if (context.date) params.set('date', context.date);
      const qs = params.toString() ? `?${params.toString()}` : '';
      if (m === 'research' && !pathname.startsWith('/research')) {
        router.push(`/research${qs}`);
      } else if (m === 'product' && pathname.startsWith('/research')) {
        // Going back to the plain view: return to the company you were reading about, or the
        // front page only if there was no company. Again -- your place is kept.
        router.push(context.instrument ? `/instruments/${context.instrument}` : '/');
      }
    },
    [context, pathname, router, persist],
  );

  // Remember a theme choice. Same pattern, separate storage -- rule 1 again.
  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try {
      window.localStorage.setItem(THEME_KEY, t);
    } catch {
      /* ignore */
    }
  }, []);

  // Update what the visitor is currently looking at.
  const setContext = useCallback((c: ModeContextValue['context']) => {
    // `{...prev, ...c}` merges the new details over the old, so setting just the date does
    // not wipe out the company.
    setContextState((prev) => ({ ...prev, ...c }));
  }, []);

  // Bundle it all up for the rest of the site. `useMemo` rebuilds this only when something
  // in it actually changed, which stops the whole page redrawing unnecessarily.
  const value = useMemo<ModeContextValue>(
    () => ({
      mode,
      setMode,
      theme,
      setTheme,
      context,
      setContext,
      modeForcedByRoute: forced !== null,
    }),
    [mode, setMode, theme, setTheme, context, setContext, forced],
  );

  return (
    <Ctx.Provider value={value}>
      {/* `useSearchParams` opts its whole subtree out of prerendering. Isolating it in
          this leaf keeps every page server-rendered; putting it in the provider made
          client-component pages ship a blank shell until JavaScript loaded. */}
      {/* PLAIN ENGLISH: a real bug, and a neat fix. Reading the address's query part forces
          everything around it to wait for the browser rather than being built in advance.
          When that reading lived in the main provider, it disabled advance building for the
          ENTIRE SITE -- so visitors got a blank page until the JavaScript downloaded and ran.
          Moving that one reading into this tiny isolated component means only this
          near-empty leaf waits. Everything else is built in advance and arrives instantly. */}
      <Suspense fallback={null}>
        <QuerySync onMode={persist} />
      </Suspense>
      {children}
    </Ctx.Provider>
  );
}

/**
 * Restores state from the query string: the subject on a deep-linked research route, and
 * the mode on a shared module URL.
 *
 * A shared `?mode=research` link has to open in research mode for the person receiving
 * it, which is the whole point of putting the mode in the URL. It updates the stored
 * preference too, because someone who follows a research link and keeps browsing is
 * expressing a preference.
 */
// PLAIN ENGLISH: this is the receiving end of a shared link. Somebody sends you a research
// view; you open it and see exactly what they saw.
// And a nice judgement in the last sentence: following such a link DOES update your saved
// preference here. Why the difference from rule 2? Because on a module page you can see the
// toggle and you are staying on that page -- carrying on from there really is a choice. On
// a one-off research URL you may just be glancing at a link somebody sent, so it does not
// stick. The distinction is deliberate, and about intent.
function QuerySync({ onMode }: { onMode: (m: ExperienceMode) => void }) {
  const search = useSearchParams();
  const pathname = usePathname() ?? '/';
  const { setContext } = useMode();
  // Pull the details out of the address. `?? undefined` turns a missing value into a clean
  // "not set" rather than an empty string.
  const instrument = search?.get('instrument') ?? undefined;
  const event = search?.get('event') ?? undefined;
  const date = search?.get('date') ?? undefined;
  const queryMode = search?.get('mode') ?? undefined;

  // Restore what the sender was looking at.
  useEffect(() => {
    if (instrument || event || date) setContext({ instrument, event, date });
  }, [instrument, event, date, setContext]);

  // And restore the mode, on module pages only.
  useEffect(() => {
    if (!isModuleRoute(pathname)) return;
    // The explicit check against both valid values means a nonsense address like
    // "?mode=banana" is simply ignored rather than putting the site into an unknown state.
    if (queryMode === 'product' || queryMode === 'research') onMode(queryMode);
  }, [pathname, queryMode, onMode]);

  // This component displays nothing at all. Its entire job is the two effects above.
  return null;
}

// How any part of the site asks about the current mode.
export function useMode(): ModeContextValue {
  const v = useContext(Ctx);
  // A loud, clear error if somebody uses this outside the provider -- naming exactly what
  // is missing. Far better than a mysterious null crash three components away.
  if (!v) throw new Error('useMode must be used inside <ModeProvider>');
  return v;
}

/** Registers the subject of the current page so a mode switch can carry it. */
export function useSubject(subject: {
  instrument?: string;
  event?: string;
  date?: string;
}) {
  // PLAIN ENGLISH: a page uses this to announce "I am about Reliance, on this date". That
  // is what fills the memory that rule 3 then carries across a mode switch. Each page says
  // what it is about, once, and the switching behaviour follows automatically.
  const { setContext } = useMode();
  const { instrument, event, date } = subject;
  useEffect(() => {
    setContext({ instrument, event, date });
  }, [instrument, event, date, setContext]);
}
