import { Outlet, redirect } from "react-router";

import type { Route } from "./+types/layout";

import { Capacitor } from "@capacitor/core";

import { getServerAddress, getToken, isRemote } from "../api";

import "./layout.scss";

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  const { pathname } = new URL(request.url);
  const remote = isRemote();

  if (!remote && pathname === "/settings") {
    throw redirect("/");
  }

  const configured = Capacitor.isNativePlatform()
    ? !!getServerAddress()
    : !!getToken();
  if (remote && !configured && pathname !== "/settings") {
    throw redirect("/settings");
  }

  return { isRemote: remote };
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
