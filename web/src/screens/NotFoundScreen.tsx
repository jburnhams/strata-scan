// A path the app has no screen for, such as an old bookmark. It says so and offers the way back,
// rather than showing an empty frame.
import { Link, useLocation } from 'react-router'
import { EmptyState, PageHeader, buttonVariants } from 'strata-react'

export function NotFoundScreen() {
  const { pathname } = useLocation()
  return (
    <>
      <PageHeader title="No such page" />
      <EmptyState title={`There is nothing at ${pathname}`} action={<Link className={buttonVariants({ variant: 'default' })} to="/">Go to the books</Link>}>
        The link may be from an older version of the app. Every screen is in the menu.
      </EmptyState>
    </>
  )
}
