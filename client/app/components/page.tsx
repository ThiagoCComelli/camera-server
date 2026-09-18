import type { ReactNode } from "react";

import { PageHeader } from "./page-header";

import "./page.scss";

export function Page({
  section,
  actions,
  children,
}: {
  section?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="page">
      <PageHeader section={section} actions={actions} />
      <div className="page-body">{children}</div>
    </div>
  );
}
