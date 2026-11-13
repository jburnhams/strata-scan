// The app's route tree, in its own module so the app (main.tsx), the jsdom tests (renderRoutes from
// strata-react/testing) and the stories build their routers from the same objects: a test that
// hand-copied the tree would keep passing after the app's routes changed.
//
// Routes are real paths (/log, /settings?tab=appearance), not #hashes: the server answers every
// page path with the app (src/app/server/app.py), so a reload or a shared link opens that screen,
// and anything a person would link to (sort, tab, page) lives in the URL's search.
import type { RouteObject } from 'react-router'
import { Layout } from './screens/Layout'
import { GreetingsScreen } from './screens/GreetingsScreen'
import { LogScreen } from './screens/LogScreen'
import { SystemScreen } from './screens/SystemScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { NotFoundScreen } from './screens/NotFoundScreen'

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <GreetingsScreen /> },
      { path: 'log', element: <LogScreen /> },
      { path: 'system', element: <SystemScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
      { path: '*', element: <NotFoundScreen /> },
    ],
  },
]
