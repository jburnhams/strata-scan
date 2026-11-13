import { describe, expect, it } from 'vitest'
import { logEmpty, logError, logLaterPageError, logLong } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

const list = () => screen.getByRole('list', { name: 'Greeting log, newest first' })
const shown = () => within(list()).getAllByRole('listitem').length

describe('Log', () => {
  it('shows every greeting and says when that is all', async () => {
    openApp('/log')
    expect(await screen.findByText('That is every greeting kept.')).toBeInTheDocument()
    expect(shown()).toBe(8)
    expect(within(list()).getAllByRole('listitem')[0]).toHaveTextContent('Welcome, Frances!')
  })

  it('reads a long log a page at a time, after the last greeting held', async () => {
    server.use(logLong)
    const { user } = openApp('/log')
    const more = await screen.findByRole('button', { name: 'Show older greetings' })
    expect(shown()).toBe(20)
    await user.click(more)
    await waitFor(() => expect(shown()).toBe(40))
    expect(within(list()).getAllByRole('listitem')[20]).toHaveTextContent('#55')        // the page after #56, the last one held
    for (let i = 0; i < 2; i++) await user.click(await screen.findByRole('button', { name: 'Show older greetings' }))
    expect(await screen.findByText('That is every greeting kept.')).toBeInTheDocument()
    expect(shown()).toBe(75)
  })

  it('keeps what it has when a later page fails, with Try again', async () => {
    server.use(logLaterPageError)
    const { user } = openApp('/log')
    await user.click(await screen.findByRole('button', { name: 'Show older greetings' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The server could not answer (503)')
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(shown()).toBe(20)
  })

  it('points to the Greetings screen when the log is empty', async () => {
    server.use(logEmpty)
    openApp('/log')
    expect(await screen.findByText('The log is empty')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Send a greeting' })).toHaveAttribute('href', '/')
  })

  it('says the server could not answer the first page', async () => {
    server.use(logError)
    openApp('/log')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
