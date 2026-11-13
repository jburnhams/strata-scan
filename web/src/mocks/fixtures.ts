// Sample data for the mock server (handlers.ts): the same records answer the unit and integration
// tests, every Storybook story and the visual suite's screenshots, so a screen looks the same in
// each. They follow the two real books strata-scan was built for (both public domain), with fixed
// dates, so screenshots do not change from day to day.
import type { Book, BookFigure, Kind, Line, PageDetail, PageSummary, Settings, SystemStatus } from '../api'

export const defaultSettings: Settings = { data_dir: '/home/ada/scans', max_dpi: '600', workers: '4' }

/** The 1874 manual, read and exported. */
export const ward: Book = {
  id: 1,
  title: 'Punch and Judy, with instructions how to manage the little wooden actors',
  author: 'T. A. M. Ward',
  source: '/home/ada/books/punch-and-judy-1874.pdf',
  lang: 'eng',
  stage: 'idle',
  done: 44,
  total: 44,
  error: null,
  created_at: '2026-11-13T21:40:00',
  updated_at: '2026-11-13T21:43:02',
  scans: 44,
  pages: 44,
  read: 44,
  figures: 14,
  to_check: 3,
  files: { 'book.md': 1794606182, 'book.txt': 1794606182, 'book.pdf': 1794606183, 'book.zip': 1794606184 },
}

/** The 1828 Collier and Cruikshank, half read. */
export const collier: Book = {
  id: 2,
  title: 'Punch and Judy, with illustrations by George Cruikshank',
  author: 'J. P. Collier',
  source: '/home/ada/books/punch-and-judy-1828.pdf',
  lang: 'eng',
  stage: 'read',
  done: 97,
  total: 206,
  error: null,
  created_at: '2026-11-13T22:35:35',
  updated_at: '2026-11-13T22:59:43',
  scans: 206,
  pages: 206,
  read: 97,
  figures: 21,
  to_check: 0,
  files: {},
}

export const initialBooks: Book[] = [collier, ward]

/** The kinds of the 1874 book's 44 pages, as the reader guessed them. */
const kinds: Kind[] = [
  'cover', 'cover', 'picture', 'blank', 'blank', 'blank', 'blank', 'blank', 'picture', 'blank',
  ...Array.from({ length: 24 }, () => 'text' as Kind),
  'blank', 'text', 'blank', 'blank', 'blank', 'blank', 'blank', 'text', 'picture', 'cover',
]

/** The 1874 book's pages, in reading order: ids 101 to 144. Pages 14 to 33 carry their printed number as the label. */
export const wardPages: PageSummary[] = kinds.map((kind, i) => {
  const position = i + 1
  const sure = kind === 'cover' ? 0.2 : 0.9
  return {
    id: 100 + position,
    book_id: 1,
    scan_id: position,
    position,
    side: 'single',
    angle: 0,
    crop: { x: 0, y: 0, w: 2674, h: 4084 },
    confidence: sure,
    hand: false,
    kind,
    label: position >= 14 && position <= 33 ? String(position - 10) : null,
    read: true,
    ocr_conf: kind === 'text' ? 92.4 : null,
    words: kind === 'text' ? 300 + ((position * 37) % 150) : 0,
    text_edited: false,
    figures: kind === 'picture' || kind === 'cover' ? 1 : 0,
    error: null,
  }
})

/** The first lines of page 14, as Tesseract read them (boxes in the page's pixels). */
export const page14Lines: Line[] = [
  { text: '4. PUNCH AND JUDY.', box: [481, 445, 1174, 59], conf: 94.6 },
  { text: '“The Play of Puncn anp Jupy,” observes a writer in Har-', box: [556, 623, 1781, 65], conf: 61.8 },
  { text: 'pers Monthly, “was exhibited for a short time at a popular', box: [473, 710, 1865, 67], conf: 91.4 },
  { text: 'place of amusement in Mew York City, in 1870, but did not', box: [482, 795, 1857, 66], conf: 95.9 },
  { text: 'take sufficiently with the audience to induce the managers to', box: [482, 880, 1853, 67], conf: 96.2 },
  { text: 'go on with it.”', box: [484, 966, 429, 67], conf: 96.3 },
  { text: 'The true cause of its failure, at the time, doubtless arose from', box: [552, 1050, 1784, 60], conf: 96.2 },
  { text: 'the vulgar and impure language, used by the fellow that work-', box: [482, 1133, 1854, 68], conf: 95.5 },
  { text: 'ed the Figures.', box: [485, 1220, 439, 66], conf: 96.1 },
]

/** Page 14 in full, as `GET /api/pages/114` answers. */
export const page14: PageDetail = {
  ...wardPages[13],
  scan: { id: 14, position: 14, width: 2674, height: 4084, dpi: 500 },
  size: { w: 2674, h: 4084 },
  text: page14Lines.map(l => l.text).join('\n'),
  lines: page14Lines,
  ocr_model: 'tesseract-eng',
  figures_list: [],
  siblings: [{ id: 114, side: 'single', angle: 0, crop: { x: 0, y: 0, w: 2674, h: 4084 } }],
  prev_id: 113,
  next_id: 115,
}

/** Page 9, an engraving with a few words under it: one picture found. */
export const page9: PageDetail = {
  ...wardPages[8],
  angle: 0.7,
  crop: { x: 24, y: 16, w: 2660, h: 4063 },
  confidence: 0.68,
  scan: { id: 9, position: 9, width: 2660, height: 4063, dpi: 500 },
  size: { w: 2660, h: 4063 },
  text: 'PUNCH AND JUDY.',
  lines: [{ text: 'PUNCH AND JUDY.', box: [820, 3620, 1010, 90], conf: 88.0 }],
  ocr_model: 'tesseract-eng',
  figures_list: [{ id: 9, page_id: 109, x: 300, y: 420, w: 2060, h: 3020, caption: null, hand: false }],
  siblings: [{ id: 109, side: 'single', angle: 0.7, crop: { x: 24, y: 16, w: 2660, h: 4063 } }],
  prev_id: 108,
  next_id: 110,
}

/** Any other page of the book, from its summary: no lines, no pictures. */
export function pageDetail(p: PageSummary): PageDetail {
  const at = wardPages.findIndex(x => x.id === p.id)
  return {
    ...p,
    scan: { id: p.scan_id, position: p.position, width: p.crop.w, height: p.crop.h, dpi: 500 },
    size: { w: p.crop.w, h: p.crop.h },
    text: p.kind === 'text' ? 'The text of this page.' : null,
    lines: [],
    ocr_model: 'tesseract-eng',
    figures_list: [],
    siblings: [{ id: p.id, side: p.side, angle: p.angle, crop: p.crop }],
    prev_id: at > 0 ? wardPages[at - 1].id : null,
    next_id: at >= 0 && at < wardPages.length - 1 ? wardPages[at + 1].id : null,
  }
}

/** Every picture in the 1874 book. */
export const wardFigures: BookFigure[] = [
  ...wardPages.filter(p => p.figures).map(p => ({ id: p.position, page_id: p.id, x: 300, y: 420, w: 2060, h: 3020, caption: null, hand: false, page_position: p.position, page_label: p.label })),
  // one drawn by hand, wide, with its caption typed
  { id: 50, page_id: 122, x: 480, y: 2400, w: 1800, h: 900, caption: 'Punch and the Constable', hand: true, page_position: 22, page_label: '12' },
]

export const GB = 1e9

export const systemStatus: SystemStatus = {
  version: '0.1.0',
  python: '3.13.1',
  platform: 'Linux 6.8.0',
  data_dir: defaultSettings.data_dir,
  data_bytes: 1.84 * GB,
  disk: { total: 512 * GB, used: 301.6 * GB, free: 210.4 * GB },
  models: { url: 'http://127.0.0.1:8366', available: true, ocr_model: 'tesseract-eng' },
}

/** The same server with its data disk past the "nearly full" threshold. */
export const systemNearlyFull: SystemStatus = { ...systemStatus, disk: { total: 512 * GB, used: 492 * GB, free: 20 * GB } }

/** strata-models is not answering: pages cannot be read. */
export const systemNoModels: SystemStatus = { ...systemStatus, models: { url: 'http://127.0.0.1:8366', available: false, ocr_model: null } }
