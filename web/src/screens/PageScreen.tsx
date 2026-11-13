// The one question: "Is this page right, and if not, what do I fix?" The finding says what the
// automation was unsure of (where the page is, or what it says); three tabs in the URL hold the
// three fixes, in the order they depend on each other: the cut (turn and crop on the scan, split
// or join a spread), the text (typed over what was read, the page's kind and label), the pictures
// (drawn on the page). P and N move through the book, so a run of pages is checked from the keys.
//
// A change of cut or turn is hand work the server keeps: it draws the page again and reads it
// again, so the text and pictures tabs follow. A typed text is kept through every re-read.
import { useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import {
  AsyncButton,
  Button,
  ChoiceGroup,
  DataView,
  EmptyState,
  Field,
  Input,
  KeysLegend,
  NumberField,
  PageHeader,
  RegionEditor,
  Skeleton,
  Status,
  Tabs,
  Textarea,
  buttonVariants,
  format,
  useAsyncAction,
  useHotkeys,
  useLoad,
  type EditableRegion,
  type Shortcut,
} from 'strata-react'
import { api, keys, pageName, paths, turnCrop, turnedSize, withBase, wrapAngle, type Crop, type Kind, type PageDetail, type Side } from '../api'

const tabs = [
  { value: 'page', label: 'Cut' },
  { value: 'text', label: 'Text' },
  { value: 'pictures', label: 'Pictures' },
]

export const kindChoices: { value: Kind; label: string; detail: string }[] = [
  { value: 'text', label: 'Text', detail: 'Read and exported.' },
  { value: 'picture', label: 'Picture', detail: 'Mostly an illustration; its words are kept only where the reader was sure.' },
  { value: 'cover', label: 'Cover', detail: 'Kept as a picture in the PDF.' },
  { value: 'blank', label: 'Blank', detail: 'Kept in the PDF, left out of the text.' },
  { value: 'skip', label: 'Leave out', detail: 'Not exported at all (a scanner target, a duplicate).' },
]

/** A line the reader was unsure of: below this mean confidence it is worth a look. */
export const UNSURE = 70

/** The page's finding: what the automation was unsure of, in the order a person fixes it. */
export function describePage(p: PageDetail): string {
  if (p.error) return `Reading this page failed: ${p.error}.`
  const unsure = p.lines.filter(l => l.conf < UNSURE).length
  const where = p.hand ? 'Cut by hand.' : p.confidence < 0.6 ? `The page finder was unsure where the page is (${format.percent(p.confidence)}): check the cut.` : 'Found and cut automatically.'
  if (!p.read) return `${where} Not read yet.`
  const what = p.text_edited ? 'The text was typed by hand.' : p.kind === 'text' ? `${format.count(p.words, 'word')} read${unsure ? `, ${format.count(unsure, 'line')} the reader was unsure of` : ''}.` : `Marked ${p.kind}.`
  return `${where} ${what}${p.figures ? ` ${format.count(p.figures, 'picture')}.` : ''}`
}

export function PageScreen() {
  const id = Number(useParams().pageId)
  const navigate = useNavigate()
  const { search } = useLocation()
  const load = useLoad({ queryKey: keys.page(id), queryFn: () => api.page(id) })
  const p = load.status === 'ready' ? load.data : undefined

  const shortcuts: Shortcut[] = [
    { keys: ['p'], label: 'Previous page', run: () => p?.prev_id && navigate(`/pages/${p.prev_id}${search}`), disabled: !p?.prev_id },
    { keys: ['n'], label: 'Next page', run: () => p?.next_id && navigate(`/pages/${p.next_id}${search}`), disabled: !p?.next_id },
  ]
  useHotkeys(shortcuts)

  return (
    <>
      <PageHeader
        title={p ? pageName(p) : 'Page'}
        scope={p ? <Link to={`/books/${p.book_id}`} className="underline-offset-4 hover:underline">Back to the book</Link> : undefined}
        finding={p ? { text: describePage(p) } : undefined}
        actions={
          p && (
            <nav aria-label="Pages" className="flex gap-2">
              {p.prev_id ? <Link className={buttonVariants({ variant: 'outline' })} to={`/pages/${p.prev_id}${search}`}>Previous page</Link> : null}
              {p.next_id ? <Link className={buttonVariants({ variant: 'outline' })} to={`/pages/${p.next_id}${search}`}>Next page</Link> : null}
            </nav>
          )
        }
      />
      <DataView
        state={load}
        isEmpty={() => false}
        skeleton={<Skeleton className="aspect-[2/3] w-full max-w-md" />}
        empty={<EmptyState title="No page">The server sent nothing.</EmptyState>}
      >
        {page => (
          <Tabs param="tab" items={tabs} label="Fix the page">
            {tab => (tab === 'text' ? <TextEditor key={page.id} page={page} /> : tab === 'pictures' ? <FigureEditor key={page.id} page={page} /> : <CutEditor key={`${page.id}-${page.angle}`} page={page} />)}
          </Tabs>
        )}
      </DataView>
      <KeysLegend shortcuts={shortcuts} label="Page keys" />
    </>
  )
}

/** Everything a change to a page makes stale: the page, its book's lists and counts. */
function useRefresh(page: PageDetail) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([keys.page(page.id), keys.pages(page.book_id), keys.book(page.book_id), keys.bookFigures(page.book_id)].map(queryKey => queryClient.invalidateQueries({ queryKey })))
}

const SIDE_WORD: Record<Side, string> = { single: 'Page', left: 'Left page', right: 'Right page' }

/** The two halves of a cut, for splitting a spread at its middle. */
export function halves(c: Crop): [Crop, Crop] {
  const left = Math.round(c.w / 2)
  return [{ ...c, w: left }, { ...c, x: c.x + left, w: c.w - left }]
}

/** The smallest cut holding all of `cs`. */
export function union(cs: Crop[]): Crop {
  const x = Math.min(...cs.map(c => c.x))
  const y = Math.min(...cs.map(c => c.y))
  return { x, y, w: Math.max(...cs.map(c => c.x + c.w)) - x, h: Math.max(...cs.map(c => c.y + c.h)) - y }
}

/** Turn and cut the page on its scan; split a spread or join one. */
export function CutEditor({ page }: { page: PageDetail }) {
  if (!page.scan) return <EmptyState title="The scan is gone">This page’s scan is missing from the data folder, so it cannot be cut again. Import the book again to bring it back.</EmptyState>
  return <CutTool page={page} scan={page.scan} />
}

function CutTool({ page, scan }: { page: PageDetail; scan: NonNullable<PageDetail['scan']> }) {
  const navigate = useNavigate()
  const refresh = useRefresh(page)
  const spread = page.siblings.length === 2
  const start = useMemo<EditableRegion[]>(() => page.siblings.map(s => ({ id: s.side, label: SIDE_WORD[s.side], ...s.crop })), [page])
  const [angle, setAngle] = useState(page.angle)
  const [regions, setRegions] = useState<readonly EditableRegion[]>(start)

  // a new turn moves each cut with the scan, so the same part of the paper stays inside it
  const turn = (to: number) => {
    const next = wrapAngle(to)
    setRegions(rs => rs.map(r => ({ ...r, ...turnCrop(r, scan.width, scan.height, angle, next) })))
    setAngle(next)
  }

  const crops = regions.map(({ x, y, w, h }) => ({ x, y, w, h }))
  const save = useAsyncAction(async () => {
    if (spread) {
      // the same two sides come back, so this page's side is among them
      const made = await api.setScanPages(scan.id, regions.map(r => ({ side: r.id as Side, angle, crop: { x: r.x, y: r.y, w: r.w, h: r.h } })))
      await refresh()
      navigate(`/pages/${made.find(m => m.side === page.side)!.id}?tab=page`, { replace: true })
    } else {
      await api.savePage(page.id, { angle, crop: crops[0] })
      await refresh()
    }
  })
  const reshape = useAsyncAction(async () => {
    const shapes = spread
      ? [{ side: 'single' as Side, angle, crop: union(crops) }]
      : halves(crops[0]).map((crop, i) => ({ side: (i ? 'right' : 'left') as Side, angle, crop }))
    const made = await api.setScanPages(scan.id, shapes)
    await refresh()
    navigate(`/pages/${made[0].id}?tab=page`, { replace: true })
  })
  const failed = save.phase === 'error' ? save.error : reshape.phase === 'error' ? reshape.error : undefined

  const size = turnedSize(scan.width, scan.height, angle)
  const changed = angle !== page.angle || JSON.stringify(crops) !== JSON.stringify(start.map(({ x, y, w, h }) => ({ x, y, w, h })))

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <RegionEditor
        label={`Cut of ${pageName(page)} on its scan`}
        size={size}
        regions={regions}
        onChange={setRegions}
        defaults={angle === page.angle ? start : undefined}
        unit="px"
        className="max-w-xl"
      >
        <img src={withBase(paths.scanImage(scan.id, angle))} alt={`Scan ${scan.position}, turned ${format.decimal(angle)}°`} className="size-full object-cover" />
      </RegionEditor>
      <div className="grid content-start gap-4">
        <Field label="Turn" hint="Degrees counter-clockwise. The cut moves with the scan.">
          <NumberField value={angle} onChange={v => turn(v ?? 0)} min={-180} max={180} step={0.1} unit="°" />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => turn(angle + 90)}>Turn left</Button>
          <Button onClick={() => turn(angle - 90)}>Turn right</Button>
        </div>
        <p className="type-body-sm text-muted-foreground">
          {spread ? 'This scan is a spread: both pages are cut from it.' : 'Drag the corners to the page’s edges, or type the numbers under the picture.'} Saving draws the page again and reads it again.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <AsyncButton variant="default" disabled={!changed} phase={save.phase} error={save.error} onClick={() => void save.run()} labels={{ idle: spread ? 'Save cuts' : 'Save cut', pending: 'Saving…', done: 'Saved' }} />
          <AsyncButton phase={reshape.phase} error={reshape.error} onClick={() => void reshape.run()} labels={spread ? { idle: 'Make one page', pending: 'Joining…', done: 'Joined' } : { idle: 'Split into two pages', pending: 'Splitting…', done: 'Split' }} />
        </div>
        {failed && <p className="type-body-sm text-danger">{failed} The page was not changed.</p>}
      </div>
    </div>
  )
}

/** The text beside the page, typed over; the page's kind and label. */
export function TextEditor({ page }: { page: PageDetail }) {
  const refresh = useRefresh(page)
  const original = { text: page.text ?? '', label: page.label ?? '' }
  const [text, setText] = useState(original.text)
  const [kind, setKind] = useState<Kind>(page.kind)
  const [label, setLabel] = useState(original.label)
  useEffect(() => setText(original.text), [original.text])
  const unsure = page.lines.filter(l => l.conf < UNSURE)

  const save = useAsyncAction(async () => {
    await api.savePage(page.id, {
      ...(text !== original.text ? { text } : {}),
      ...(kind !== page.kind ? { kind } : {}),
      ...(label !== original.label ? { label } : {}),
    })
    await refresh()
  })
  const changed = text !== original.text || kind !== page.kind || label !== original.label

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <img src={withBase(paths.pageImage(page.id, 'preview'))} alt={`${pageName(page)} as cut`} className="w-full max-w-xl rounded-surface border border-border" />
      <div className="grid content-start gap-4">
        <Field label="Text" hint={page.text_edited ? 'Typed by hand: reading the page again keeps it.' : 'As the reader got it. What you type here is kept through every re-read.'}>
          <Textarea value={text} onChange={e => setText(e.target.value)} rows={18} spellCheck />
        </Field>
        {unsure.length > 0 && (
          <section aria-labelledby="unsure" className="grid gap-2">
            <h3 id="unsure" className="type-label">Lines the reader was unsure of</h3>
            <ul className="grid gap-1 type-body-sm">
              {unsure.map((l, i) => (
                <li key={i} className="flex items-baseline gap-2">
                  <Status tone="warning">{format.percent(l.conf / 100)}</Status>
                  <span className="font-mono">{l.text}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        <ChoiceGroup legend="This page is" name="kind" choices={kindChoices} value={kind} onChange={v => setKind(v as Kind)} />
        <Field label="Label" hint="Its printed page number or running head, used in the files’ page markers.">
          <Input value={label} onChange={e => setLabel(e.target.value)} autoComplete="off" />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <AsyncButton variant="default" disabled={!changed} phase={save.phase} error={save.error} onClick={() => void save.run()} labels={{ idle: 'Save page', pending: 'Saving…', done: 'Saved' }} />
          {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The page was not changed.</p>}
        </div>
      </div>
    </div>
  )
}

/** The pictures on the page: drag on the page to draw one, choose one to move or remove it. */
export function FigureEditor({ page }: { page: PageDetail }) {
  const refresh = useRefresh(page)
  const start = useMemo<EditableRegion[]>(() => page.figures_list.map((f, i) => ({ id: String(f.id), label: f.caption ?? `Picture ${i + 1}`, x: f.x, y: f.y, w: f.w, h: f.h })), [page])
  const [regions, setRegions] = useState<readonly EditableRegion[]>(start)
  const [chosen, setChosen] = useState<string | null>(null)
  const [drawn, setDrawn] = useState(0)

  const save = useAsyncAction(async () => {
    await api.setFigures(page.id, regions.map(({ x, y, w, h, label }) => ({ x, y, w, h, caption: /^Picture \d+$/.test(label) ? null : label })))
    await refresh()
  })
  const changed = JSON.stringify(regions) !== JSON.stringify(start)
  const remove = () => {
    setRegions(rs => rs.filter(r => r.id !== chosen))
    setChosen(null)
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <RegionEditor
        label={`Pictures on ${pageName(page)}`}
        size={[page.size.w, page.size.h]}
        regions={regions}
        onChange={setRegions}
        selectedId={chosen}
        onSelectedChange={setChosen}
        onDraw={rect => {
          const id = `new-${drawn + 1}`
          setDrawn(drawn + 1)
          setRegions(rs => [...rs, { id, label: `Picture ${rs.length + 1}`, ...rect }])
          setChosen(id)
        }}
        min={{ w: Math.round(page.size.w / 40), h: Math.round(page.size.h / 40) }}
        unit="px"
        className="max-w-xl"
      >
        <img src={withBase(paths.pageImage(page.id, 'preview'))} alt={`${pageName(page)} as cut`} className="size-full object-cover" />
      </RegionEditor>
      <div className="grid content-start gap-4">
        <p className="type-body-sm text-muted-foreground">
          {regions.length ? `${format.count(regions.length, 'picture')} on this page.` : 'No pictures on this page.'} Drag on the page to draw one; choose one to move it or change its size.
        </p>
        <Button disabled={!chosen} onClick={remove}>
          <Trash2 aria-hidden className="size-4" /> Remove the chosen picture
        </Button>
        <div className="flex flex-wrap items-center gap-3">
          <AsyncButton variant="default" disabled={!changed} phase={save.phase} error={save.error} onClick={() => void save.run()} labels={{ idle: 'Save pictures', pending: 'Saving…', done: 'Saved' }} />
          {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The pictures were not changed.</p>}
        </div>
      </div>
    </div>
  )
}
