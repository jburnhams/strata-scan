// The one question: "Which books are here, and how far along is each?" The finding answers with
// what is running or what needs a look; then the books (a table: the title links to the book, the
// state is a word, never colour alone), then adding one, which is the only write on the screen.
//
// A book arrives two ways: a PDF dropped or picked in the browser (uploaded, then imported), or a
// path on the server's own disk (a PDF or a folder of photographs: no upload, which matters for a
// 400 MB scan). Either way the server starts all four stages at once, so the new row says
// "Importing" and the table polls while any book is busy.
import { useQueryClient } from '@tanstack/react-query'
import { FileUp } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  AsyncButton,
  DataTable,
  DataView,
  EmptyState,
  Field,
  FileButton,
  FileDropZone,
  Input,
  PageHeader,
  Status,
  TableSkeleton,
  format,
  useAsyncAction,
  useLoad,
  type Column,
} from 'strata-react'
import { api, describeBook, keys, stageWord, type Book } from '../api'

/** The page's finding: what is running, what stopped, what needs a look, or how to start. */
export function describeShelf(books: Book[]): string {
  if (!books.length) return 'No books yet. Add a scanned book below: a PDF, or a folder of photographs on the server.'
  const busy = books.filter(b => b.stage !== 'idle')
  const failed = books.filter(b => b.error)
  const check = books.reduce((n, b) => n + b.to_check, 0)
  const parts = [`${format.count(books.length, 'book')}, ${format.count(books.reduce((n, b) => n + b.pages, 0), 'page')}.`]
  if (busy.length) parts.push(`${busy[0].title} is ${stageWord[busy[0].stage].toLowerCase()}${busy.length > 1 ? `, and ${format.count(busy.length - 1, 'other')}` : ''}.`)
  if (failed.length) parts.push(`${format.count(failed.length, 'book')} stopped with an error.`)
  if (check) parts.push(`${format.count(check, 'page')} the page finder was unsure of need a look.`)
  return parts.join(' ')
}

/** A book's state as a word in its tone: busy, stopped, needs a look, or ready. */
export function BookState({ book }: { book: Book }) {
  if (book.error) return <Status tone="danger">Stopped</Status>
  if (book.stage !== 'idle') return <Status tone="info">{stageWord[book.stage]}</Status>
  if (book.to_check) return <Status tone="warning">Needs a look</Status>
  return <Status tone="success">Ready</Status>
}

const columns: Column<Book>[] = [
  { key: 'title', header: 'Book', cell: b => <Link to={`/books/${b.id}`} className="font-medium text-foreground underline-offset-4 hover:underline">{b.title}</Link>, value: b => b.title, truncate: true },
  { key: 'state', header: 'State', cell: b => <BookState book={b} />, value: b => (b.error ? 0 : b.stage !== 'idle' ? 1 : b.to_check ? 2 : 3) },
  { key: 'pages', header: 'Pages', numeric: true, value: b => b.pages, cell: b => format.integer(b.pages) },
  { key: 'read', header: 'Read', numeric: true, value: b => b.read, cell: b => format.integer(b.read) },
  { key: 'pictures', header: 'Pictures', numeric: true, value: b => b.figures, cell: b => format.integer(b.figures) },
  { key: 'progress', header: 'Where it is', cell: b => <span className="text-muted-foreground">{describeBook(b)}</span>, sort: false },
]

export function BooksScreen() {
  const load = useLoad({
    queryKey: keys.books,
    queryFn: api.books,
    // read again every 2 s while any book is being worked on, so its row moves without a reload
    refetchInterval: q => (q.state.data?.some(b => b.stage !== 'idle') ? 2000 : false),
  })

  return (
    <>
      <PageHeader title="Books" scope="Scanned books on this server" finding={load.status === 'ready' ? { text: describeShelf(load.data) } : undefined} />
      <section aria-labelledby="shelf" className="grid gap-3">
        <h2 id="shelf" className="sr-only">Every book</h2>
        <DataView
          state={load}
          isEmpty={books => books.length === 0}
          skeleton={<TableSkeleton rows={3} columns={6} />}
          empty={<EmptyState title="No books yet">Drop a scanned book’s PDF below, or give the path of one on the server. strata-scan finds the pages, reads them and cuts out the pictures.</EmptyState>}
        >
          {books => <DataTable caption="Books, most recently changed first" columns={columns} rows={books} rowKey={b => String(b.id)} sortParam="sort" />}
        </DataView>
      </section>
      <AddBook />
    </>
  )
}

/** The PDF among files dropped or picked, or why there is none. */
export function pickPdf(files: readonly File[]): File | string {
  const pdf = files.find(f => f.name.toLowerCase().endsWith('.pdf'))
  return pdf ?? `${files[0]?.name ?? 'That'} is not a PDF. For photographs, put them in a folder on the server and give its path below.`
}

/** Add a book: upload a PDF, or name one (or a folder of pictures) on the server. */
export function AddBook() {
  const queryClient = useQueryClient()
  const [source, setSource] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.books })

  const upload = useAsyncAction(async (file: File) => {
    const b = await api.upload(file)
    setSent(`${b.title} is uploaded and importing.`)
    await refresh()
  })
  const fromPath = useAsyncAction(
    async (path: string) => {
      const b = await api.addBook(path)
      setSource('')
      setSent(`${b.title} is importing.`)
      await refresh()
    },
    { validate: (path: string) => ({ source: path.trim() ? undefined : 'Enter the full path of a PDF or a folder of pictures on the server.' }) },
  )

  const onFiles = (files: File[]) => {
    const pick = pickPdf(files)
    if (typeof pick === 'string') setSent(pick)
    else void upload.run(pick)
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void fromPath.run(source.trim())
  }

  return (
    <section aria-labelledby="add" className="grid max-w-3xl gap-4">
      <h2 id="add" className="type-heading">Add a book</h2>
      <FileDropZone onFiles={onFiles} acceptLabel="a PDF of a scanned book" title="Drop a scanned book’s PDF here" disabled={upload.phase === 'pending'}>
        <FileButton accept={['.pdf', 'application/pdf']} onFiles={onFiles} icon={FileUp}>{upload.phase === 'pending' ? 'Uploading…' : 'Choose a PDF'}</FileButton>
      </FileDropZone>
      {upload.phase === 'error' && <p className="type-body-sm text-danger">{upload.error} The book was not added.</p>}
      <form onSubmit={onSubmit} noValidate>
        <Field
          label="Or a PDF or folder on the server"
          hint="A full path on the computer strata-scan runs on. A folder’s pictures are taken in name order."
          error={fromPath.fieldErrors.source ?? (fromPath.phase === 'error' ? fromPath.error : undefined)}
          action={<AsyncButton type="submit" variant="default" phase={fromPath.phase} error={fromPath.error} labels={{ idle: 'Add book', pending: 'Adding…', done: 'Added' }} />}
        >
          <Input value={source} onChange={e => setSource(e.target.value)} placeholder="/home/ada/books/punch-and-judy.pdf" autoComplete="off" spellCheck={false} />
        </Field>
      </form>
      {sent && <p role="status" className="type-body-sm text-muted-foreground">{sent}</p>}
    </section>
  )
}
