import { Outlet } from "react-router";

import "./layout.scss";

export default function Layout() {
  return (
    <main className="layout">
      <Outlet />
    </main>
  );
}
