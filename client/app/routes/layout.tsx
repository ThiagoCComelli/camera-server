import { Outlet, redirect } from "react-router";

import type { Route } from "./+types/layout";

import { getServerAddress, getToken, isApp } from "../api";

import "./layout.scss";

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const { pathname } = new URL(request.url);

  if (!isApp() && pathname === "/settings") {
    throw redirect("/");
  }

  if (
    isApp() &&
    (!getServerAddress() || !getToken()) &&
    pathname !== "/settings"
  ) {
    throw redirect("/settings");
  }

  return null;
}

export function shouldRevalidate() {
  return true;
}

export default function Layout() {
  return (
    <main className="layout">
      <Outlet />
    </main>
  );
}
