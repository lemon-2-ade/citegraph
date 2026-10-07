import { Link } from "react-router-dom";

import { Empty } from "../components/StateViews";

export function NotFoundPage() {
  return (
    <Empty title="Page not found">
      <Link to="/">Back to the dashboard</Link>
    </Empty>
  );
}
