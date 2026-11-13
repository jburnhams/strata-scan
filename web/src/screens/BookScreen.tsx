// The one question: "How did this book come out, and which pages need me?" The finding says where
// the work is (a stage running, an error, pages to look at, or done); the running stage is a
// JobStatus polled through useJob, which reads the pages again once it ends. Then three tabs in the
// URL (?tab=pictures): the pages as pictures in reading order (each one a link to its editor, the
// unsure ones marked), the pictures found, and the files to download.
//
// One filled button: "Make the files" (export) is what a person does after fixing pages; reading
// again and finding the pages again are outline, and every run is refused while one is going.
import { useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import {
  AsyncButton,
  DataView,
  EmptyState,
  JobStatus,
  LinkCard,
  LinkCardList,
  PageHeader,
  Skeleton,
  Status,
  Tabs,
  Thumbnail,
  format,
  useAsyncAction,
  useJob,
  useLoad,
  type AsyncLabels,
  type Load,
} from 'strata-react'
import { api, describeBook, fileNames, keys, pageName, paths, stageWord, withBase, type Book, type FileName, type PageSummary, type Stage } from '../api'

const tabs = [
  { value: 'pages', label: 'Pages' },
  { value: 'pictures', label: 'Pictures' },
  { value: 'files', label: 'Files' },
]

/** What each export is, for its link. */
export const fileWords: Record<FileName, { title: string; description: string }> = {
  'book.md': { title: 'Markdown', description: 'The text in paragraphs, running heads dropped, pictures where they stand.' },
  'book.txt': { title: 'Plain text', description: 'Every page’s text as it was read or typed, page by page.' },
  'book.pdf': { title: 'Searchable PDF', description: 'The pages as pictures with their text behind them, to search and copy.' },
  'book.zip': { title: 'Everything', description: 'The three files and the pictures, in one zip.' },
}

/** A page that needs a person: the page finder was unsure and nobody has looked, or reading it failed. */
export const needsLook = (p: PageSummary) => Boolean(p.error) || (!p.hand && p.confidence < 0.6)

/** The page's finding, from the book and (once read) its pages. */
export function describeWork(b: Book, pages: PageSummary[] | undefined): string {
  if (b.error || b.stage !== 'idle') return describeBook(b)
  if (!b.pages) return 'No pages yet: find them from the scans with “Find pages again”.'
  const look = pages?.filter(needsLook) ?? []
  if (look.length) return `${format.count(look.length, 'page')} need a look: the page finder was unsure where ${look.length === 1 ? 'it is' : 'they are'}. ${pageName(look[0])} is first.`
  if (!b.files?.['book.md']) return `${describeBook(b)} The files are not made yet.`
  return `${describeBook(b)} The files are up to date as of ${format.dateTime(new Date(Math.max(...Object.values(b.files)) * 1000))}.`
}

export function BookScreen() {
  const id = Number(useParams().bookId)
  const queryClient = useQueryClient()
  const job = useJob({
    queryKey: keys.book(id),
    queryFn: () => api.book(id),
    isRunning: b => b.stage !== 'idle',
    invalidates: [keys.pages(id), keys.bookFigures(id), keys.books],
  })
  const pages = useLoad({ queryKey: keys.pages(id), queryFn: () => api.pages(id) })

  const started = () => {
    void queryClient.invalidateQueries({ queryKey: keys.book(id) })
    job.poll()
  }
  const book = job.status === 'ready' ? job.data : undefined

  return (
    <>
      <PageHeader
        title={book?.title ?? 'Book'}
        scope={book ? [book.author, `${format.count(book.scans, 'scan')} from ${book.source.split('/').pop()}`].filter(Boolean).join(' · ') : undefined}
        finding={book ? { text: describeWork(book, pages.status === 'ready' ? pages.data : undefined) } : undefined}
        actions={
          <div className="flex flex-wrap gap-2">
            <RunButton book={id} stages={['detect', 'read', 'export']} busy={job.running} onStarted={started} labels={{ idle: 'Find pages again', pending: 'Starting…', done: 'Started' }} />
            <RunButton book={id} stages={['read', 'export']} busy={job.running} onStarted={started} labels={{ idle: 'Read again', pending: 'Starting…', done: 'Started' }} />
            <RunButton book={id} stages={['export']} busy={job.running} onStarted={started} labels={{ idle: 'Make the files', pending: 'Making…', done: 'Started' }} primary />
          </div>
        }
      />
      {book && (book.stage !== 'idle' || book.error) && (
        <JobStatus
          label={`Work on ${book.title}`}
          running={book.stage !== 'idle'}
          words={{ running: stageWord[book.stage], finished: 'Done', failed: 'Stopped' }}
          summary={describeBook(book)}
          current={book.total ? book.done : undefined}
          total={book.total || undefined}
          failed={Boolean(book.error)}
        />
      )}
      <DataView state={job} isEmpty={() => false} skeleton={<Skeleton className="h-10 w-full max-w-xl" />} empty={<span />}>
        {b => (
          <Tabs param="tab" items={tabs} label="The book">
            {tab => (tab === 'pictures' ? <Pictures book={b} /> : tab === 'files' ? <Files book={b} /> : <Pages pages={pages} />)}
          </Tabs>
        )}
      </DataView>
    </>
  )
}

/** Starts stages on the book; refused (disabled) while a stage runs. Says why it could not start under itself. */
function RunButton({ book, stages, busy, onStarted, labels, primary = false }: { book: number; stages: Stage[]; busy: boolean; onStarted: () => void; labels: AsyncLabels; primary?: boolean }) {
  const run = useAsyncAction(async () => {
    await api.run(book, stages)
    onStarted()
  })
  return (
    <span className="grid gap-1">
      <AsyncButton disabled={busy || run.phase === 'pending'} variant={primary ? 'default' : 'outline'} phase={run.phase} error={run.error} onClick={() => void run.run()} labels={labels} />
      {run.phase === 'error' && <span className="type-caption text-danger">{run.error}</span>}
    </span>
  )
}

function GridSkeleton() {
  return (
    <ul className="grid grid-cols-3 gap-4 sm:grid-cols-5 lg:grid-cols-7" aria-hidden>
      {Array.from({ length: 14 }, (_, i) => <li key={i}><Skeleton className="aspect-[2/3] w-full" /></li>)}
    </ul>
  )
}

/** The pages in reading order, as pictures that open the page. */
export function Pages({ pages }: { pages: Load<PageSummary[]> }) {
  return (
    <DataView
      state={pages}
      isEmpty={ps => ps.length === 0}
      skeleton={<GridSkeleton />}
      empty={<EmptyState title="No pages yet">The pages are found from the scans after they are imported. If the book is still importing, they appear here when it is done.</EmptyState>}
    >
      {ps => (
        <ul aria-label="Pages in reading order" className="grid grid-cols-3 gap-4 sm:grid-cols-5 lg:grid-cols-7">
          {ps.map(p => (
            <li key={p.id}>
              <Link to={`/pages/${p.id}`} className="grid gap-1 rounded-control type-caption text-muted-foreground">
                <Thumbnail src={withBase(paths.pageImage(p.id, 'thumb'))} alt="" aspect="2/3" fit="contain" missing="Not drawn yet" className="w-full">
                  {needsLook(p) && <Status tone="warning" className="absolute top-1 left-1">Look</Status>}
                </Thumbnail>
                <span className="truncate text-foreground">{pageName(p)}</span>
                <span>{p.kind === 'text' ? format.count(p.words, 'word') : p.kind}{p.figures ? `, ${format.count(p.figures, 'picture')}` : ''}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </DataView>
  )
}

/** Every picture found in the book, each a link to its page. */
function Pictures({ book }: { book: Book }) {
  const figures = useLoad({ queryKey: keys.bookFigures(book.id), queryFn: () => api.bookFigures(book.id) })
  return (
    <DataView
      state={figures}
      isEmpty={fs => fs.length === 0}
      skeleton={<GridSkeleton />}
      empty={<EmptyState title="No pictures found">Pictures are found when the pages are read. To add one, open its page and draw it on the Pictures tab.</EmptyState>}
    >
      {fs => (
        <ul aria-label="Pictures in the book" className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-5">
          {fs.map(f => (
            <li key={f.id}>
              <Link to={`/pages/${f.page_id}?tab=pictures`} className="grid gap-1 rounded-control type-caption text-muted-foreground">
                <Thumbnail src={withBase(paths.figureImage(f.id))} alt={f.caption ?? `Picture on page ${f.page_position}`} aspect={f.w / f.h > 1.2 ? '4/3' : '3/4'} fit="contain" missing="Picture not cut yet" className="w-full" />
                <span className="truncate text-foreground">{f.caption ?? pageName({ position: f.page_position, label: f.page_label })}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </DataView>
  )
}

/** The exports, each with when it was made; the button above makes them. */
function Files({ book }: { book: Book }) {
  const made = fileNames.filter(n => book.files?.[n])
  if (!made.length) return <EmptyState title="No files yet">“Make the files” writes the Markdown, the text, a searchable PDF and a zip of everything from the pages as they are now.</EmptyState>
  return (
    <LinkCardList label="Files made from the book">
      {made.map(n => (
        <LinkCard key={n} href={withBase(paths.file(book.id, n))} title={`${fileWords[n].title} (${n})`} description={`${fileWords[n].description} Made ${format.dateTime(new Date(book.files![n]! * 1000))}.`} />
      ))}
    </LinkCardList>
  )
}
