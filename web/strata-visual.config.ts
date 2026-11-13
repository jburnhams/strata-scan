// The visual suite, run by strata-react's own runner (`strata-visual`, from strata-react/visual):
// Playwright Chromium screenshots, light and dark, compared with committed baselines in
// tests/visual/baselines/ by pixelmatch. Two targets:
//
// - storybook: every story of the built Storybook (each screen in each server state);
// - app: the production build served as the Python server would (history fallback), each route at
//   a wide and a phone viewport, with every request answered in Node by the same MSW handlers the
//   jsdom tests use. Route states here are a tab or a server state, plus one a story cannot reach
//   without a click (a field's error). None writes to the mock server, which the runner never
//   resets, so shots cannot affect each other.
//
// `npm run test:visual` builds both and compares; `npm run test:visual:update` writes new
// baselines. Look at a diff in tests/visual/output/ before accepting it.
import { defineVisualConfig } from 'strata-react/visual'
import { handlers, pageSpread } from './src/mocks/handlers'

export default defineVisualConfig({
  storybook: 'storybook-static',
  app: {
    dir: 'dist-visual',
    handlers,
    viewports: ['wide', 'phone'],
    routes: [
      { name: 'books', path: '/', states: { shelf: [], invalid: { setup: async page => {
        await page.getByRole('button', { name: 'Add book' }).click()
        await page.getByText('Enter the full path of a PDF').waitFor()
      } } } },
      { name: 'book', path: '/books/1', states: { pages: [], pictures: { path: '/books/1?tab=pictures' }, files: { path: '/books/1?tab=files' } } },
      {
        name: 'page',
        path: '/pages/114',
        states: {
          cut: [],
          text: { path: '/pages/114?tab=text' },
          pictures: { path: '/pages/109?tab=pictures' },
          spread: [pageSpread],
        },
      },
      { name: 'system', path: '/system' },
      { name: 'settings', path: '/settings', states: { general: [], appearance: { path: '/settings?tab=appearance' } } },
    ],
  },
})
