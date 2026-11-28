// The one question: "Does each finished page match its scan, and which do I need to look at?"
// (Jonathan, 2026-11-28: both PDFs at once, side by side, above and below, as spreads, laid over
// each other; the pages' match measured so only the bad ones need be looked at.) The finding is how
// many pages are to look at and why the first one is; the list under it opens on those pages, and
// "All pages" shows the rest.
//
// Each page's measures come from the server (compare.py): the quality gate's verdict on a page set
// in type (gate.py, the rebuild's), and over the whole page the ink of the finished page against the
// scan's, a page that lost its ink (a picture cut short or left out), and a page of another shape.
// The pictures are the page's preview and its finished page drawn as wide, so every overlay lines up;
// a spread is one picture of the two (the server joins them), so every view works on it too.
//
// Everything a person would link to is in the URL: the page (`page`, its id), which pages
// (`show`), page or spread (`layout`) and the view (`mode`). N and P step through the pages listed,
// beside Compare's own keys, in one legend.
import { useParams } from 'react-router'
import {
  Compare,
  DataTable,
  DataView,
  EmptyState,
  IconButton,
  PageHeader,
  RowAction,
  Skeleton,
  Status,
  TextLink,
  ToggleGroup,
  Toolbar,
  ToolbarSeparator,
  format,
  useLoad,
  useSearchParam,
  viewsOf,
  type CompareMode,
} from 'strata-react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api, keys, pageName, paths, withBase, type PageMatch } from '../api'

const MODES: CompareMode[] = ['side', 'stack', 'swipe', 'fade', 'blink', 'difference', 'match']
const isMode = (v: string): v is CompareMode => (MODES as string[]).includes(v)

/** A page's name in the list and the heading: its position, with its printed label when it has one. */
const named = (r: PageMatch) => pageName({ position: r.position, label: r.label })

/** The pages shown together: one page each, or the book's spreads (the first page alone, then 2 and 3, 4 and 5), as the pages' rows. */
export function viewsFor(rows: PageMatch[], spread: boolean): PageMatch[][] {
  return viewsOf(rows.length, spread).map(v => v.map(i => rows[i]))
}

/** The finding: how many pages are to look at, and why the first is; or that every finished page matches. */
export function describeMatches(rows: PageMatch[]): string {
  if (!rows.length) return 'No pages yet: the book has to be read and set in type first.'
  const unset = rows.filter(r => !r.finished).length
  if (unset === rows.length) return 'No page is set in type yet: set the book in type to compare its pages.'
  const look = rows.filter(r => r.look && r.finished)
  const notYet = unset ? ` ${format.count(unset, 'page')} not set yet.` : ''
  if (!look.length) return `Every finished page matches its scan.${notYet}`
  return `${format.count(look.length, 'page')} of ${format.count(rows.length - unset, 'finished page')} to look at: ${named(look[0])}, ${look[0].why[0]}.${notYet}`
}

export function CompareScreen() {
  const id = Number(useParams().bookId)
  const book = useLoad({ queryKey: keys.book(id), queryFn: () => api.book(id) })
  const matches = useLoad({ queryKey: keys.compare(id), queryFn: () => api.compare(id) })
  const rows = matches.status === 'ready' ? matches.data : undefined
  return (
    <>
      <PageHeader
        title={book.status === 'ready' ? `Compare ${book.data.title}` : 'Compare'}
        scope="Each page as scanned against the same page in the finished PDF"
        finding={rows ? { text: describeMatches(rows) } : undefined}
      />
      <DataView
        state={matches}
        isEmpty={rs => rs.length === 0}
        skeleton={<Skeleton className="aspect-[4/3] w-full max-w-3xl" />}
        empty={<EmptyState title="No pages yet">The pages are found and read from the book’s scans, then set in type; once they are, each can be compared with its scan here.</EmptyState>}
      >
        {rs => <Comparing book={id} rows={rs} />}
      </DataView>
    </>
  )
}

function Comparing({ book, rows }: { book: number; rows: PageMatch[] }) {
  const anyLook = rows.some(r => r.look && r.finished)
  const [show] = useSearchParam<'look' | 'all'>('show', { default: anyLook ? 'look' : 'all', parse: v => v === 'look' || v === 'all' })
  const [layout] = useSearchParam<'page' | 'spread'>('layout', { default: 'page', parse: v => v === 'page' || v === 'spread' })
  const [mode, setMode] = useSearchParam<CompareMode>('mode', { default: 'side', parse: isMode })
  const [pageParam, setPage] = useSearchParam<string>('page', { default: '' })

  // A page "to look at" is a finished one with faults: a page not set yet has nothing to compare, and the finding says how many there are.
  const bad = (r: PageMatch) => r.look && r.finished
  const views = viewsFor(rows, layout === 'spread').filter(v => show === 'all' || v.some(bad))
  const at = Math.max(0, views.findIndex(v => v.some(r => String(r.page_id) === pageParam)))
  const view = views[at] as PageMatch[] | undefined
  // only called while a view is shown, so `views` has one; the buttons and keys are off at either end
  const go = (i: number) => setPage(String(views[Math.min(Math.max(i, 0), views.length - 1)][0].page_id))
  const listed = show === 'all' ? rows : rows.filter(bad)

  return (
    <div className="grid gap-4">
      <Toolbar label="Pages to compare" className="flex-wrap items-center gap-2">
        <ToggleGroup
          label="Pages"
          param="show"
          options={anyLook ? [{ value: 'look', label: 'To look at' }, { value: 'all', label: 'All pages' }] : [{ value: 'all', label: 'All pages' }]}
          size="sm"
        />
        <ToolbarSeparator />
        <ToggleGroup label="Layout" param="layout" options={[{ value: 'page', label: 'Page' }, { value: 'spread', label: 'Spread' }]} size="sm" />
        <ToolbarSeparator />
        <IconButton label="Previous" icon={ChevronLeft} size="sm" variant="ghost" disabled={at <= 0} onPress={() => go(at - 1)} />
        <span role="status" className="type-body-sm tabular-nums text-muted-foreground">
          {view ? `${view.map(named).join(' and ')}: ${at + 1} of ${views.length}` : ''}
        </span>
        <IconButton label="Next" icon={ChevronRight} size="sm" variant="ghost" disabled={at >= views.length - 1} onPress={() => go(at + 1)} />
      </Toolbar>

      {view ? (
        <>
          <Compare
            key={layout}
            label={`${view.map(named).join(' and ')}, scan and finished`}
            blind={false}
            missing={view.some(r => !r.finished) ? 'Not set in type yet' : 'Picture not drawn yet'}
            mode={mode}
            onModeChange={setMode}
            modes={MODES}
            maxHeight="fit"
            reserve={24}
            cannotCompare="Could not read the pages’ pictures to compare them."
            extraShortcuts={[
              { keys: ['p'], label: 'Previous page', run: () => go(at - 1), disabled: at <= 0 },
              { keys: ['n'], label: 'Next page', run: () => go(at + 1), disabled: at >= views.length - 1 },
            ]}
            a={{
              id: 'scan',
              label: 'Scan',
              media: {
                kind: 'image',
                src: withBase(view.length > 1 ? paths.spread(book, view.map(r => r.page_id), 'scan') : paths.pageImage(view[0].page_id, 'preview')),
                alt: `${view.map(named).join(' and ')} as scanned`,
              },
            }}
            b={{
              id: 'finished',
              label: 'Finished',
              media: {
                kind: 'image',
                src: withBase(view.length > 1 ? paths.spread(book, view.map(r => r.page_id), 'finished') : paths.finishedImage(view[0].page_id)),
                alt: `${view.map(named).join(' and ')} as finished`,
              },
            }}
          />
          <ul aria-label="What was found" className="grid gap-1">
            {view.map(r => (
              <li key={r.page_id} className="flex flex-wrap items-baseline gap-2 type-body-sm">
                <Verdict r={r} />
                <TextLink to={`/pages/${r.page_id}`}>{named(r)}</TextLink>
                <span className="text-muted-foreground">{explain(r)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <EmptyState title="No page to look at">Every finished page matches its scan. Choose “All pages” to look through them anyway.</EmptyState>
      )}

      {listed.length > 0 && (
        <DataTable
          caption={show === 'all' ? 'Every page, scan against finished' : 'Pages to look at'}
          rows={listed}
          rowKey={r => String(r.page_id)}
          columns={[
            { key: 'page', header: 'Page', value: r => r.position, cell: r => named(r) },
            // to look at first, then those that match, then those not set
            { key: 'state', header: 'State', value: r => (!r.finished ? 2 : r.look ? 0 : 1), cell: r => <Verdict r={r} /> },
            { key: 'kind', header: 'Kind', value: r => r.kind, hideBelow: 'sm' },
            { key: 'ink', header: 'Ink agrees', numeric: true, value: inkOf, cell: r => format.share(inkOf(r)) },
            { key: 'why', header: 'Found', truncate: true, cell: r => r.why.join('; ') || 'Nothing', hideBelow: 'md' },
            { key: 'open', header: 'Compare', hideHeader: true, cell: r => <RowAction label="Compare" subject={named(r)} onPress={() => setPage(String(r.page_id))} /> },
          ]}
        />
      )}
    </div>
  )
}

/** How well the page's ink agrees, or null before it is set. */
const inkOf = (r: PageMatch) => r.match?.ink ?? null

/** The page's state in a word. */
function Verdict({ r }: { r: PageMatch }) {
  if (!r.finished) return <Status tone="neutral">Not set</Status>
  return r.look ? <Status tone="warning">Look</Status> : <Status tone="success">Matches</Status>
}

/** The measures and faults of one page, as a sentence: the ink's agreement first, then what else was found (the ink fault is the same number). */
export function explain(r: PageMatch): string {
  if (!r.match) return 'Not set in type yet.'
  const ink = `The ink agrees ${format.share(r.match.ink)}.`
  const others = r.why.filter(w => !w.startsWith('the ink agrees'))
  const gate = r.gate?.passed ? ' The type passed its checks.' : ''
  const why = others.length ? ` ${others.map(w => w[0].toUpperCase() + w.slice(1)).join('. ')}.` : ''
  return `${ink}${gate}${why}`
}
