// The mock server: MSW handlers for every endpoint the app calls, answering like a healthy server.
// One set serves the jsdom tests (Node, tests/utils/server.ts), Storybook (a service worker,
// .storybook/preview.tsx) and the visual suite (Node, strata-visual.config.ts), so the app's real
// fetch, query and DataView code runs in all three and nothing is a module mock.
//
// The named handlers below each replace one route to put a test, story or screenshot into another
// state: `server.use(messagesError)` in a test, `msw.use(messagesError)` in a story's beforeEach,
// `states: { error: [messagesError] }` in the visual config.
import { delay, http, HttpResponse } from 'msw'
import { paths, type MessagePage, type MessageRecord, type Settings } from '../api'
import { defaultSettings, initialMessages, longLog, systemNearlyFull as nearlyFull, systemStatus } from './fixtures'

/** What the mock server holds. Writes change it, so a test can add a greeting and see it listed. */
export const mock = {
  settings: { ...defaultSettings } as Settings,
  messages: [...initialMessages] as MessageRecord[],
}

/** Back to the healthy state: call between tests and stories. */
export function resetMock() {
  mock.settings = { ...defaultSettings }
  mock.messages = [...initialMessages]
}

// Matched as paths, so they answer whatever origin and base the app runs under.
const at = (path: string) => `*${path}`

/** Serves `GET /api/messages/page?after=<id>&limit=<n>` from a list, as greet.page_messages does. */
export function messagePage(url: string, list: MessageRecord[]): MessagePage {
  const params = new URL(url).searchParams
  const after = params.get('after')
  const limit = Number(params.get('limit') ?? 20)
  const rest = after === null ? list : list.filter(m => m.id < Number(after))
  return { messages: rest.slice(0, limit), has_more: rest.length > limit }
}

const refused = (detail: string, status = 400) => HttpResponse.json({ detail }, { status })

export const handlers = [
  http.get(at(paths.health), () => HttpResponse.json({ ok: true, version: systemStatus.version })),
  http.get(at(paths.system), () => HttpResponse.json({ ...systemStatus, data_dir: mock.settings.data_dir, messages: mock.messages.length })),
  http.get(at(paths.settings), () => HttpResponse.json(mock.settings)),
  http.put(at(paths.settings), async ({ request }) => {
    const body = (await request.json()) as Partial<Settings>
    if (body.data_dir !== undefined && !body.data_dir.startsWith('/') && !body.data_dir.startsWith('~')) return refused('the data folder must be an absolute path')
    mock.settings = { ...mock.settings, ...body }
    return HttpResponse.json(mock.settings)
  }),
  http.get(at(paths.messages), () => HttpResponse.json(mock.messages)),
  http.get(at(paths.messagesPage), ({ request }) => HttpResponse.json(messagePage(request.url, mock.messages))),
  http.post(at(paths.messages), async ({ request }) => {
    const b = (await request.json()) as { name?: string; greeting?: string }
    const name = (b.name ?? '').trim() || 'World'
    const greeting = (b.greeting ?? '').trim() || mock.settings.greeting
    const id = Math.max(0, ...mock.messages.map(m => m.id)) + 1
    const entry: MessageRecord = { id, name, greeting, message: `${greeting}, ${name}!`, created: '2026-11-09T09:30:00.000Z' }
    mock.messages = [entry, ...mock.messages]
    return HttpResponse.json(entry)
  }),
  http.delete(at('/api/messages/:id'), ({ params }) => {
    const found = mock.messages.find(m => m.id === Number(params.id))
    if (!found) return refused(`there is no greeting ${params.id}`, 404)
    mock.messages = mock.messages.filter(m => m !== found)
    return HttpResponse.json(found)
  }),
]

// States. A request that never answers is "loading"; 503 is a server that is down. The app's query
// client retries once, so an error shows after about a second (tests turn retries off).

export const messagesLoading = http.get(at(paths.messages), () => delay('infinite'))
export const messagesEmpty = http.get(at(paths.messages), () => HttpResponse.json([]))
export const messagesError = http.get(at(paths.messages), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))
export const addFails = http.post(at(paths.messages), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))
export const removeFails = http.delete(at('/api/messages/:id'), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))

export const logLoading = http.get(at(paths.messagesPage), () => delay('infinite'))
export const logEmpty = http.get(at(paths.messagesPage), () => HttpResponse.json({ messages: [], has_more: false }))
export const logError = http.get(at(paths.messagesPage), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))
/** 75 greetings, four pages of 20. */
export const logLong = http.get(at(paths.messagesPage), ({ request }) => HttpResponse.json(messagePage(request.url, longLog)))
/** The first page arrives; every page after it fails, so the list shows its Try again row. */
export const logLaterPageError = http.get(at(paths.messagesPage), ({ request }) =>
  new URL(request.url).searchParams.has('after') ? new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }) : HttpResponse.json(messagePage(request.url, longLog)),
)

export const systemLoading = http.get(at(paths.system), () => delay('infinite'))
export const systemError = http.get(at(paths.system), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))
export const systemNearlyFull = http.get(at(paths.system), () => HttpResponse.json(nearlyFull))

export const settingsLoading = http.get(at(paths.settings), () => delay('infinite'))
export const settingsError = http.get(at(paths.settings), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))
export const saveSettingsFails = http.put(at(paths.settings), () => new HttpResponse(null, { status: 503, statusText: 'Service Unavailable' }))
