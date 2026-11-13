// The app's route tree, in its own module so the app (main.tsx), the jsdom tests (renderRoutes from
// strata-react/testing) and the stories build their routers from the same objects: a test that
// hand-copied the tree would keep passing after the app's routes changed.
//
// Routes are real paths (/books/1?tab=files, /pages/114?tab=text), not #hashes: the server answers
// every page path with the app (src/stratascan/server/app.py), so a reload or a shared link opens
// that screen, and anything a person would link to (sort, tab) lives in the URL's search.
import type { RouteObject } from 'react-router'
import { Layout } from './screens/Layout'
import { BooksScreen } from './screens/BooksScreen'
import { BookScreen } from './screens/BookScreen'
import { PageScreen } from './screens/PageScreen'
import { SystemScreen } from './screens/SystemScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { NotFoundScreen } from './screens/NotFoundScreen'

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <BooksScreen /> },
      { path: 'books/:bookId', element: <BookScreen /> },
      { path: 'pages/:pageId', element: <PageScreen /> },
      { path: 'system', element: <SystemScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
      { path: '*', element: <NotFoundScreen /> },
    ],
  },
]
