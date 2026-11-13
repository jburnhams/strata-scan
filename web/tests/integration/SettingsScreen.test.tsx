import { describe, expect, it } from 'vitest'
import { saveSettingsFails, settingsError } from '../../src/mocks/handlers'
import { openApp, screen, waitFor } from '../utils/render'
import { mock, server } from '../utils/server'

describe('Settings', () => {
  it('starts the form from what the server holds and saves a change', async () => {
    const { user } = openApp('/settings')
    const workers = await screen.findByRole('textbox', { name: 'Pages at once' })
    expect(workers).toHaveValue('4')
    expect(screen.getByRole('textbox', { name: 'Data folder' })).toHaveValue('/home/ada/scans')
    expect(screen.getByRole('textbox', { name: 'Highest resolution' })).toHaveValue('600')
    await user.clear(workers)
    await user.type(workers, '2')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('Saved', { selector: '[role=status]' })).toBeInTheDocument()
    expect(mock.settings.workers).toBe('2')
  })

  it('says under each field what is wrong, and saves nothing', async () => {
    const { user } = openApp('/settings')
    const dpi = await screen.findByRole('textbox', { name: 'Highest resolution' })
    const workers = screen.getByRole('textbox', { name: 'Pages at once' })
    const folder = screen.getByRole('textbox', { name: 'Data folder' })
    await user.clear(dpi)
    await user.type(dpi, '5000')
    await user.clear(workers)
    await user.clear(folder)
    await user.type(folder, 'relative/path')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(dpi).toHaveAccessibleDescription(/Use a whole number from 72 to 1200/)
    expect(workers).toHaveAccessibleDescription(/Use a whole number from 1 to 32/)
    expect(folder).toHaveAccessibleDescription(/Use a full path from the top of the disk/)
    expect(mock.settings.max_dpi).toBe('600')
  })

  it('says what happened when saving fails', async () => {
    server.use(saveSettingsFails)
    const { user } = openApp('/settings')
    await user.click(await screen.findByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('The server could not answer (503). The settings were not changed.')).toBeInTheDocument()
  })

  it('keeps the tab in the URL, and the colour scheme choice changes the page', async () => {
    const { user, router } = openApp('/settings')
    await user.click(screen.getByRole('tab', { name: 'Appearance' }))
    expect(router.state.location.search).toBe('?tab=appearance')
    await user.click(screen.getByRole('radio', { name: 'Dark' }))
    await waitFor(() => expect(document.documentElement).toHaveClass('dark'))
  })

  it('opens on a tab from a link', () => {
    openApp('/settings?tab=appearance')
    expect(screen.getByRole('tab', { name: 'Appearance' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('radiogroup', { name: 'Colour scheme' })).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(settingsError)
    openApp('/settings')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})
