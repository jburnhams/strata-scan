import type { Meta, StoryObj } from '@storybook/react-vite'
import { compareAllGood, compareError, compareLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Compare',
  render: () => <AppAt route="/books/1/compare" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** The 1874 book: the three pages to look at, the first one's scan and finished page side by side. */
export const ToLookAt: Story = {}
/** Every page, as spreads, one above the other. */
export const SpreadsAboveAndBelow: Story = { render: () => <AppAt route="/books/1/compare?show=all&layout=spread&mode=stack&page=116" /> }
/** The scan laid over the finished page with a swipe. */
export const Swipe: Story = { render: () => <AppAt route="/books/1/compare?mode=swipe" /> }
/** Every finished page matches its scan: nothing to look at, so every page is listed. */
export const AllMatch: Story = { beforeEach: ({ msw }) => msw.use(compareAllGood) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(compareLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(compareError) }
export const Phone: Story = { tags: ['visual-phone'] }
