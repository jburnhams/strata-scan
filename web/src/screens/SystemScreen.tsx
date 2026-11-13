// The one question: "Can books be read here, and will the disk hold?" The finding answers with
// strata-models first (without it no page is read), then the data disk's state, from the same
// thresholds the meter draws; then the next questions in order:
// how full is the disk and what is it full of (a Meter with named thresholds, a CompositionBar
// with its table), what is running (Status words, never colour alone), and where to go next
// (LinkCards). The read is polled; a poll that fails keeps the last readings on screen and says
// how old they are (DataView's stale notice), so a restarting server does not blank the page.
import {
  CompositionBar,
  DataView,
  EmptyState,
  LinkCard,
  LinkCardList,
  Meter,
  PageHeader,
  Skeleton,
  StaleNotice,
  Status,
  crossedThreshold,
  format,
  useLoad,
  type MeterThreshold,
} from 'strata-react'
import { api, keys, paths, withBase, type SystemStatus } from '../api'

/** One set of thresholds for the data disk, as shares of its size, named in the app's words. */
export const diskThresholds: MeterThreshold[] = [
  { at: 0.8, tone: 'warning', label: 'Filling up' },
  { at: 0.95, tone: 'danger', label: 'Nearly full' },
]

/** "301.6 GB of 512 GB": both in the larger figure's unit, so they read as one comparison. */
export function ofSize(used: number, size: number) {
  const unit = format.byteUnit(size)
  return `${format.bytes(used, unit)} of ${format.bytes(size, unit)}`
}

/** The disk's usable size, as `df` counts it: what is used plus what is free. Space the system
 *  reserves for itself is neither, so measuring against `total` would never show a full disk. */
export const usable = (disk: SystemStatus['disk']) => disk.used + disk.free

/** The page's finding, from the disk the data folder is on. When the latest poll failed, it says so first and reads the disk as old news. */
export function describeDisk({ disk, models }: SystemStatus, answering = true): string {
  const share = disk.used / usable(disk)
  const crossed = crossedThreshold(share, diskThresholds)
  const left = `${format.bytes(disk.free)} free`
  if (!answering) return `The server is not answering. When last read, the data disk was ${format.percent(share)} full, with ${left}.`
  if (!models.available) return `Pages cannot be read: strata-models is not answering at ${models.url}. Books can still be imported and cut. The data disk is ${format.percent(share)} full.`
  if (!models.ocr_model) return `Pages cannot be read: strata-models at ${models.url} has no ocr role. The data disk is ${format.percent(share)} full.`
  if (!crossed) return `Everything is running. The data disk is ${format.percent(share)} full, with ${left}.`
  return crossed.tone === 'danger'
    ? `The data disk is ${format.percent(share)} full, with ${left}. Free space or move the data folder in Settings before books stop importing (each scanned book takes a few hundred MB).`
    : `The data disk is ${format.percent(share)} full, with ${left}. Nothing needs doing yet.`
}

function SystemSkeleton() {
  return (
    <div className="grid gap-10" aria-hidden>
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-24 w-full max-w-xl" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map(i => <Skeleton key={i} className="h-28" />)}
      </div>
    </div>
  )
}

export function SystemScreen() {
  const load = useLoad({ queryKey: keys.system, queryFn: api.system, refetchInterval: 60_000 })
  // Readings kept from an earlier poll are still shown, but the server is not answering now.
  const answering = !(load.status === 'ready' && load.stale)

  return (
    <>
      <PageHeader
        title="System"
        scope="This computer, checked every minute"
        finding={load.status === 'ready' ? { text: describeDisk(load.data, answering) } : undefined}
      />
      <DataView
        state={load}
        isEmpty={() => false}
        skeleton={<SystemSkeleton />}
        staleNotice={stale => <StaleNotice stale={stale} shown={when => `These readings are from ${when}.`} />}
        empty={<EmptyState title="No readings">The server sent nothing to report.</EmptyState>}
      >
        {s => (
          <div className="grid gap-10">
            <section aria-labelledby="disk" className="grid max-w-xl gap-3">
              <h2 id="disk" className="type-heading">Data disk</h2>
              <p className="type-body-sm text-muted-foreground">
                The data folder, <span className="font-mono text-foreground">{s.data_dir}</span>, is on this disk.
              </p>
              <Meter label="Data disk space used" value={s.disk.used} max={usable(s.disk)} thresholds={diskThresholds} detail={ofSize(s.disk.used, usable(s.disk))} />
              <CompositionBar
                label={`${format.bytes(usable(s.disk))} in all`}
                parts={[
                  { key: 'app', label: 'This app’s data', value: s.data_bytes },
                  { key: 'other', label: 'Everything else', value: Math.max(0, s.disk.used - s.data_bytes) },
                ]}
                total={usable(s.disk)}
                restLabel="Free"
                formatValue={v => format.bytes(v)}
              />
            </section>

            <section aria-labelledby="running" className="grid gap-3">
              <h2 id="running" className="type-heading">Running</h2>
              <dl className="grid max-w-xl gap-2 type-body-sm">
                {([
                  ['Server', <>{answering ? <Status tone="success">Answering</Status> : <Status tone="danger">Not answering</Status>} <span className="ml-2 tabular-nums">version {s.version}</span></>],
                  ['Python', <span className="tabular-nums">{s.python}</span>],
                  ['Platform', s.platform],
                  ['Reading', s.models.available && s.models.ocr_model ? <><Status tone="success">Ready</Status> <span className="ml-2">{s.models.ocr_model} on strata-models</span></> : <Status tone="danger">{s.models.available ? 'No ocr role' : 'Not answering'}</Status>],
                ] as const).map(([term, value]) => (
                  <div key={term} className="flex gap-6">
                    <dt className="w-28 shrink-0 text-muted-foreground">{term}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section aria-labelledby="next" className="grid gap-3">
              <h2 id="next" className="type-heading">Go to</h2>
              <LinkCardList label="Places to go from here">
                <LinkCard to="/settings" title="Settings" description="Move the data folder, set how many pages are worked on at once, or choose light or dark." />
                <LinkCard href={withBase('/api/docs')} title="API reference" description="Every endpoint the server answers, with a form to try each one." />
                <LinkCard href={withBase(paths.health)} title="Health check" description="The JSON a monitor polls to see that the server is up." />
              </LinkCardList>
            </section>
          </div>
        )}
      </DataView>
    </>
  )
}
