import { describe, expect, it } from 'vitest'
import { expectOneFilledButton } from 'strata-react/testing'
import { bookError, bookFailed, pagesLoading, runFails } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

describe('Book', () => {
  it('points at the pages that need a look and lists every page as a link', async () => {
    const { user, router } = openApp('/books/1')
    expect(await screen.findByText(/^3\spages need a look: the page finder was unsure where they are\. Page 1 is first\./)).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Pages in reading order' })
    expect(within(list).getAllByRole('link')).toHaveLength(44)
    expect(within(list).getAllByText('Look')).toHaveLength(3)
    expectOneFilledButton()
    await user.click(within(list).getByRole('link', { name: /Page 14, 4/ }))
    expect(router.state.location.pathname).toBe('/pages/114')
  })

  it('shows the work running, with its progress', async () => {
    openApp('/books/2')
    const job = await screen.findByRole('region', { name: /Work on Punch and Judy/ })
    expect(within(job).getByText('Reading page 97 of 206.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make the files' })).toBeDisabled()
  })

  it('says a stage is running before it knows how many pages', async () => {
    mock.books = mock.books.map(b => (b.id === 2 ? { ...b, stage: 'import', done: 0, total: 0 } : b))
    openApp('/books/2')
    const job = await screen.findByRole('region', { name: /Work on Punch and Judy/ })
    expect(within(job).getAllByText('Importing…')).not.toHaveLength(0)
  })

  it('says why work stopped', async () => {
    server.use(bookFailed)
    openApp('/books/2')
    expect(await screen.findAllByText('Stopped: strata-models is not running at http://127.0.0.1:8366.')).not.toHaveLength(0)
  })

  it('makes the files and lists them for download', async () => {
    mock.books = mock.books.map(b => (b.id === 1 ? { ...b, files: {} } : b))
    const { user } = openApp('/books/1?tab=files')
    expect(await screen.findByText('No files yet')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Make the files' }))
    const files = await screen.findByRole('list', { name: 'Files made from the book' })
    expect(within(files).getByRole('link', { name: /Searchable PDF \(book\.pdf\)/ })).toHaveAttribute('href', '/api/books/1/files/book.pdf')
    expect(within(files).getAllByRole('link')).toHaveLength(4)
  })

  it('reads again, and says when it could not start', async () => {
    const { user } = openApp('/books/1')
    await user.click(await screen.findByRole('button', { name: 'Read again' }))
    await waitFor(() => expect(mock.books.find(b => b.id === 1)!.stage).toBe('idle'))
    server.use(runFails)
    await user.click(await screen.findByRole('button', { name: 'Find pages again' }))
    expect(await screen.findByText('The server could not answer (503).')).toBeInTheDocument()
  })

  it('shows the pictures found, each a link to its page', async () => {
    openApp('/books/1?tab=pictures')
    const pictures = await screen.findByRole('list', { name: 'Pictures in the book' })
    expect(within(pictures).getAllByRole('link')[0]).toHaveAttribute('href', '/pages/101?tab=pictures')
    expect(within(pictures).getByRole('link', { name: /Punch and the Constable/ })).toHaveAttribute('href', '/pages/122?tab=pictures')
  })

  it('has empty states for a book with no pages or pictures', async () => {
    openApp('/books/2?tab=pictures')
    expect(await screen.findByText('No pictures found')).toBeInTheDocument()
    await screen.findByRole('tab', { name: 'Pages' }).then(t => t.click())
    expect(await screen.findByText('No pages yet')).toBeInTheDocument()
  })

  it('draws a skeleton while the pages load, and says the server could not answer', async () => {
    server.use(pagesLoading)
    openApp('/books/1')
    expect(await screen.findByRole('tab', { name: 'Pages' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Pages in reading order' })).not.toBeInTheDocument()
    server.use(bookError)
    openApp('/books/3')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
