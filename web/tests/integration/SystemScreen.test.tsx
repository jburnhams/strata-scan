import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { createQueryClient } from 'strata-react'
import { keys } from '../../src/api'
import { systemStatus } from '../../src/mocks/fixtures'
import { systemError, systemNearlyFull, systemNoModels } from '../../src/mocks/handlers'
import { openApp, screen } from '../utils/render'
import { server } from '../utils/server'

describe('System', () => {
  it('answers with the data disk and shows what fills it', async () => {
    openApp('/system')
    expect(await screen.findByText(/^Everything is running\. The data disk is 59% full/)).toBeInTheDocument()
    const meter = screen.getByRole('meter', { name: 'Data disk space used' })
    expect(meter).toHaveAttribute('aria-valuenow', String(301.6e9))
    expect(screen.getByRole('table', { name: /in all/ })).toHaveTextContent('This app’s data')
    expect(screen.getByText('Answering')).toBeInTheDocument()
    expect(screen.getByText('/home/ada/scans')).toBeInTheDocument()
    expect(screen.getByText('tesseract-eng on strata-models')).toBeInTheDocument()
  })

  it('names the threshold a nearly full disk has crossed, and what to do', async () => {
    server.use(systemNearlyFull)
    openApp('/system')
    expect(await screen.findByText(/Free space or move the data folder in Settings/)).toBeInTheDocument()
    expect(screen.getByText('Nearly full')).toBeInTheDocument()
  })

  it('links to settings in the app and to the API outside it', async () => {
    openApp('/system')
    expect(await screen.findByRole('link', { name: /^Settings/ , description: /Move the data folder/ })).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('link', { name: /API reference/ })).toHaveAttribute('href', '/api/docs')
  })

  it('says first that pages cannot be read when strata-models is away', async () => {
    server.use(systemNoModels)
    openApp('/system')
    expect(await screen.findByText(/^Pages cannot be read: strata-models is not answering/)).toBeInTheDocument()
    expect(screen.getByText('Not answering')).toBeInTheDocument()
  })

  it('says when strata-models answers without an ocr role', async () => {
    server.use(http.get('*/api/system', () => HttpResponse.json({ ...systemStatus, models: { ...systemStatus.models, ocr_model: null } })))
    openApp('/system')
    expect(await screen.findByText('No ocr role')).toBeInTheDocument()
  })

  it('says the server could not answer', async () => {
    server.use(systemError)
    openApp('/system')
    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not answer (503)')
  })
})

describe('System, when a poll fails after a good one', () => {
  it('keeps the last readings and says how old they are', async () => {
    const client = createQueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(keys.system, systemStatus, { updatedAt: Date.UTC(2026, 10, 9, 8, 50) })
    server.use(systemError)
    openApp('/system', { client })
    expect(await screen.findByText(/These readings are from .*08:50\./)).toBeInTheDocument()
    expect(screen.getByText('Not answering')).toBeInTheDocument()
    expect(screen.getByRole('meter', { name: 'Data disk space used' })).toBeInTheDocument()
  })
})
