import { describe, expect, it } from 'vitest'
import { expectOneFilledButton } from 'strata-react/testing'
import { pageError, pageNoScan, reshapeFails, saveFiguresFails, savePageFails } from '../../src/mocks/handlers'
import { openApp, screen, waitFor, within } from '../utils/render'
import { mock, server } from '../utils/server'

const page = (id: number) => mock.pages.find(p => p.id === id)!

describe('Page: the cut', () => {
  it('says what was unsure, and saves a new cut as hand work', async () => {
    const { user } = openApp('/pages/114')
    expect(await screen.findByText(/^Found and cut automatically\. .* 1\sline the reader was unsure of\.$/)).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Save cut' })
    expect(save).toBeDisabled()
    const width = screen.getByRole('textbox', { name: 'Width' })
    await user.clear(width)
    await user.type(width, '2500{Enter}')
    await waitFor(() => expect(save).toBeEnabled())
    expectOneFilledButton()
    await user.click(save)
    await waitFor(() => expect(page(114).hand).toBe(true))
    expect(page(114).crop.w).toBe(2500)
  })

  it('turns the scan a quarter and keeps the turn', async () => {
    const { user } = openApp('/pages/114')
    await user.click(await screen.findByRole('button', { name: 'Turn left' }))
    expect(screen.getByRole('img', { name: /turned 90°/ })).toHaveAttribute('src', '/api/scans/14/image?angle=90')
    await user.click(screen.getByRole('button', { name: 'Turn right' }))
    await user.click(screen.getByRole('button', { name: 'Turn right' }))
    await user.click(screen.getByRole('button', { name: 'Save cut' }))
    await waitFor(() => expect(page(114).angle).toBe(-90))
  })

  it('turns by a typed angle', async () => {
    const { user } = openApp('/pages/114')
    const turn = await screen.findByRole('textbox', { name: 'Turn' })
    await user.clear(turn)
    await user.type(turn, '1.5{Enter}')
    expect(await screen.findByRole('img', { name: /turned 1\.5°/ })).toHaveAttribute('src', '/api/scans/14/image?angle=1.5')
    await user.clear(turn)
    await user.tab()
    expect(screen.getByRole('img', { name: /turned 0°/ })).toBeInTheDocument()
  })

  it('splits a scan into a spread and joins it again', async () => {
    const { user, router } = openApp('/pages/114')
    await user.click(await screen.findByRole('button', { name: 'Split into two pages' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/pages/1140'))
    expect(mock.pages.filter(p => p.scan_id === 14).map(p => [p.side, p.crop.w])).toEqual([['left', 1337], ['right', 1337]])
    expect(await screen.findByText(/This scan is a spread/)).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: /^Cut of/ })).getByText('Left page')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Make one page' }))
    await waitFor(() => expect(mock.pages.filter(p => p.scan_id === 14).map(p => p.side)).toEqual(['single']))
    expect(page(1140).crop).toEqual({ x: 0, y: 0, w: 2674, h: 4084 })
  })

  it('saves both cuts of a spread', async () => {
    const { user, router } = openApp('/pages/114')
    await user.click(await screen.findByRole('button', { name: 'Split into two pages' }))
    await screen.findByText(/This scan is a spread/)
    await user.click(screen.getByRole('group', { name: /^Left page:/ }))
    const width = screen.getByRole('textbox', { name: 'Width' })
    await user.clear(width)
    await user.type(width, '1300{Enter}')
    await user.click(screen.getByRole('button', { name: 'Save cuts' }))
    await waitFor(() => expect(mock.pages.filter(p => p.scan_id === 14).map(p => p.crop.w)).toEqual([1300, 1337]))
    expect(router.state.location.pathname).toBe('/pages/1140')
  })

  it('moves through the book from the keys and the links', async () => {
    const { user, router } = openApp('/pages/114?tab=text')
    await screen.findByRole('heading', { level: 1, name: 'Page 14, 4' })
    await user.keyboard('n')
    await waitFor(() => expect(router.state.location.pathname).toBe('/pages/115'))
    expect(router.state.location.search).toBe('?tab=text')
    await user.keyboard('p')
    await waitFor(() => expect(router.state.location.pathname).toBe('/pages/114'))
    await user.click(screen.getByRole('link', { name: 'Previous page' }))
    expect(router.state.location.pathname).toBe('/pages/113')
    await user.click(await screen.findByRole('link', { name: 'Back to the book' }))
    expect(router.state.location.pathname).toBe('/books/1')
  })

  it('has no previous page at the start of the book', async () => {
    openApp('/pages/101')
    expect(await screen.findByText(/The page finder was unsure where the page is \(20%\)/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Previous page' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Next page' })).toHaveAttribute('href', '/pages/102')
  })

  it('says when a cut cannot be saved or a spread split, and when the scan is gone', async () => {
    server.use(reshapeFails, savePageFails)
    const { user } = openApp('/pages/114')
    await user.click(await screen.findByRole('button', { name: 'Split into two pages' }))
    expect(await screen.findByText('The server could not answer (503). The page was not changed.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Turn left' }))
    await user.click(screen.getByRole('button', { name: 'Save cut' }))
    await waitFor(() => expect(screen.getAllByText('The server could not answer (503). The page was not changed.')).toHaveLength(1))
    server.use(pageNoScan)
    openApp('/pages/114')
    expect(await screen.findByText('The scan is gone')).toBeInTheDocument()
  })

  it('has no next page at the end of the book', async () => {
    openApp('/pages/144')
    expect(await screen.findByRole('link', { name: 'Previous page' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Next page' })).not.toBeInTheDocument()
  })
})

describe('Page: the text', () => {
  it('lists the lines the reader was unsure of and keeps a typed correction', async () => {
    const { user } = openApp('/pages/114?tab=text')
    const unsure = await screen.findByRole('region', { name: 'Lines the reader was unsure of' })
    expect(within(unsure).getByText(/observes a writer in Har-$/)).toBeInTheDocument()
    const text = screen.getByRole('textbox', { name: 'Text' })
    await user.clear(text)
    await user.type(text, 'The Play of Punch and Judy.')
    await user.click(screen.getByRole('radio', { name: /Leave out/ }))
    await user.type(screen.getByRole('textbox', { name: 'Label' }), 'iv')
    await user.click(screen.getByRole('button', { name: 'Save page' }))
    await waitFor(() => expect(page(114)).toMatchObject({ text_edited: true, kind: 'skip', label: '4iv' }))
    expect(mock.details[114].text).toBe('The Play of Punch and Judy.')
    expect(await screen.findByText(/Typed by hand/)).toBeInTheDocument()
  })

  it('saves typed text for a page never read', async () => {
    const { user } = openApp('/pages/104?tab=text')
    const text = await screen.findByRole('textbox', { name: 'Text' })
    expect(text).toHaveValue('')
    await user.type(text, 'Blank, but for a stamp.')
    await user.click(screen.getByRole('button', { name: 'Save page' }))
    await waitFor(() => expect(page(104)).toMatchObject({ text_edited: true, label: null }))
  })

  it('says when saving fails', async () => {
    server.use(savePageFails)
    const { user } = openApp('/pages/114?tab=text')
    await user.type(await screen.findByRole('textbox', { name: 'Label' }), 'x')
    await user.click(screen.getByRole('button', { name: 'Save page' }))
    expect(await screen.findByText('The server could not answer (503). The page was not changed.')).toBeInTheDocument()
  })
})

describe('Page: the pictures', () => {
  it('removes a picture and saves the rest', async () => {
    const { user } = openApp('/pages/109?tab=pictures')
    expect(await screen.findByText(/^1\spicture on this page\./)).toBeInTheDocument()
    const remove = screen.getByRole('button', { name: 'Remove the chosen picture' })
    expect(remove).toBeDisabled()
    await user.click(screen.getByRole('group', { name: /^Picture 1:/ }))
    await user.click(remove)
    expect(screen.getByText(/^No pictures on this page\./)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save pictures' }))
    await waitFor(() => expect(page(109).figures).toBe(0))
  })
})

describe('Page: drawing a picture', () => {
  it('draws one by dragging on the page, and keeps the captions of the others', async () => {
    mock.details[114] = { ...mock.details[114], figures_list: [{ id: 7, page_id: 114, x: 100, y: 3000, w: 900, h: 700, caption: 'Punch and the Constable', hand: true }] }
    const { user } = openApp('/pages/114?tab=pictures')
    const editor = await screen.findByRole('group', { name: /^Pictures on/ })
    await user.pointer([
      { keys: '[MouseLeft>]', target: editor, coords: { clientX: 20, clientY: 20 } },
      { target: editor, coords: { clientX: 200, clientY: 300 } },
      { keys: '[/MouseLeft]', target: editor, coords: { clientX: 200, clientY: 300 } },
    ])
    expect(screen.getByText(/^2\spictures on this page\./)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save pictures' }))
    await waitFor(() => expect(page(114).figures).toBe(2))
    expect(mock.details[114].figures_list.map(f => f.caption)).toEqual(['Punch and the Constable', null])
  })
})

describe('Page: pictures that cannot be saved', () => {
  it('says so', async () => {
    server.use(saveFiguresFails)
    const { user } = openApp('/pages/109?tab=pictures')
    await user.click(await screen.findByRole('group', { name: /^Picture 1:/ }))
    await user.click(screen.getByRole('button', { name: 'Remove the chosen picture' }))
    await user.click(screen.getByRole('button', { name: 'Save pictures' }))
    expect(await screen.findByText('The server could not answer (503). The pictures were not changed.')).toBeInTheDocument()
  })
})

describe('Page, when the server cannot answer', () => {
  it('says so', async () => {
    server.use(pageError)
    openApp('/pages/114')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
