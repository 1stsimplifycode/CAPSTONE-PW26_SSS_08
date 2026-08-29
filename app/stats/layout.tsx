import { ModuleLayout } from '@/components/modules/ModuleLayout';

/**
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE FRAME AROUND EVERY /stats PAGE.
 *
 * In Next.js, a file called `layout` wraps every page in its folder and every folder
 * beneath it. So this one file puts the module sidebar around all sixteen module pages
 * plus the index -- without any of them having to ask for it.
 *
 * It is four lines because all the work lives in `ModuleLayout`. That matters: the sidebar
 * is defined once, so it cannot look one way on one module page and another way on the
 * next.
 */
export default function StatsLayout({ children }: { children: React.ReactNode }) {
  // `children` is whichever page is being shown. The layout wraps it and knows nothing
  // else about it -- which is why one layout can serve every page underneath.
  return <ModuleLayout>{children}</ModuleLayout>;
}
