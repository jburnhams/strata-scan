// The one question: "How is the app set up, and how do I change it?" Two tabs whose choice lives
// in the URL (?tab=appearance), so a link can open either one. General is a form over the server's
// settings: the fields start from what the server holds (rendered inside DataView's ready state,
// so they are never blank while loading), problems are said under the field they belong to, and
// saving is one AsyncButton through Saving… and Saved. Appearance is Strata's ColorSchemeChoice,
// which ThemeProvider (main.tsx) keeps in this browser.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { AsyncButton, ColorSchemeChoice, DataView, EmptyState, Field, Input, PageHeader, Skeleton, Tabs, useAsyncAction, useLoad } from 'strata-react'
import { api, folderProblem, greetingProblem, keys, limits, type Settings } from '../api'

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

/** Mirrors the form: two fields with hints, then the button. */
function FormSkeleton() {
  return (
    <div className="grid max-w-xl gap-6" aria-hidden>
      {[0, 1].map(i => (
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
  const [greeting, setGreeting] = useState(current.greeting)
  const [folder, setFolder] = useState(current.data_dir)
  const [problems, setProblems] = useState<{ greeting?: string; folder?: string }>({})

  const save = useAsyncAction(async () => {
    await api.saveSettings({ greeting: greeting.trim(), data_dir: folder.trim() })
    // Everything that reads the settings, or the folder they point at, reads again.
    await Promise.all([keys.settings, keys.messages, keys.system].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const found = {
      greeting: greeting.trim() ? greetingProblem('greeting', greeting) : 'Enter the word greetings start with, such as Hello.',
      folder: folderProblem(folder),
    }
    setProblems(found)
    if (!found.greeting && !found.folder) void save.run()
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid max-w-xl gap-6">
      <Field label="Default greeting" hint={`Used when a greeting is sent without one. Up to ${limits.greeting} characters.`} error={problems.greeting}>
        <Input value={greeting} onChange={e => setGreeting(e.target.value)} autoComplete="off" />
      </Field>
      <Field label="Data folder" hint="A full path. Greetings are kept in messages.json there; moving it starts an empty log." error={problems.folder}>
        <Input value={folder} onChange={e => setFolder(e.target.value)} autoComplete="off" spellCheck={false} />
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
