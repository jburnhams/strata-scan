// Sample data for the mock server (handlers.ts): the same records answer the unit and integration
// tests, every Storybook story and the visual suite's screenshots, so a screen looks the same in
// each. Dates are fixed, so screenshots do not change from day to day.
import type { MessageRecord, Settings, SystemStatus } from '../api'

export const defaultSettings: Settings = { data_dir: '/home/ada/.local/share/greetings', greeting: 'Hello' }

const people = ['Grace', 'Alan', 'Ada', 'Linus', 'Margaret', 'Edsger', 'Barbara', 'Ken', 'Frances', 'Dennis', 'Radia', 'Tim']
const words = ['Hello', 'Hello', 'Welcome', 'Good morning', 'Hello', 'Hi']

/** `n` greetings, newest first, one every 97 minutes back from 09:12 UTC on 9 November 2026: the shape `GET /api/messages` returns. */
export function makeMessages(n: number): MessageRecord[] {
  const newest = Date.UTC(2026, 10, 9, 9, 12)
  return Array.from({ length: n }, (_, i) => {
    const id = n - i
    const name = people[id % people.length]
    const greeting = words[id % words.length]
    return { id, name, greeting, message: `${greeting}, ${name}!`, created: new Date(newest - i * 97 * 60_000).toISOString() }
  })
}

/** What the server holds in the healthy state: eight greetings. */
export const initialMessages = makeMessages(8)

/** A long log, for paging: 75 greetings, so the Log screen needs four pages of 20. */
export const longLog = makeMessages(75)

export const GB = 1e9

export const systemStatus: SystemStatus = {
  version: '0.1.0',
  python: '3.13.1',
  platform: 'Linux 6.8.0',
  data_dir: defaultSettings.data_dir,
  messages: initialMessages.length,
  data_bytes: 18_432,
  disk: { total: 512 * GB, used: 301.6 * GB, free: 210.4 * GB },
}

/** The same server with its data disk past the "nearly full" threshold. */
export const systemNearlyFull: SystemStatus = { ...systemStatus, data_bytes: 2.4 * GB, disk: { total: 512 * GB, used: 492 * GB, free: 20 * GB } }
