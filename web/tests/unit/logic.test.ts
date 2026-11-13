import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { colorSchemeScript, format } from 'strata-react'
import { folderProblem, greetingProblem, pageUrl, withBase } from '../../src/api'
import { initialMessages, makeMessages, systemNearlyFull, systemStatus } from '../../src/mocks/fixtures'
import { messagePage } from '../../src/mocks/handlers'
import { describeLatest, favouriteWord } from '../../src/screens/GreetingsScreen'
import { describeDisk, ofSize, usable } from '../../src/screens/SystemScreen'

describe('api helpers', () => {
  it('builds URLs under the base and pages after a cursor', () => {
    expect(withBase('/api/health')).toBe('/api/health')
    expect(withBase('relative')).toBe('relative')
    expect(pageUrl(undefined, 20)).toBe('/api/messages/page?limit=20')
    expect(pageUrl(41, 20)).toBe('/api/messages/page?limit=20&after=41')
  })

  it('says what is wrong with a name or greeting that is too long, and nothing otherwise', () => {
    expect(greetingProblem('name', 'Ada')).toBeUndefined()
    expect(greetingProblem('name', `  ${'x'.repeat(120)}  `)).toBeUndefined()
    expect(greetingProblem('name', 'x'.repeat(121))).toBe('Use at most 120 characters; this is 121.')
    expect(greetingProblem('greeting', 'g'.repeat(61))).toBe('Use at most 60 characters; this is 61.')
  })

  it('takes only full paths for the data folder, as the server does', () => {
    for (const ok of ['/srv/greetings', '~/greetings', 'C:\\Users\\ada', 'D:/data', '\\\\nas\\share']) expect(folderProblem(ok)).toBeUndefined()
    expect(folderProblem('relative/path')).toMatch(/^Use a full path/)
    expect(folderProblem('   ')).toBe('Enter the folder greetings are kept in.')
  })
})

describe('the Greetings finding and figures', () => {
  it('counts greetings and people and names the latest', () => {
    const two = [
      { id: 2, name: 'Ada', greeting: 'Hi', message: 'Hi, Ada!', created: '2026-11-09T09:12:00Z' },
      { id: 1, name: 'Ada', greeting: 'Hello', message: 'Hello, Ada!', created: '2026-11-08T09:12:00Z' },
    ]
    expect(describeLatest(two)).toBe(`${format.count(2, 'greeting')} to ${format.count(1, 'person', 'people')}. The latest, “Hi, Ada!”, went out on ${format.dateTime('2026-11-09T09:12:00Z')}.`)
    expect(describeLatest([])).toBe('No greetings have gone out yet. Send the first one below.')
  })

  it('finds the most used greeting word', () => {
    expect(favouriteWord(initialMessages)).toEqual({ word: 'Hello', times: 4 })
    expect(favouriteWord([])).toBeUndefined()
  })
})

describe('the System finding', () => {
  it('measures the disk as df does and names the threshold crossed', () => {
    expect(usable(systemStatus.disk)).toBe(512e9)
    expect(ofSize(301.6e9, 512e9)).toBe(`${format.bytes(301.6e9, 'GB')} of ${format.bytes(512e9, 'GB')}`)
    expect(describeDisk(systemStatus)).toBe(`Everything is running. The data disk is 59% full, with ${format.bytes(210.4e9)} free.`)
    expect(describeDisk(systemNearlyFull)).toMatch(/^The data disk is 96% full, .* Free space or move the data folder in Settings/)
    const filling = { ...systemStatus, disk: { total: 100, used: 85, free: 15 } }
    expect(describeDisk(systemStatus, false)).toBe(`The server is not answering. When last read, the data disk was 59% full, with ${format.bytes(210.4e9)} free.`)
    expect(describeDisk(filling)).toBe(`The data disk is 85% full, with ${format.bytes(15)} free. Nothing needs doing yet.`)
  })
})

describe('the mock server', () => {
  it('pages the log after a cursor, as greet.page_messages does', () => {
    const log = makeMessages(5)                          // ids 5..1, newest first
    const url = (q: string) => `http://x/api/messages/page?${q}`
    expect(messagePage(url('limit=2'), log)).toEqual({ messages: log.slice(0, 2), has_more: true })
    expect(messagePage(url('after=2&limit=2'), log)).toEqual({ messages: log.slice(4), has_more: false })
    expect(messagePage(url(''), log).messages).toHaveLength(5)
  })
})

describe('index.html', () => {
  it('inlines the colour-scheme script ThemeProvider expects, so a dark page does not flash light', () => {
    const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8')
    expect(html).toContain(`<script>${colorSchemeScript()}</script>`)
  })
})
