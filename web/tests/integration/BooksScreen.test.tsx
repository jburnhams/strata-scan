import { describe, expect, it } from 'vitest'
import { expectOneFilledButton } from 'strata-react/testing'
import { ward } from '../../src/mocks/fixtures'
import { booksEmpty, booksError, uploadFails } from '../../src/mocks/handlers'
import { fireEvent } from '@testing-library/react'
import { openApp, screen, within } from '../utils/render'
import { mock, server } from '../utils/server'

describe('Books', () => {
  it('lists the books with where each one is, and opens one', async () => {
    const { user, router } = openApp('/')
    expect(await screen.findByText(/^2\sbooks, 250\spages\. Punch and Judy, with illustrations by George Cruikshank is reading\./)).toBeInTheDocument()
    const table = screen.getByRole('grid', { name: /Books/ })
    expect(within(table).getByText('Reading')).toBeInTheDocument()
    expect(within(table).getByText('Needs a look')).toBeInTheDocument()
    expect(within(table).getByText('Reading page 97 of 206.')).toBeInTheDocument()
    expectOneFilledButton()
    await user.click(within(table).getByRole('link', { name: ward.title }))
    expect(router.state.location.pathname).toBe('/books/1')
  })

  it('marks a finished book Ready and a stopped one Stopped', async () => {
    mock.books = mock.books.map(b => (b.id === 1 ? { ...b, to_check: 0 } : { ...b, stage: 'idle', error: 'strata-models is not running' }))
    openApp('/')
    const table = await screen.findByRole('grid', { name: /Books/ })
    expect(within(table).getByText('Ready')).toBeInTheDocument()
    expect(within(table).getByText('Stopped')).toBeInTheDocument()
    expect(screen.getByText(/1\sbook stopped with an error\.$/)).toBeInTheDocument()
  })

  it('teaches how to start when there are none', async () => {
    server.use(booksEmpty)
    openApp('/')
    expect(await screen.findByText('No books yet')).toBeInTheDocument()
    expect(screen.getByText(/^No books yet\. Add a scanned book below/)).toBeInTheDocument()
  })

  it('adds a book from a path on the server, and says what is wrong with an empty one', async () => {
    const { user } = openApp('/')
    const path = await screen.findByRole('textbox', { name: 'Or a PDF or folder on the server' })
    await user.click(screen.getByRole('button', { name: 'Add book' }))
    expect(path).toHaveAccessibleDescription(/Enter the full path of a PDF or a folder of pictures/)
    expect(mock.books).toHaveLength(2)
    await user.type(path, '/home/ada/books/judy.pdf')
    await user.click(screen.getByRole('button', { name: 'Add book' }))
    expect(await screen.findByText('judy is importing.')).toBeInTheDocument()
    expect(mock.books[0]).toMatchObject({ title: 'judy', source: '/home/ada/books/judy.pdf' })
    expect(path).toHaveValue('')
  })

  it('says the server’s reason when it refuses a path', async () => {
    const { user } = openApp('/')
    await user.type(await screen.findByRole('textbox', { name: 'Or a PDF or folder on the server' }), '/home/ada/notes.txt')
    await user.click(screen.getByRole('button', { name: 'Add book' }))
    expect(await screen.findByRole('textbox', { name: 'Or a PDF or folder on the server' })).toHaveAccessibleDescription(/notes\.txt is not a PDF or a folder of pictures/)
  })

  it('uploads a PDF from the picker', async () => {
    const { user } = openApp('/')
    const input = await screen.findByText('Choose a PDF').then(() => document.querySelector('input[type=file]') as HTMLInputElement)
    await user.upload(input, new File(['%PDF-1.4'], 'Punch.pdf', { type: 'application/pdf' }))
    expect(await screen.findByText('Uploaded book is uploaded and importing.')).toBeInTheDocument()
    expect(mock.books).toHaveLength(3)

  })

  it('turns away a dropped file that is not a PDF', async () => {
    openApp('/')
    const zone = (await screen.findByText('Drop a scanned book’s PDF here')).closest('[data-rac], [class*="border"]') as HTMLElement
    const file = new File(['x'], 'cover.jpg', { type: 'image/jpeg' })
    const dataTransfer = { files: [file], types: ['Files'], items: [{ kind: 'file', type: 'image/jpeg', getAsFile: () => file }], dropEffect: 'copy', effectAllowed: 'all', getData: () => '', setData: () => {} }
    fireEvent.dragEnter(zone, { dataTransfer })
    fireEvent.dragOver(zone, { dataTransfer })
    fireEvent.drop(zone, { dataTransfer })
    expect(await screen.findByText(/^cover\.jpg is not a PDF\. For photographs/)).toBeInTheDocument()
  })

  it('says when an upload fails', async () => {
    server.use(uploadFails)
    const { user } = openApp('/')
    const input = await screen.findByText('Choose a PDF').then(() => document.querySelector('input[type=file]') as HTMLInputElement)
    await user.upload(input, new File(['%PDF-1.4'], 'Punch.pdf', { type: 'application/pdf' }))
    expect(await screen.findByText('The server could not answer (503). The book was not added.')).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(booksError)
    openApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
