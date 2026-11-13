// The frame every screen shares: product name, side nav (a scrolling row on phones) and the main
// region, from Strata's AppShell. Nav items are React Router NavLinks, so the current screen is
// marked with aria-current. Each screen supplies its own PageHeader inside <Outlet />.
import { History, MessageSquareText, Server, Settings } from 'lucide-react'
import { Outlet } from 'react-router'
import { AppShell, type NavItem } from 'strata-react'

export const nav: NavItem[] = [
  { to: '/', label: 'Greetings', icon: MessageSquareText, end: true },
  { to: '/log', label: 'Log', icon: History },
  { to: '/system', label: 'System', icon: Server },
  { to: '/settings', label: 'Settings', icon: Settings },
]

/** The product's name. Rename it with the package (README, "Using this template"). */
export const product = 'python-app-template'

export function Layout() {
  return (
    <AppShell product={product} nav={nav}>
      <div className="grid max-w-5xl gap-8 pb-16">
        <Outlet />
      </div>
    </AppShell>
  )
}
