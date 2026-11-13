import type { Meta, StoryObj } from '@storybook/react-vite'
import { pageError, pageLoading, pageNoScan, pageSpread } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Page',
  render: () => <AppAt route="/pages/114" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** Page 14 of the 1874 book: its cut on the scan. */
export const Cut: Story = {}
/** The text beside the page, with the line the reader was unsure of. */
export const Text: Story = { render: () => <AppAt route="/pages/114?tab=text" /> }
/** An engraving with the picture found on it. */
export const Pictures: Story = { render: () => <AppAt route="/pages/109?tab=pictures" /> }
/** A cover the page finder was unsure of. */
export const Unsure: Story = { render: () => <AppAt route="/pages/101" /> }
/** A spread split by hand: both cuts on the one scan. */
export const Spread: Story = { beforeEach: ({ msw }) => msw.use(pageSpread) }
export const ScanGone: Story = { beforeEach: ({ msw }) => msw.use(pageNoScan) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(pageLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(pageError) }
export const Phone: Story = { tags: ['visual-phone'] }
