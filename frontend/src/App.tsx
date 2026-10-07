import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PaperDetailPage } from "./pages/PaperDetailPage";
import { PapersPage } from "./pages/PapersPage";
import { Loading } from "./components/StateViews";

const GraphPage = lazy(() => import("./pages/GraphPage").then((m) => ({ default: m.GraphPage })));

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route
          path="graph"
          element={
            <Suspense fallback={<Loading label="Loading graph explorer" />}>
              <GraphPage />
            </Suspense>
          }
        />
        <Route path="papers" element={<PapersPage />} />
        <Route path="papers/:paperId" element={<PaperDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
