import type { Meta, StoryObj } from '@storybook/react-vite'
import { bookFailed, booksEmpty, booksError, booksLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Books',
  render: () => <AppAt route="/" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Shelf: Story = {}
export const Empty: Story = { beforeEach: ({ msw }) => msw.use(booksEmpty) }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(booksLoading) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(booksError) }
export const Phone: Story = { tags: ['visual-phone'] }

/** One book (the 1828 Collier) stopped: strata-models went away part way through reading. */
export const Stopped: Story = { render: () => <AppAt route="/books/2" />, beforeEach: ({ msw }) => msw.use(bookFailed) }
