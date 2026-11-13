// The one question: "Who has been greeted, and what went out last?" The finding answers it in a
// sentence; then the next questions in the order a person asks them: how many, to how many people
// (figures), send another (the form, the one filled button), and which ones are kept (the table).
//
// Patterns shown here, each the Strata way:
// - a remote read is useLoad -> DataView, with a skeleton shaped like the table and an empty state
//   that teaches the next action;
// - a write is useAsyncAction -> AsyncButton, one label per phase, then a query invalidation;
// - a reversible removal is useUndoable -> UndoBar (no confirm dialog), rows filtered with
//   isRemoved, and the commit is the request plus the invalidation;
// - checkboxes only because a bulk action exists: useSelection -> DataTable selection -> BulkBar;
// - one filled button per view at a time: while greetings are chosen, the bulk "Remove N" is the
//   filled one and "Send greeting" steps down to outline until the selection clears;
// - the sort is in the URL (?sort=sent.asc), so a sorted table can be linked and reloaded.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import {
  AsyncButton,
  BulkBar,
  Button,
  DataTable,
  DataView,
  EmptyState,
  HttpError,
  Field,
  Input,
  Metric,
  MetricStrip,
  PageHeader,
  RowAction,
  TableSkeleton,
  UndoBar,
  format,
  useAsyncAction,
  useLoad,
  useSelection,
  useUndoable,
  type Column,
} from 'strata-react'
import { api, greetingProblem, keys, limits, type MessageRecord } from '../api'

/** The page's finding: how many, to how many people, and the latest, or what to do when there are none. */
export function describeLatest(messages: MessageRecord[]): string {
  const latest = messages[0]
  if (!latest) return 'No greetings have gone out yet. Send the first one below.'
  const people = new Set(messages.map(m => m.name)).size
  return `${format.count(messages.length, 'greeting')} to ${format.count(people, 'person', 'people')}. The latest, “${latest.message}”, went out on ${format.dateTime(latest.created)}.`
}

/** The most used greeting word, and how often; ties go to the one used most recently. */
export function favouriteWord(messages: MessageRecord[]): { word: string; times: number } | undefined {
  const counts = new Map<string, number>()
  for (const m of messages) counts.set(m.greeting, (counts.get(m.greeting) ?? 0) + 1)
  let best: { word: string; times: number } | undefined
  for (const [word, times] of counts) if (!best || times > best.times) best = { word, times }
  return best
}

const key = (m: MessageRecord) => String(m.id)

export function GreetingsScreen() {
  const load = useLoad({ queryKey: keys.messages, queryFn: api.messages })
  const queryClient = useQueryClient()
  const undoable = useUndoable()

  // The undo hook owns which rows are out of view: through Undo, a failed removal and the refetch.
  const rows = load.status === 'ready' ? load.data.filter(m => !undoable.isRemoved(key(m))) : []
  const selection = useSelection(rows, key)
  const favourite = favouriteWord(rows)

  /** One removal for one or many rows: one message, one Undo, one commit. */
  const remove = (chosen: MessageRecord[]) => {
    const one = chosen.length === 1 ? chosen[0] : undefined
    const ids = chosen.map(key)
    undoable.schedule({
      id: ids.join(','),
      ids,
      message: one ? `Removed “${one.message}”.` : `Removed ${format.count(chosen.length, 'greeting')}.`,
      failure: one ? `“${one.message}” is back: removing it did not go through.` : `The ${format.count(chosen.length, 'greeting')} are back: removing them did not go through.`,
      commit: async () => {
        // One request each, so a batch can fail part way. Read again whatever happens, so a greeting
        // that did go stays gone, and count one already gone (404, a retry after a partial failure) as done.
        try {
          for (const m of chosen) await api.removeMessage(m.id).catch(e => { if (!(e instanceof HttpError && e.status === 404)) throw e })
        } finally {
          await queryClient.invalidateQueries({ queryKey: keys.messages })
          await queryClient.invalidateQueries({ queryKey: keys.system })
        }
      },
    })
    selection.clear()
  }

  const columns: Column<MessageRecord>[] = [
    { key: 'message', header: 'Greeting', cell: m => m.message, truncate: true },
    { key: 'name', header: 'To', cell: m => m.name, sort: (a, b) => a.name.localeCompare(b.name) },
    { key: 'sent', header: 'Sent', cell: m => format.dateTime(m.created), sort: (a, b) => a.created.localeCompare(b.created), className: 'whitespace-nowrap' },
    { key: 'actions', header: 'Actions', hideHeader: true, cell: m => <RowAction label="Remove" subject={m.message} onClick={() => remove([m])} /> },
  ]

  return (
    <>
      <PageHeader
        title="Greetings"
        scope="Kept in the data folder on this computer"
        finding={load.status === 'ready' ? { text: describeLatest(rows) } : undefined}
      />

      <MetricStrip label="Greetings so far">
        <Metric label="Greetings kept" value={load.status === 'ready' ? format.integer(rows.length) : '–'} note="Removed ones are not counted" />
        <Metric label="People greeted" value={load.status === 'ready' ? format.integer(new Set(rows.map(m => m.name)).size) : '–'} note="Each name once" />
        <Metric label="Most used greeting" value={favourite?.word ?? '–'} note={favourite ? `Used ${format.count(favourite.times, 'time')}` : 'None sent yet'} />
      </MetricStrip>

      <GreetingForm primary={selection.count === 0} />

      <section aria-labelledby="kept" className="grid gap-3">
        <h2 id="kept" className="type-heading">Kept greetings</h2>
        <DataView
          state={load}
          isEmpty={() => rows.length === 0}
          skeleton={<TableSkeleton rows={6} columns={4} />}
          empty={<EmptyState title="Nothing kept yet">Greetings you send are kept here, newest first. Send one with the form above, or from the command line with <code className="font-mono">./app hello Ada --save</code>.</EmptyState>}
        >
          {() => (
            <div className="grid gap-3">
              <BulkBar count={selection.count} noun="greeting" onClear={selection.clear}>
                <Button size="sm" variant="default" onClick={() => remove(selection.selectedRows)}>
                  Remove {format.integer(selection.count)}
                </Button>
              </BulkBar>
              <DataTable
                caption="Kept greetings, newest first"
                columns={columns}
                rows={rows}
                rowKey={key}
                sortParam="sort"
                selection={{ ...selection, rowLabel: m => m.message }}
              />
            </div>
          )}
        </DataView>
      </section>
      <UndoBar undoable={undoable} />
    </>
  )
}

/** Send a greeting. Its own component so typing does not re-render the table. `primary` is false
 *  while rows are chosen, when the bulk action holds the view's one filled button. */
export function GreetingForm({ primary = true }: { primary?: boolean }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [word, setWord] = useState('')
  const [problems, setProblems] = useState<{ name?: string; greeting?: string }>({})
  const settings = useLoad({ queryKey: keys.settings, queryFn: api.settings })
  const fallback = settings.status === 'ready' ? `“${settings.data.greeting}”, the default in Settings` : 'the default in Settings'

  const send = useAsyncAction(async () => {
    await api.addMessage(name.trim() || 'World', word.trim() || undefined)
    setName('')
    setWord('')
    await queryClient.invalidateQueries({ queryKey: keys.messages })
    await queryClient.invalidateQueries({ queryKey: keys.system })
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const found = { name: greetingProblem('name', name), greeting: greetingProblem('greeting', word) }
    setProblems(found)
    if (!found.name && !found.greeting) void send.run()
  }

  return (
    <section aria-labelledby="send" className="grid gap-3">
      <h2 id="send" className="type-heading">Send a greeting</h2>
      <form onSubmit={onSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" hint={`Leave it empty to greet the World. Up to ${limits.name} characters.`} error={problems.name}>
          <Input value={name} onChange={e => setName(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="Greeting" hint={`Leave it empty for ${fallback}. Up to ${limits.greeting} characters.`} error={problems.greeting}>
          <Input value={word} onChange={e => setWord(e.target.value)} autoComplete="off" />
        </Field>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <AsyncButton type="submit" variant={primary ? 'default' : 'outline'} phase={send.phase} error={send.error} labels={{ idle: 'Send greeting', pending: 'Sending…', done: 'Sent' }} />
          {send.phase === 'error' && <p className="type-body-sm text-danger">{send.error} Nothing was kept.</p>}
        </div>
      </form>
    </section>
  )
}
