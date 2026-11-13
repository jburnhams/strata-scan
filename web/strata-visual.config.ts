// The visual suite, run by strata-react's own runner (`strata-visual`, from strata-react/visual):
// Playwright Chromium screenshots, light and dark, compared with committed baselines in
// tests/visual/baselines/ by pixelmatch. Two targets:
//
// - storybook: every story of the built Storybook (each screen in each server state);
// - app: the production build served as the Python server would (history fallback), each route at
//   a wide and a phone viewport, with every request answered in Node by the same MSW handlers the
//   jsdom tests use. Route states here are the ones a story cannot reach without a click: a removal
//   with its Undo bar, the bulk bar, a field's error. None of them writes to the mock server (the
//   removal is still inside its undo window when the shot is taken), so shots cannot affect each other.
//
// `npm run test:visual` builds both and compares; `npm run test:visual:update` writes new
// baselines. Look at a diff in tests/visual/output/ before accepting it.
import { defineVisualConfig } from 'strata-react/visual'
import { handlers } from './src/mocks/handlers'

export default defineVisualConfig({
  storybook: 'storybook-static',
  app: {
    dir: 'dist-visual',
    handlers,
    viewports: ['wide', 'phone'],
    routes: [
      {
        name: 'greetings',
        path: '/',
        states: {
          ready: [],
          removed: {
            setup: async page => {
              await page.getByRole('button', { name: 'Remove Welcome, Frances!' }).click()
              await page.getByRole('button', { name: 'Undo' }).waitFor()
            },
          },
          selected: {
            setup: async page => {
              await page.getByRole('checkbox', { name: 'Select Welcome, Frances!' }).click()
              await page.getByRole('checkbox', { name: 'Select Hello, Ken!' }).click()
              await page.getByRole('button', { name: 'Remove 2' }).waitFor()
            },
          },
          invalid: {
            setup: async page => {
              await page.getByRole('textbox', { name: 'Name' }).fill('x'.repeat(121))
              await page.getByRole('button', { name: 'Send greeting' }).click()
              await page.getByText('Use at most 120 characters').waitFor()
            },
          },
        },
      },
      // The log is shot with one page. A long log is not screenshotted: the list asks for the next page on
      // its own as its end comes near, and focus and scroll move as pages land, so which rows are in view
      // depends on timing (two machines disagreed). Its paging is tested in jsdom (tests/integration/LogScreen).
      { name: 'log', path: '/log' },
      { name: 'system', path: '/system' },
      { name: 'settings', path: '/settings', states: { general: [], appearance: { path: '/settings?tab=appearance' } } },
    ],
  },
})
