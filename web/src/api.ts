// The FastAPI server's endpoints (src/stratascan/server/app.py, listed in its docstring) and their
// shapes. Reads go through strata-react's useLoad / useJob with fetchJson, which throws HttpError on
// a non-2xx answer (with the server's reason); the screens never call fetch themselves. Every URL is
// built here, through withBase, so the app works at the server's root and behind a reverse proxy.
import { fetchJson } from 'strata-react'

/** Settings are stored and answered as text (strata_python.settings). */
export interface Settings { data_dir: string; max_dpi: string; workers: string }

/** The stage a book is in: `idle` when nothing runs. */
export type Stage = 'idle' | 'import' | 'detect' | 'read' | 'export'

/** `GET /api/books` and `GET /api/books/{id}` (which adds `files`: name → modified, seconds since the epoch). */
export interface Book {
  id: number
  title: string
  author: string | null
  source: string
  lang: string
  stage: Stage
  done: number
  total: number
  error: string | null
  created_at: string | null
  updated_at: string | null
  scans: number
  pages: number
  read: number
  figures: number
  /** Pages the page finder was unsure of and nobody has looked at. */
  to_check: number
  files?: Partial<Record<FileName, number>>
}

export type FileName = 'book.md' | 'book.txt' | 'book.pdf' | 'book.zip'
export const fileNames: readonly FileName[] = ['book.md', 'book.txt', 'book.pdf', 'book.zip']

export interface Crop { x: number; y: number; w: number; h: number }
export type Side = 'single' | 'left' | 'right'
export type Kind = 'text' | 'picture' | 'cover' | 'blank' | 'skip'

/** A page as listed (`GET /api/books/{id}/pages`). */
export interface PageSummary {
  id: number
  book_id: number
  scan_id: number
  position: number
  side: Side
  /** Degrees counter-clockwise the scan is turned before the crop. */
  angle: number
  /** In the turned scan's pixels. */
  crop: Crop
  /** How sure the page finder was, 0 to 1. */
  confidence: number
  hand: boolean
  kind: Kind
  label: string | null
  read: boolean
  ocr_conf: number | null
  words: number
  text_edited: boolean
  figures: number
  error: string | null
}

export interface Line { text: string; box: [number, number, number, number]; conf: number }
export interface Figure { id: number; page_id: number; x: number; y: number; w: number; h: number; caption: string | null; hand: boolean }
/** A picture as the book lists it (`GET /api/books/{id}/figures`): with its page's position and label. */
export interface BookFigure extends Figure { page_position: number; page_label: string | null }

/** `GET /api/pages/{id}`: the page with its scan, its text and lines, its pictures and its neighbours. */
export interface PageDetail extends PageSummary {
  scan: { id: number; position: number; width: number; height: number; dpi: number | null } | null
  /** The drawn page's size in pixels: the units of `lines` and `figures_list`. */
  size: { w: number; h: number }
  text: string | null
  lines: Line[]
  ocr_model: string | null
  figures_list: Figure[]
  siblings: { id: number; side: Side; angle: number; crop: Crop }[]
  prev_id: number | null
  next_id: number | null
}

/** `GET /api/system`. Sizes are bytes. */
export interface SystemStatus {
  version: string
  python: string
  platform: string
  data_dir: string
  data_bytes: number
  disk: { total: number; used: number; free: number }
  models: { url: string; available: boolean; ocr_model: string | null }
}

// Where the app is served from: '' at the server's own root, '/prefix' behind a reverse proxy. Read
// from the page's base URL: the server gives every page a relative <base> back to its root
// (app.py with_base), and assets are relative (vite.config.ts base './'), so one build works in
// both places. React Router takes the same value as its basename (main.tsx).
export const BASE = typeof document === 'undefined' ? '' : new URL('.', document.baseURI).pathname.replace(/\/$/, '')     // no page (the unit tests run in node): the root
export const withBase = (u: string) => (u.startsWith('/') ? BASE + u : u)

/** The endpoints, as paths under the server's root. Mock handlers (src/mocks/handlers.ts) match the same paths. */
export const paths = {
  health: '/api/health',
  system: '/api/system',
  settings: '/api/settings',
  books: '/api/books',
  upload: '/api/books/upload',
  book: (id: number) => `/api/books/${id}`,
  run: (id: number) => `/api/books/${id}/run`,
  pages: (id: number) => `/api/books/${id}/pages`,
  bookFigures: (id: number) => `/api/books/${id}/figures`,
  file: (id: number, name: FileName) => `/api/books/${id}/files/${name}`,
  page: (id: number) => `/api/pages/${id}`,
  pageImage: (id: number, size: 'thumb' | 'preview' | 'full') => `/api/pages/${id}/image?size=${size}`,
  pageFigures: (id: number) => `/api/pages/${id}/figures`,
  scanPages: (id: number) => `/api/scans/${id}/pages`,
  scanImage: (id: number, angle: number) => `/api/scans/${id}/image?angle=${angle}`,
  figureImage: (id: number) => `/api/figures/${id}/image`,
} as const

/** The query keys the screens share, so a write can invalidate every read it changes. */
export const keys = {
  system: ['system'],
  settings: ['settings'],
  books: ['books'],
  book: (id: number) => ['books', id],
  pages: (id: number) => ['books', id, 'pages'],
  bookFigures: (id: number) => ['books', id, 'figures'],
  page: (id: number) => ['pages', id],
} as const

const send = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  system: () => fetchJson<SystemStatus>(withBase(paths.system)),
  settings: () => fetchJson<Settings>(withBase(paths.settings)),
  saveSettings: (s: Partial<Settings>) => fetchJson<Settings>(withBase(paths.settings), send('PUT', s)),
  books: () => fetchJson<Book[]>(withBase(paths.books)),
  book: (id: number) => fetchJson<Book>(withBase(paths.book(id))),
  addBook: (source: string) => fetchJson<Book>(withBase(paths.books), send('POST', { source })),
  upload: (file: File) => {
    const body = new FormData()
    body.set('file', file)
    return fetchJson<Book>(withBase(paths.upload), { method: 'POST', body })
  },
  run: (id: number, stages: Stage[]) => fetchJson<Book>(withBase(paths.run(id)), send('POST', { stages })),
  pages: (id: number) => fetchJson<PageSummary[]>(withBase(paths.pages(id))),
  bookFigures: (id: number) => fetchJson<BookFigure[]>(withBase(paths.bookFigures(id))),
  page: (id: number) => fetchJson<PageDetail>(withBase(paths.page(id))),
  savePage: (id: number, change: Partial<{ angle: number; crop: Crop; kind: Kind; label: string; text: string }>) => fetchJson<PageDetail>(withBase(paths.page(id)), send('PATCH', change)),
  setScanPages: (scanId: number, pages: { side: Side; angle: number; crop: Crop }[]) => fetchJson<PageSummary[]>(withBase(paths.scanPages(scanId)), send('PUT', { pages })),
  setFigures: (pageId: number, figures: { x: number; y: number; w: number; h: number; caption?: string | null }[]) => fetchJson<Figure[]>(withBase(paths.pageFigures(pageId)), send('PUT', { figures })),
}

/** The book's stage in a word, for its status: "Reading", or "Ready" when nothing runs. */
export const stageWord: Record<Stage, string> = { idle: 'Ready', import: 'Importing', detect: 'Finding pages', read: 'Reading', export: 'Exporting' }

/** Where a book is, as a sentence: "Reading page 12 of 206." or the error, or what it holds. */
export function describeBook(b: Book): string {
  if (b.error) return `Stopped: ${b.error}.`
  if (b.stage !== 'idle') {
    const what = { import: 'Importing scan', detect: 'Finding pages in scan', read: 'Reading page', export: 'Writing the files, step' }[b.stage]
    return b.total ? `${what} ${b.done} of ${b.total}.` : `${stageWord[b.stage]}…`
  }
  if (!b.pages) return 'No pages yet.'
  const check = b.to_check ? ` ${b.to_check} ${b.to_check === 1 ? 'page needs' : 'pages need'} a look.` : ''
  return `${b.pages} pages, ${b.read} read, ${b.figures} ${b.figures === 1 ? 'picture' : 'pictures'}.${check}`
}

/** The size of a scan turned by `angle` degrees: the canvas `geometry.rotate` makes, so a crop drawn on it is in the server's units. */
export function turnedSize(w: number, h: number, angle: number): [number, number] {
  const a = (angle * Math.PI) / 180
  const c = Math.abs(Math.cos(a))
  const s = Math.abs(Math.sin(a))
  return [Math.round(w * c + h * s), Math.round(w * s + h * c)]
}

/** A crop kept inside a canvas of `w` × `h`, at least 1 pixel each way. */
export function clampCrop(c: Crop, w: number, h: number): Crop {
  const x = Math.min(Math.max(0, Math.round(c.x)), w - 1)
  const y = Math.min(Math.max(0, Math.round(c.y)), h - 1)
  return { x, y, w: Math.max(1, Math.min(Math.round(c.w), w - x)), h: Math.max(1, Math.min(Math.round(c.h), h - y)) }
}

/** The same cut on the canvas of a new angle: its centre turned with the scan, its size kept (then clamped). */
export function turnCrop(c: Crop, scanW: number, scanH: number, from: number, to: number): Crop {
  const [fw, fh] = turnedSize(scanW, scanH, from)
  const [tw, th] = turnedSize(scanW, scanH, to)
  const d = ((to - from) * Math.PI) / 180
  const cx = c.x + c.w / 2 - fw / 2
  const cy = c.y + c.h / 2 - fh / 2
  // image y runs down, so a counter-clockwise turn of the picture is (x cos + y sin, -x sin + y cos)
  const nx = cx * Math.cos(d) + cy * Math.sin(d)
  const ny = -cx * Math.sin(d) + cy * Math.cos(d)
  return clampCrop({ x: tw / 2 + nx - c.w / 2, y: th / 2 + ny - c.h / 2, w: c.w, h: c.h }, tw, th)
}

/** An angle brought into (-180, 180], as the server takes it: a quarter turn past 180 comes round to -90. */
export const wrapAngle = (a: number) => Math.round((a > 180 ? a - 360 : a <= -180 ? a + 360 : a) * 10) / 10

/** A page's name in a sentence: its label when it has one ("Page 12, PUNCH AND JUDY"). */
export const pageName = (p: Pick<PageSummary, 'position' | 'label'>) => (p.label ? `Page ${p.position}, ${p.label}` : `Page ${p.position}`)

/** What is wrong with a data folder, or undefined. The server takes absolute paths only, `~` included. */
export function folderProblem(value: string): string | undefined {
  const v = value.trim()
  if (!v) return 'Enter the folder the scans and pages are kept in.'
  return /^(\/|~|[A-Za-z]:[\\/]|\\\\)/.test(v) ? undefined : 'Use a full path from the top of the disk, such as /home/ada/scans.'
}

/** What is wrong with a whole-number setting, or undefined (the server's limits: settings.py). */
export function wholeProblem(value: string, lo: number, hi: number): string | undefined {
  const n = Number(value.trim())
  return Number.isInteger(n) && n >= lo && n <= hi ? undefined : `Use a whole number from ${lo} to ${hi}.`
}
