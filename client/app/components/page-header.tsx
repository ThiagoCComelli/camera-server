import type { ReactNode } from "react";

import "./page-header.scss";

const CAMERA = { name: "Front Door Camera", id: "CAM-01" };

export function PageHeader({
  section,
  actions,
}: {
  section?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <h1 className="page-header-title">
        {CAMERA.name}
        {section && <span className="page-header-section">/ {section}</span>}
      </h1>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
