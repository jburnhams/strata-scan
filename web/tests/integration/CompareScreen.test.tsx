import { describe, expect, it } from 'vitest'
import { compareAllGood, compareError } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { server } from '../utils/server'

describe('Compare', () => {
  it('opens on the pages to look at, the first one compared side by side', async () => {
    openApp('/books/1/compare')
    expect(await screen.findByText(/^3\spages of 40\sfinished pages to look at: Page 7, a line is set 1\.6 times its block's size\. 4\spages not set yet\./)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Compare Punch and Judy, with instructions how to manage the little wooden actors' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'To look at' })).toBeChecked()
    expect(screen.getByRole('img', { name: 'Page 7 as scanned' })).toHaveAttribute('src', '/api/pages/107/image?size=preview')
    expect(screen.getByRole('img', { name: 'Page 7 as finished' })).toHaveAttribute('src', '/api/pages/107/finished')
    expect(screen.getByRole('status', { name: '' }).textContent).toBe('Page 7: 1 of 3')
    const table = screen.getByRole('grid', { name: 'Pages to look at' })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
  })

  it('steps through the pages to look at, and keeps the page in the URL', async () => {
    const { user, router } = openApp('/books/1/compare')
    await screen.findByRole('img', { name: 'Page 7 as scanned' })
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByRole('img', { name: 'Page 16, 6 as scanned' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('?page=116')
    expect(within(screen.getByRole('list', { name: 'What was found' })).getByText(/^The ink agrees 38%\./)).toBeInTheDocument()
    await user.keyboard('n')
    expect(await screen.findByRole('img', { name: 'Page 22, 12 as scanned' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    await user.keyboard('p')
    expect(await screen.findByRole('img', { name: 'Page 16, 6 as scanned' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    expect(await screen.findByRole('img', { name: 'Page 7 as scanned' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await user.click(within(screen.getByRole('grid', { name: 'Pages to look at' })).getByRole('button', { name: 'Compare Page 7' }))
    expect(await screen.findByRole('img', { name: 'Page 7 as scanned' })).toBeInTheDocument()
  })

  it('shows every page, as spreads, in any view', async () => {
    const { user, router } = openApp('/books/1/compare?show=all&layout=spread&page=116')
    expect(await screen.findByRole('img', { name: 'Page 16, 6 and Page 17, 7 as scanned' })).toHaveAttribute('src', '/api/books/1/spread?pages=116,117&side=scan')
    expect(screen.getByRole('img', { name: 'Page 16, 6 and Page 17, 7 as finished' })).toHaveAttribute('src', '/api/books/1/spread?pages=116,117&side=finished')
    expect(screen.getByRole('grid', { name: 'Every page, scan against finished' })).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Above and below' }))
    expect(router.state.location.search).toContain('mode=stack')
    await user.click(screen.getByRole('radio', { name: 'Ink match' }))
    expect(screen.getByRole('group', { name: 'Ink of Scan matched against Finished' })).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Page' }))
    await waitFor(() => expect(router.state.location.search).not.toContain('layout'))
    expect(await screen.findByRole('img', { name: 'Page 16, 6 as scanned' })).toBeInTheDocument()
  })

  it('says a page not set yet has nothing to compare', async () => {
    openApp('/books/1/compare?show=all&page=141')
    expect(await screen.findByText('Not set in type yet.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Page 41 as finished' })).toHaveAttribute('src', '/api/pages/141/finished')
  })

  it('says when every finished page matches, and lists them all', async () => {
    server.use(compareAllGood)
    openApp('/books/1/compare')
    expect(await screen.findByText('Every finished page matches its scan.')).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'To look at' })).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Page 1 as scanned' })).toBeInTheDocument()
  })

  it('says there is nothing to look at when asked for those pages and every page matches', async () => {
    server.use(compareAllGood)
    openApp('/books/1/compare?show=look')
    expect(await screen.findByText('No page to look at')).toBeInTheDocument()
    expect(screen.queryByRole('grid')).not.toBeInTheDocument()
  })

  it('says when the comparison could not be read', async () => {
    server.use(compareError)
    openApp('/books/1/compare')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('is reached from the book', async () => {
    const { user, router } = openApp('/books/1')
    await user.click(await screen.findByRole('link', { name: 'Compare with the scans' }))
    expect(router.state.location.pathname).toBe('/books/1/compare')
  })
})
