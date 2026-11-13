import type { Meta, StoryObj } from '@storybook/react-vite'
import { addFails, messagesEmpty, messagesError, messagesLoading } from '../src/mocks/handlers'
import { AppAt } from './app-at'

// The Greetings screen in each server state. Interactions (a removal with its Undo bar, the bulk
// bar, a field error) are screenshotted in route mode instead (strata-visual.config.ts), where a
// click is a setup step.
const meta = {
  title: 'Screens/Greetings',
  render: () => <AppAt route="/" />,
  tags: ['visual-wide'],
} satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

export const Ready: Story = {}
export const SortedByName: Story = { render: () => <AppAt route="/?sort=name.asc" /> }
export const Loading: Story = { beforeEach: ({ msw }) => msw.use(messagesLoading) }
export const Empty: Story = { beforeEach: ({ msw }) => msw.use(messagesEmpty) }
export const ServerError: Story = { beforeEach: ({ msw }) => msw.use(messagesError) }
/** Sending fails; try it with the button. Not screenshotted, since the state needs the click. */
export const SendingFails: Story = { beforeEach: ({ msw }) => msw.use(addFails), tags: ['no-visual'] }
export const Phone: Story = { tags: ['visual-phone'] }
