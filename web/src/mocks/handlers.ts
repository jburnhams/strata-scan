// The mock server: MSW handlers for every endpoint the app calls, answering like a healthy server.
// One set serves the jsdom tests (Node, tests/utils/server.ts), Storybook (a service worker,
// .storybook/preview.tsx) and the visual suite (Node, strata-visual.config.ts), so the app's real
// fetch, query and DataView code runs in all three and nothing is a module mock.
//
// The named handlers below each replace one route to put a test, story or screenshot into another
// state: `server.use(booksError)` in a test, `msw.use(booksError)` in a story's beforeEach,
// `states: { error: [booksError] }` in the visual config.
import { delay, http, HttpResponse } from 'msw'
import { paths, type Book, type Figure, type PageDetail, type PageSummary, type Settings, type Stage } from '../api'
import { collier, defaultSettings, initialBooks, page14, page9, pageDetail, systemNearlyFull as nearlyFull, systemNoModels as noModels, systemStatus, ward, wardFigures, wardPages } from './fixtures'
import { coverPage, picturePage, textPage } from './images'

/** What the mock server holds. Writes change it, so a test can add a book and see it listed. */
export const mock = {
  settings: { ...defaultSettings } as Settings,
  books: [...initialBooks] as Book[],
  pages: [...wardPages] as PageSummary[],
  details: { 109: page9, 114: page14 } as Record<number, PageDetail>,
}

/** Back to the healthy state: call between tests and stories. */
export function resetMock() {
  mock.settings = { ...defaultSettings }
  mock.books = [...initialBooks]
  mock.pages = [...wardPages]
  mock.details = { 109: page9, 114: page14 }
}

// Matched as paths, so they answer whatever origin and base the app runs under.
const at = (path: string) => `*${path}`

const refused = (detail: string, status = 400) => HttpResponse.json({ detail }, { status })
const down = () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' })

function jpeg(b64: string) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
  return new HttpResponse(bytes, { headers: { 'Content-Type': 'image/jpeg' } })
}

/** The picture for a page: a cover, an engraving or a page of type, by its kind. */
function pagePicture(id: number) {
  const kind = mock.pages.find(p => p.id === id)?.kind
  return jpeg(kind === 'cover' ? coverPage : kind === 'picture' ? picturePage : textPage)
}

const findBook = (id: number) => mock.books.find(b => b.id === id)
const detail = (id: number): PageDetail | undefined => {
  const p = mock.pages.find(x => x.id === id)
  if (!p) return undefined
  const siblings = mock.pages.filter(x => x.scan_id === p.scan_id).map(({ id, side, angle, crop }) => ({ id, side, angle, crop }))
  const at = mock.pages.indexOf(p)
  return {
    ...(mock.details[id] ? { ...mock.details[id], ...p } : pageDetail(p)),
    siblings,
    prev_id: mock.pages[at - 1]?.id ?? null,
    next_id: mock.pages[at + 1]?.id ?? null,
  }
}

export const handlers = [
  http.get(at(paths.health), () => HttpResponse.json({ ok: true, version: systemStatus.version })),
  http.get(at(paths.system), () => HttpResponse.json({ ...systemStatus, data_dir: mock.settings.data_dir })),
  http.get(at(paths.settings), () => HttpResponse.json(mock.settings)),
  http.put(at(paths.settings), async ({ request }) => {
    const body = (await request.json()) as Partial<Settings>
    if (body.data_dir !== undefined && !body.data_dir.startsWith('/') && !body.data_dir.startsWith('~')) return refused('data_dir: must be an absolute path')
    mock.settings = { ...mock.settings, ...body }
    return HttpResponse.json(mock.settings)
  }),

  http.get(at(paths.books), () => HttpResponse.json(mock.books)),
  http.post(at(paths.books), async ({ request }) => {
    const b = (await request.json()) as { source: string; title?: string }
    if (!b.source.endsWith('.pdf') && !b.source.endsWith('/')) return refused(`${b.source} is not a PDF or a folder of pictures`)
    const book = newBook(b.title || b.source.split('/').filter(Boolean).pop()!.replace(/\.pdf$/, ''), b.source)
    return HttpResponse.json(book, { status: 201 })
  }),
  // The body is not read: in the jsdom tests a File from jsdom cannot be streamed through Node's fetch
  // ("Premature close"), and the screen has already refused anything but a PDF. The book is named as
  // an upload without a title is: after its file.
  http.post(at(paths.upload), () => HttpResponse.json(newBook('Uploaded book', '/uploads/book.pdf'), { status: 201 })),
  http.get(at('/api/books/:id'), ({ params }) => {
    const b = findBook(Number(params.id))
    return b ? HttpResponse.json(b) : refused(`there is no book ${params.id}`, 404)
  }),
  http.delete(at('/api/books/:id'), ({ params }) => {
    const b = findBook(Number(params.id))
    if (!b) return refused(`there is no book ${params.id}`, 404)
    if (b.stage !== 'idle') return refused(`${b.title} is busy (${b.stage}); try again when it is done`, 409)
    mock.books = mock.books.filter(x => x !== b)
    return HttpResponse.json({ removed: b.id })
  }),
  http.post(at('/api/books/:id/run'), async ({ params, request }) => {
    const b = findBook(Number(params.id))
    if (!b) return refused(`there is no book ${params.id}`, 404)
    const { stages } = (await request.json()) as { stages: Stage[] }
    // The mock does the work at once: the book is idle again, its files made, when the screen next asks.
    const done = { ...b, stage: 'idle' as Stage, done: b.pages, total: b.pages, files: stages.includes('export') ? ward.files : b.files }
    mock.books = mock.books.map(x => (x === b ? done : x))
    return HttpResponse.json({ ...b, stage: stages[0] }, { status: 202 })
  }),
  http.get(at('/api/books/:id/pages'), ({ params }) => HttpResponse.json(Number(params.id) === ward.id ? mock.pages : [])),
  http.get(at('/api/books/:id/figures'), ({ params }) => HttpResponse.json(Number(params.id) === ward.id ? wardFigures : [])),

  http.get(at('/api/pages/:id'), ({ params }) => {
    const d = detail(Number(params.id))
    return d ? HttpResponse.json(d) : refused(`there is no page ${params.id}`, 404)
  }),
  http.patch(at('/api/pages/:id'), async ({ params, request }) => {
    const id = Number(params.id)
    const d = detail(id)
    if (!d) return refused(`there is no page ${params.id}`, 404)
    const ch = (await request.json()) as Partial<PageDetail>
    const reshaped = ch.angle !== undefined || ch.crop !== undefined
    const next: PageDetail = { ...d, ...ch, hand: d.hand || reshaped, text_edited: d.text_edited || ch.text !== undefined, confidence: reshaped ? 1 : d.confidence }
    mock.details = { ...mock.details, [id]: next }
    mock.pages = mock.pages.map(p => (p.id === id ? { ...p, ...ch, hand: next.hand, text_edited: next.text_edited, confidence: next.confidence } : p))
    return HttpResponse.json(next)
  }),
  http.put(at('/api/scans/:id/pages'), async ({ params, request }) => {
    const scanId = Number(params.id)
    const { pages } = (await request.json()) as { pages: Pick<PageSummary, 'side' | 'angle' | 'crop'>[] }
    if (pages.length === 2 && [...pages.map(p => p.side)].sort().join() !== 'left,right') return refused("a spread's two pages are its left and right", 422)
    const old = mock.pages.filter(p => p.scan_id === scanId)
    if (!old.length) return refused(`there is no scan ${scanId}`, 404)
    const first = old[0]
    const made: PageSummary[] = pages.map((x, i) => ({ ...first, id: 1000 + scanId * 10 + i, side: pages.length === 2 ? x.side : 'single', angle: x.angle, crop: x.crop, hand: true, confidence: 1, read: false, words: 0, figures: 0 }))
    const at = mock.pages.indexOf(first)
    mock.pages = [...mock.pages.slice(0, at), ...made, ...mock.pages.slice(at + old.length)].map((p, i) => ({ ...p, position: i + 1 }))
    return HttpResponse.json(mock.pages.filter(p => p.scan_id === scanId))
  }),
  http.put(at('/api/pages/:id/figures'), async ({ params, request }) => {
    const id = Number(params.id)
    const d = detail(id)
    if (!d) return refused(`there is no page ${params.id}`, 404)
    const { figures } = (await request.json()) as { figures: Omit<Figure, 'id' | 'page_id' | 'hand'>[] }
    const list: Figure[] = figures.map((f, i) => ({ ...f, caption: f.caption ?? null, id: id * 100 + i, page_id: id, hand: true }))
    mock.details = { ...mock.details, [id]: { ...d, figures_list: list, figures: list.length } }
    mock.pages = mock.pages.map(p => (p.id === id ? { ...p, figures: list.length } : p))
    return HttpResponse.json(list)
  }),

  http.get(at('/api/pages/:id/image'), ({ params }) => pagePicture(Number(params.id))),
  http.get(at('/api/scans/:id/image'), ({ params }) => pagePicture(mock.pages.find(p => p.scan_id === Number(params.id))?.id ?? 0)),
  http.get(at('/api/figures/:id/image'), () => jpeg(picturePage)),
]

function newBook(title: string, source: string): Book {
  const id = Math.max(0, ...mock.books.map(b => b.id)) + 1
  const book: Book = { ...collier, id, title, source, author: null, stage: 'import', done: 0, total: 0, scans: 0, pages: 0, read: 0, figures: 0, to_check: 0, files: {}, created_at: '2026-11-13T23:10:00', updated_at: '2026-11-13T23:10:00' }
  mock.books = [book, ...mock.books]
  return book
}

// States. A request that never answers is "loading"; 503 is a server that is down. The app's query
// client retries once, so an error shows after about a second (tests turn retries off).

export const booksLoading = http.get(at(paths.books), () => delay('infinite'))
export const booksEmpty = http.get(at(paths.books), () => HttpResponse.json([]))
export const booksError = http.get(at(paths.books), down)
export const uploadFails = http.post(at(paths.upload), down)

export const bookLoading = http.get(at('/api/books/:id'), () => delay('infinite'))
export const bookError = http.get(at('/api/books/:id'), down)
/** The 1828 book stopped part way: strata-models went away. */
export const bookFailed = http.get(at('/api/books/:id'), () => HttpResponse.json({ ...collier, stage: 'idle', error: 'strata-models is not running at http://127.0.0.1:8366' }))
export const pagesLoading = http.get(at('/api/books/:id/pages'), () => delay('infinite'))
export const runFails = http.post(at('/api/books/:id/run'), down)

export const pageLoading = http.get(at('/api/pages/:id'), () => delay('infinite'))
export const pageError = http.get(at('/api/pages/:id'), down)
export const savePageFails = http.patch(at('/api/pages/:id'), down)
export const reshapeFails = http.put(at('/api/scans/:id/pages'), down)
export const saveFiguresFails = http.put(at('/api/pages/:id/figures'), down)
/** Page 14's scan as a spread split by hand: this page is its left half. */
export const pageSpread = http.get(at('/api/pages/:id'), () =>
  HttpResponse.json({
    ...page14,
    side: 'left',
    hand: true,
    confidence: 1,
    crop: { x: 0, y: 0, w: 1337, h: 4084 },
    siblings: [
      { id: 114, side: 'left', angle: 0, crop: { x: 0, y: 0, w: 1337, h: 4084 } },
      { id: 1141, side: 'right', angle: 0, crop: { x: 1337, y: 0, w: 1337, h: 4084 } },
    ],
  }),
)
/** A page whose scan is missing from the data folder. */
export const pageNoScan = http.get(at('/api/pages/:id'), () => HttpResponse.json({ ...page14, scan: null }))

export const systemLoading = http.get(at(paths.system), () => delay('infinite'))
export const systemError = http.get(at(paths.system), down)
export const systemNearlyFull = http.get(at(paths.system), () => HttpResponse.json(nearlyFull))
export const systemNoModels = http.get(at(paths.system), () => HttpResponse.json(noModels))

export const settingsLoading = http.get(at(paths.settings), () => delay('infinite'))
export const settingsError = http.get(at(paths.settings), down)
export const saveSettingsFails = http.put(at(paths.settings), down)
