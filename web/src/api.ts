// The FastAPI server's endpoints (src/app/server/app.py) and their shapes. Reads go through
// strata-react's useLoad / useInfiniteLoad with fetchJson, which throws HttpError on a non-2xx
// answer; the screens never call fetch themselves. Every URL is built here, through withBase, so
// the app works at the server's root and behind a reverse proxy at /<prefix>/.
import { fetchJson } from 'strata-react'

export interface Health { ok: boolean; version: string }
export interface Settings { data_dir: string; greeting: string }
export interface Greeting { name: string; greeting: string; message: string }
export interface MessageRecord extends Greeting { id: number; created: string }
/** One page of the log, newest first: `GET /api/messages/page?after=<id>&limit=<n>`. */
export interface MessagePage { messages: MessageRecord[]; has_more: boolean }
/** `GET /api/system`. Sizes are bytes. */
export interface SystemStatus {
  version: string
  python: string
  platform: string
  data_dir: string
  messages: number
  data_bytes: number
  disk: { total: number; used: number; free: number }
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
  messages: '/api/messages',
  messagesPage: '/api/messages/page',
  message: (id: number) => `/api/messages/${id}`,
} as const

/** The query keys the screens share, so a write can invalidate every read it changes. */
export const keys = {
  health: ['health'],
  system: ['system'],
  settings: ['settings'],
  messages: ['messages'],
  log: ['messages', 'log'],
} as const

export function pageUrl(after: number | undefined, limit: number) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (after !== undefined) params.set('after', String(after))
  return withBase(`${paths.messagesPage}?${params}`)
}

const send = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  system: () => fetchJson<SystemStatus>(withBase(paths.system)),
  settings: () => fetchJson<Settings>(withBase(paths.settings)),
  saveSettings: (s: Partial<Settings>) => fetchJson<Settings>(withBase(paths.settings), send('PUT', s)),
  messages: () => fetchJson<MessageRecord[]>(withBase(paths.messages)),
  page: (after: number | undefined, limit: number, signal?: AbortSignal) => fetchJson<MessagePage>(pageUrl(after, limit), { signal }),
  addMessage: (name: string, greeting?: string) => fetchJson<MessageRecord>(withBase(paths.messages), send('POST', greeting ? { name, greeting } : { name })),
  removeMessage: (id: number) => fetchJson<MessageRecord>(withBase(paths.message(id)), { method: 'DELETE' }),
}

// The server's own limits (src/app/greet.py format_greeting, server put_settings), checked here
// too so a person sees the reason under the field before sending. The server's 400 carries the
// same sentence in its body, but fetchJson's HttpError does not keep the body (jburnhams/strata-react#42),
// so without these the field could only say "refused (400)".
export const limits = { name: 120, greeting: 60 } as const

/** What is wrong with a greeting's name or word, in a sentence, or undefined when it can be sent. */
export function greetingProblem(field: 'name' | 'greeting', value: string): string | undefined {
  const max = limits[field]
  return value.trim().length > max ? `Use at most ${max} characters; this is ${value.trim().length}.` : undefined
}

/** What is wrong with a data folder, or undefined. The server takes absolute paths only, `~` included. */
export function folderProblem(value: string): string | undefined {
  const v = value.trim()
  if (!v) return 'Enter the folder greetings are kept in.'
  return /^(\/|~|[A-Za-z]:[\\/]|\\\\)/.test(v) ? undefined : 'Use a full path from the top of the disk, such as /home/ada/greetings.'
}
