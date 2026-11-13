// The one question: "How is the app set up, and how do I change it?" Two tabs whose choice lives
// in the URL (?tab=appearance), so a link can open either one. General is a form over the server's
// settings: the fields start from what the server holds (rendered inside DataView's ready state,
// so they are never blank while loading), problems are said under the field they belong to, and
// saving is one AsyncButton through Saving… and Saved. Appearance is Strata's ColorSchemeChoice,
// which ThemeProvider (main.tsx) keeps in this browser.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { AsyncButton, ColorSchemeChoice, DataView, EmptyState, Field, Input, PageHeader, Skeleton, Tabs, useAsyncAction, useLoad } from 'strata-react'
import { api, folderProblem, keys, wholeProblem, type Settings } from '../api'

const tabs = [
  { value: 'general', label: 'General' },
  { value: 'appearance', label: 'Appearance' },
]

export function SettingsScreen() {
  return (
    <>
      <PageHeader title="Settings" scope="Saved on this computer, for every browser that opens the app" />
      <Tabs param="tab" items={tabs} label="Settings">
        {tab => (tab === 'appearance' ? <Appearance /> : <General />)}
      </Tabs>
    </>
  )
}

function General() {
  const load = useLoad({ queryKey: keys.settings, queryFn: api.settings })
  return (
    <DataView
      state={load}
      isEmpty={() => false}
      skeleton={<FormSkeleton />}
      empty={<EmptyState title="No settings">The server sent none.</EmptyState>}
    >
      {s => <SettingsForm current={s} />}
    </DataView>
  )
}

/** Mirrors the form: three fields with hints, then the button. */
function FormSkeleton() {
  return (
    <div className="grid max-w-xl gap-6" aria-hidden>
      {[0, 1, 2].map(i => (
        <div key={i} className="grid gap-1.5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ))}
      <Skeleton className="h-9 w-32" />
    </div>
  )
}

export function SettingsForm({ current }: { current: Settings }) {
  const queryClient = useQueryClient()
  const [folder, setFolder] = useState(current.data_dir)
  const [dpi, setDpi] = useState(current.max_dpi)
  const [workers, setWorkers] = useState(current.workers)
  const [problems, setProblems] = useState<{ folder?: string; dpi?: string; workers?: string }>({})

  const save = useAsyncAction(async () => {
    await api.saveSettings({ data_dir: folder.trim(), max_dpi: dpi.trim(), workers: workers.trim() })
    // Everything that reads the settings, or the folder they point at, reads again.
    await Promise.all([keys.settings, keys.books, keys.system].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const found = { folder: folderProblem(folder), dpi: wholeProblem(dpi, 72, 1200), workers: wholeProblem(workers, 1, 32) }
    setProblems(found)
    if (!found.folder && !found.dpi && !found.workers) void save.run()
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid max-w-xl gap-6">
      <Field label="Data folder" hint="A full path. The scans, pages, pictures and files are kept there, a few hundred MB a book; moving it does not move them." error={problems.folder}>
        <Input value={folder} onChange={e => setFolder(e.target.value)} autoComplete="off" spellCheck={false} />
      </Field>
      <Field label="Highest resolution" hint="Dots per inch, 72 to 1200. A PDF page is drawn at the resolution of the scan inside it, up to this." error={problems.dpi}>
        <Input value={dpi} onChange={e => setDpi(e.target.value)} inputMode="numeric" autoComplete="off" />
      </Field>
      <Field label="Pages at once" hint="1 to 32. strata-models reads four at a time, so more than four only queue there." error={problems.workers}>
        <Input value={workers} onChange={e => setWorkers(e.target.value)} inputMode="numeric" autoComplete="off" />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="default" phase={save.phase} error={save.error} labels={{ idle: 'Save settings', pending: 'Saving…', done: 'Saved' }} />
        {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The settings were not changed.</p>}
      </div>
    </form>
  )
}

function Appearance() {
  return (
    <div className="grid max-w-xl gap-3">
      <ColorSchemeChoice legend="Colour scheme" />
      <p className="type-body-sm text-muted-foreground">Kept in this browser only.</p>
    </div>
  )
}
