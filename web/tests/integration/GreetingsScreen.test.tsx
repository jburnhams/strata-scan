import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { addFails, messagesEmpty, messagesError, removeFails } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const table = () => screen.getByRole('table', { name: 'Kept greetings, newest first' })
const greetings = () => within(table()).getAllByRole('row').slice(1).map(r => within(r).getAllByRole('cell')[1]?.textContent)

afterEach(() => { vi.useRealTimers() })

describe('Greetings', () => {
  it('answers its question in the finding and figures, and lists what is kept', async () => {
    openApp('/')
    expect(await screen.findByText(/^8 greetings to 8 people\. The latest, “Welcome, Frances!”/)).toBeInTheDocument()
    expect(screen.getByText('Most used greeting').nextSibling).toHaveTextContent('Hello')
    expect(screen.getByText(/^Used 4\stimes$/)).toBeInTheDocument()
    expect(greetings()).toHaveLength(8)
    expect(greetings()[0]).toBe('Welcome, Frances!')
  })

  it('sorts by a column and keeps the sort in the URL', async () => {
    const { user, router } = openApp('/')
    await screen.findByRole('table')
    await user.click(within(table()).getByRole('button', { name: /^To/ }))
    expect(router.state.location.search).toBe('?sort=name.asc')
    expect(greetings()[0]).toBe('Welcome, Ada!')
  })

  it('opens already sorted from a link', async () => {
    openApp('/?sort=sent.asc')
    await screen.findByRole('table')
    expect(greetings()[0]).toBe('Hello, Alan!')
  })

  it('sends a greeting through Sending… and Sent, and lists it first', async () => {
    const { user } = openApp('/')
    await screen.findByRole('table')
    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Hedy')
    await user.type(screen.getByRole('textbox', { name: 'Greeting' }), 'Good evening')
    await user.click(screen.getByRole('button', { name: 'Send greeting' }))
    expect(await screen.findByText('Sent', { selector: '[role=status]' })).toBeInTheDocument()        // AsyncButton announces the outcome politely
    await waitFor(() => expect(greetings()[0]).toBe('Good evening, Hedy!'))
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('')
    expect(mock.messages[0].message).toBe('Good evening, Hedy!')
  })

  it('greets the World with the default word when both fields are left empty', async () => {
    const { user } = openApp('/')
    expect(await screen.findByText(/Leave it empty for “Hello”, the default in Settings/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Send greeting' }))
    await waitFor(() => expect(greetings()[0]).toBe('Hello, World!'))
  })

  it('says under the field when a name is too long, and sends nothing', async () => {
    const { user } = openApp('/')
    await screen.findByRole('table')
    const name = screen.getByRole('textbox', { name: 'Name' })
    await user.click(name)
    await user.paste('x'.repeat(121))
    await user.click(screen.getByRole('button', { name: 'Send greeting' }))
    expect(name).toHaveAccessibleDescription(/Use at most 120 characters; this is 121\./)
    expect(name).toBeInvalid()
    expect(mock.messages).toHaveLength(8)
  })

  it('says what happened when sending fails, and offers to try again', async () => {
    server.use(addFails)
    const { user } = openApp('/')
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Send greeting' }))
    expect(await screen.findByText('The server could not answer (503). Nothing was kept.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('removes a greeting at once with Undo in reach, and Undo brings it back', async () => {
    const { user } = openApp('/')
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Remove Welcome, Frances!' }))
    expect(greetings()).not.toContain('Welcome, Frances!')
    expect(screen.getByText('Removed “Welcome, Frances!”.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(greetings()[0]).toBe('Welcome, Frances!')
    expect(mock.messages).toHaveLength(8)
  })

  it('commits a removal when the undo window closes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { user } = openApp('/', { user: { advanceTimers: vi.advanceTimersByTime } })
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Remove Welcome, Frances!' }))
    await vi.advanceTimersByTimeAsync(8000)
    await waitFor(() => expect(mock.messages.map(m => m.name)).not.toContain('Frances'))
    await waitFor(() => expect(screen.getByText(/^7 greetings/)).toBeInTheDocument())
  })

  it('brings a greeting back with Try again when the removal fails', async () => {
    server.use(removeFails)
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { user } = openApp('/', { user: { advanceTimers: vi.advanceTimersByTime } })
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Remove Welcome, Frances!' }))
    await vi.advanceTimersByTimeAsync(8000)
    expect(await screen.findByText(/“Welcome, Frances!” is back: removing it did not go through\./)).toBeInTheDocument()
    expect(greetings()[0]).toBe('Welcome, Frances!')
  })

  it('removes the chosen greetings together from the bulk bar', async () => {
    const { user } = openApp('/')
    await screen.findByRole('table')
    // One filled button at a time: Send greeting is filled until rows are chosen, then the bulk action is.
    // The filled buttons, by accessible name (AsyncButton keeps every phase's label in its text for its width).
    const named = ['Send greeting', 'Remove 2']
    const filled = () => screen.getAllByRole('button').filter(b => b.className.includes('bg-primary')).map(b => named.find(name => screen.queryByRole('button', { name }) === b) ?? b.textContent)
    expect(filled()).toEqual(['Send greeting'])
    await user.click(screen.getByRole('checkbox', { name: 'Select Welcome, Frances!' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select Hello, Ken!' }))
    expect(screen.getByText(/^2\sgreetings selected$/)).toBeInTheDocument()
    expect(filled()).toEqual(['Remove 2'])
    await user.click(screen.getByRole('button', { name: 'Remove 2' }))
    expect(greetings()).toHaveLength(6)
    expect(screen.getByText('Removed 2 greetings.')).toBeInTheDocument()
    // Undo, so nothing is left to commit when the screen unmounts (leaving the screen commits a pending
    // removal, which would then run against the next test's server).
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(greetings()).toHaveLength(8)
    expect(filled()).toEqual(['Send greeting'])
  })

  it('keeps a greeting gone when a bulk removal fails part way, and brings back only the rest', async () => {
    server.use(http.delete('*/api/messages/7', () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' })))
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { user } = openApp('/', { user: { advanceTimers: vi.advanceTimersByTime } })
    await screen.findByRole('table')
    await user.click(screen.getByRole('checkbox', { name: 'Select Welcome, Frances!' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select Hello, Ken!' }))
    await user.click(screen.getByRole('button', { name: 'Remove 2' }))
    await vi.advanceTimersByTimeAsync(8000)
    expect(await screen.findByText(/did not go through/)).toBeInTheDocument()
    await waitFor(() => expect(greetings()[0]).toBe('Hello, Ken!'))
    expect(greetings()).not.toContain('Welcome, Frances!')
    expect(mock.messages.map(m => m.name)).not.toContain('Frances')

    // The server recovers; Try again sends the batch again, and the greeting already gone (404) counts as done.
    server.resetHandlers()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(mock.messages.map(m => m.name)).not.toContain('Ken'))
    await waitFor(() => expect(greetings()[0]).toBe('Hello, Barbara!'))
    expect(screen.queryByText(/did not go through/)).toBeNull()
  })

  it('teaches the next step when nothing is kept', async () => {
    server.use(messagesEmpty)
    openApp('/')
    expect(await screen.findByText('Nothing kept yet')).toBeInTheDocument()
    expect(screen.getByText('No greetings have gone out yet. Send the first one below.')).toBeInTheDocument()
  })

  it('says the server could not answer, with Try again', async () => {
    server.use(messagesError)
    openApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
    expect(within(screen.getByRole('alert')).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
