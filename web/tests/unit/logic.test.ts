import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { colorSchemeScript, format } from 'strata-react'
import { clampCrop, describeBook, wrapAngle, folderProblem, pageName, turnCrop, turnedSize, wholeProblem, withBase } from '../../src/api'
import { collier, page14, page9, systemNearlyFull, systemNoModels, systemStatus, ward, wardPages } from '../../src/mocks/fixtures'
import { describeShelf, pickPdf } from '../../src/screens/BooksScreen'
import { describeWork, needsLook } from '../../src/screens/BookScreen'
import { describePage, halves, union } from '../../src/screens/PageScreen'
import { describeDisk, ofSize, usable } from '../../src/screens/SystemScreen'

describe('api helpers', () => {
  it('builds URLs under the base', () => {
    expect(withBase('/api/health')).toBe('/api/health')
    expect(withBase('relative')).toBe('relative')
  })

  it('takes only full paths for the data folder and whole numbers in range, as the server does', () => {
    for (const ok of ['/srv/scans', '~/scans', 'C:\\Users\\ada', 'D:/data', '\\\\nas\\share']) expect(folderProblem(ok)).toBeUndefined()
    expect(folderProblem('relative/path')).toMatch(/^Use a full path/)
    expect(folderProblem('   ')).toBe('Enter the folder the scans and pages are kept in.')
    expect(wholeProblem(' 600 ', 72, 1200)).toBeUndefined()
    for (const bad of ['71', '1201', '2.5', 'many', '']) expect(wholeProblem(bad, 72, 1200)).toBe('Use a whole number from 72 to 1200.')
  })

  it('names a page by its position and label', () => {
    expect(pageName({ position: 14, label: '4' })).toBe('Page 14, 4')
    expect(pageName({ position: 3, label: null })).toBe('Page 3')
  })
})

describe('adding a book', () => {
  it('takes the PDF among dropped files, and says why when there is none', () => {
    const pdf = new File(['%PDF'], 'Punch.PDF')
    expect(pickPdf([new File(['x'], 'a.jpg'), pdf])).toBe(pdf)
    expect(pickPdf([new File(['x'], 'cover.jpg')])).toMatch(/^cover\.jpg is not a PDF\. For photographs/)
    expect(pickPdf([])).toMatch(/^That is not a PDF/)
  })
})

describe('turning a scan', () => {
  it('grows the canvas as geometry.rotate does', () => {
    expect(turnedSize(200, 100, 0)).toEqual([200, 100])
    expect(turnedSize(200, 100, 90)).toEqual([100, 200])
    expect(turnedSize(200, 100, 30)).toEqual([223, 187])         // geometry.rotated_size(200, 100, 30)
  })

  it('brings an angle into (-180, 180]', () => {
    expect([wrapAngle(270), wrapAngle(-270), wrapAngle(180), wrapAngle(-180), wrapAngle(1.25)]).toEqual([-90, 90, 180, 180, 1.3])
  })

  it('keeps a cut inside the canvas', () => {
    expect(clampCrop({ x: -5, y: 90, w: 500, h: 50 }, 200, 100)).toEqual({ x: 0, y: 90, w: 200, h: 10 })
  })

  it('moves a cut with the scan, so the same part of the paper stays in it', () => {
    // the right half of a 200 x 100 scan, turned a quarter left, is its top half
    expect(turnCrop({ x: 100, y: 0, w: 100, h: 100 }, 200, 100, 0, 90)).toEqual({ x: 0, y: 0, w: 100, h: 100 })
    // a cut turned and turned back is where it was
    const c = { x: 40, y: 10, w: 60, h: 70 }
    expect(turnCrop(turnCrop(c, 200, 100, 0, 7), 200, 100, 7, 0)).toEqual(c)
  })

  it('splits a cut at its middle and joins cuts again', () => {
    const [l, r] = halves({ x: 10, y: 0, w: 101, h: 50 })
    expect(l).toEqual({ x: 10, y: 0, w: 51, h: 50 })
    expect(r).toEqual({ x: 61, y: 0, w: 50, h: 50 })
    expect(union([l, r])).toEqual({ x: 10, y: 0, w: 101, h: 50 })
  })
})

describe('the findings', () => {
  it('says where a book is', () => {
    expect(describeBook(ward)).toBe('44 pages, 44 read, 14 pictures. 3 pages need a look.')
    expect(describeBook(collier)).toBe('Reading page 97 of 206.')
    expect(describeBook({ ...collier, total: 0 })).toBe('Reading…')
    expect(describeBook({ ...collier, stage: 'idle', error: 'strata-models is not running' })).toBe('Stopped: strata-models is not running.')
    expect(describeBook({ ...ward, pages: 0 })).toBe('No pages yet.')
    expect(describeBook({ ...ward, figures: 1, to_check: 1 })).toBe('44 pages, 44 read, 1 picture. 1 page needs a look.')
  })

  it('sums up the shelf', () => {
    expect(describeShelf([])).toMatch(/^No books yet/)
    expect(describeShelf([collier, ward])).toBe(`${format.count(2, 'book')}, ${format.count(250, 'page')}. ${collier.title} is reading. ${format.count(3, 'page')} the page finder was unsure of need a look.`)
    expect(describeShelf([collier, { ...collier, id: 3 }, { ...ward, error: 'gone', to_check: 0 }])).toMatch(/is reading, and 1\sother\. 1\sbook stopped with an error\.$/)
  })

  it('points a book at the pages that need a look, or its files', () => {
    const unsure = wardPages.filter(needsLook)
    expect(unsure.map(p => p.position)).toEqual([1, 2, 44])                   // the covers
    expect(describeWork(ward, wardPages)).toBe(`${format.count(3, 'page')} need a look: the page finder was unsure where they are. Page 1 is first.`)
    const sure = wardPages.map(p => ({ ...p, hand: true }))
    expect(describeWork(ward, sure)).toMatch(/^44 pages, 44 read, 14 pictures\. 3 pages need a look\. The files are up to date as of /)
    expect(describeWork({ ...ward, files: {} }, sure)).toMatch(/The files are not made yet\.$/)
    expect(describeWork(collier, undefined)).toBe('Reading page 97 of 206.')
    expect(describeWork({ ...ward, pages: 0 }, [])).toMatch(/^No pages yet/)
    expect(describeWork(ward, [{ ...wardPages[0], hand: false, confidence: 0.3 }])).toMatch(/1\spage need a look: the page finder was unsure where it is/)
  })

  it('says what was unsure on a page', () => {
    expect(describePage(page14)).toBe(`Found and cut automatically. ${format.count(352, 'word')} read, ${format.count(1, 'line')} the reader was unsure of.`.replace('352', String(page14.words)))
    expect(describePage(page9)).toBe('Found and cut automatically. Marked picture. 1\u00a0picture.'.replace('1\u00a0picture', format.count(1, 'picture')))
    expect(describePage({ ...page14, confidence: 0.2 })).toMatch(/^The page finder was unsure where the page is \(20%\): check the cut\./)
    expect(describePage({ ...page14, hand: true, read: false })).toBe('Cut by hand. Not read yet.')
    expect(describePage({ ...page14, text_edited: true })).toBe('Found and cut automatically. The text was typed by hand.')
    expect(describePage({ ...page14, error: 'no such picture' })).toBe('Reading this page failed: no such picture.')
    expect(describePage({ ...page14, lines: [] })).toBe(`Found and cut automatically. ${format.count(page14.words, 'word')} read.`)
  })

  it('measures the disk as df does, and puts reading first', () => {
    expect(usable(systemStatus.disk)).toBe(512e9)
    expect(ofSize(301.6e9, 512e9)).toBe(`${format.bytes(301.6e9, 'GB')} of ${format.bytes(512e9, 'GB')}`)
    expect(describeDisk(systemStatus)).toBe(`Everything is running. The data disk is 59% full, with ${format.bytes(210.4e9)} free.`)
    expect(describeDisk(systemNearlyFull)).toMatch(/^The data disk is 96% full, .* Free space or move the data folder in Settings/)
    expect(describeDisk(systemNoModels)).toBe('Pages cannot be read: strata-models is not answering at http://127.0.0.1:8366. Books can still be imported and cut. The data disk is 59% full.')
    expect(describeDisk({ ...systemStatus, models: { ...systemStatus.models, ocr_model: null } })).toMatch(/has no ocr role/)
    expect(describeDisk(systemStatus, false)).toBe(`The server is not answering. When last read, the data disk was 59% full, with ${format.bytes(210.4e9)} free.`)
    expect(describeDisk({ ...systemStatus, disk: { total: 100, used: 85, free: 15 } })).toBe(`The data disk is 85% full, with ${format.bytes(15)} free. Nothing needs doing yet.`)
  })
})

describe('index.html', () => {
  it('inlines the colour-scheme script ThemeProvider expects, so a dark page does not flash light', () => {
    const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
    expect(html).toContain(`<script>${colorSchemeScript()}</script>`)
  })
})
