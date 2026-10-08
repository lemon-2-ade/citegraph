import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { AuthorDetailPage } from "./pages/AuthorDetailPage";
import { AuthorsPage } from "./pages/AuthorsPage";
import { CommunitiesPage } from "./pages/CommunitiesPage";
import { CommunityDetailPage } from "./pages/CommunityDetailPage";
import { SearchPage } from "./pages/SearchPage";
import { TopicDetailPage } from "./pages/TopicDetailPage";
import { TopicsPage } from "./pages/TopicsPage";
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
        <Route path="search" element={<SearchPage />} />
        <Route path="authors" element={<AuthorsPage />} />
        <Route path="authors/:authorId" element={<AuthorDetailPage />} />
        <Route path="topics" element={<TopicsPage />} />
        <Route path="topics/:topicId" element={<TopicDetailPage />} />
        <Route path="communities" element={<CommunitiesPage />} />
        <Route path="communities/:communityId" element={<CommunityDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
