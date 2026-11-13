import type { Meta, StoryObj } from '@storybook/react-vite'
import { logEmpty, logError, logLaterPageError, logLoading, logLong } from '../src/mocks/handlers'
import { AppAt } from './app-at'

const meta = {
  title: 'Screens/Log',
  render: () => <AppAt route="/log" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
/** 75 greetings, 20 to a page: scroll the list to load the next. Not screenshotted: when the next page lands depends on timing. */
export const Long: Story = { beforeEach: ({ msw }) => msw.use(logLong), tags: ['no-visual'] }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(logLoading) }
export const Empty: Story = { beforeEach: ({ msw }) => msw.use(logEmpty) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(logError) }
/** The first page arrives and every later one fails: scroll or press Show more to see the Try again row. */
export const LaterPageFails: Story = { beforeEach: ({ msw }) => msw.use(logLaterPageError), tags: ['no-visual'] }
