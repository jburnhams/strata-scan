import type { Meta, StoryObj } from '@storybook/react-vite'
import { bookError, pagesLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Book',
  render: () => <AppAt route="/books/1" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

/** The 1874 book, read: its pages in reading order, the unsure ones marked. */
export const Pages: Story = {}
export const Pictures: Story = { render: () => <AppAt route="/books/1?tab=pictures" /> }
export const Files: Story = { render: () => <AppAt route="/books/1?tab=files" /> }
/** The 1828 book while it is being read. */
export const Reading: Story = { render: () => <AppAt route="/books/2" /> }
export const PagesLoading: Story = { beforeEach: ({ msw }) => msw.use(pagesLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(bookError) }
export const Phone: Story = { tags: ['visual-phone'] }
