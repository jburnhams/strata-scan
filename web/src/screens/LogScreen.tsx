// The one question: "What went out, and when, all the way back?" A log grows without end, so it
// is read a page at a time, the Strata way: useInfiniteLoad over a cursor API (`after` = the id of
// the last greeting held, never an offset, so a greeting removed between pages cannot make the
// next page skip one) -> InfiniteList, which loads the next page as the end comes near, shows a
// skeleton for it, a Try again row when it fails and a Show more button for the keyboard. Its
// first page's loading, error and empty states are DataView's, so they read like every other read.
import { Link } from 'react-router'
import { Button, EmptyState, InfiniteList, PageHeader, Skeleton, format, useInfiniteLoad } from 'strata-react'
import { api, keys, type MessagePage, type MessageRecord } from '../api'

/** Greetings per page. Small enough that the first page is quick, large enough to fill a screen. */
export const PAGE_SIZE = 20

function LogRow({ m }: { m: MessageRecord }) {
  return (
    <div className="flex items-baseline gap-4 py-2 type-body-sm">
      <span className="w-40 shrink-0 text-muted-foreground tabular-nums">{format.dateTime(m.created)}</span>
      <span className="min-w-0 flex-1 truncate">{m.message}</span>
      <span className="hidden w-16 shrink-0 text-right text-muted-foreground tabular-nums sm:block">#{m.id}</span>
    </div>
  )
}

/** Mirrors LogRow: the same heights and column widths, so nothing moves when the rows arrive. */
function RowsSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="grid">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 py-3">
          <Skeleton className="h-3.5 w-40" />
          <Skeleton className="h-3.5 flex-1" />
          <Skeleton className="hidden h-3.5 w-16 sm:block" />
        </div>
      ))}
    </div>
  )
}

export function LogScreen() {
  const log = useInfiniteLoad<MessageRecord, MessagePage, number>({
    queryKey: keys.log,
    queryFn: ({ cursor, signal }) => api.page(cursor, PAGE_SIZE, signal),
    items: page => page.messages,
    itemKey: m => String(m.id),
    cursorAfter: m => m.id,
    hasMore: page => page.has_more,
  })

  return (
    <>
      <PageHeader title="Log" scope="Every greeting kept, newest first" />
      <InfiniteList
        state={log}
        label="Greeting log, newest first"
        moreLabel="Show older greetings"
        skeleton={<RowsSkeleton rows={8} />}
        moreSkeleton={<RowsSkeleton />}
        empty={
          <EmptyState title="The log is empty" action={<Button asChild variant="default"><Link to="/">Send a greeting</Link></Button>}>
            Each greeting you send is logged here with the time it went out.
          </EmptyState>
        }
        end="That is every greeting kept."
        estimateSize={37}
      >
        {m => <LogRow m={m} />}
      </InfiniteList>
    </>
  )
}
