import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import type { Route } from "./+types/settings";

import { Page } from "../components/page";

import "./settings.scss";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Settings · Camera Server" }];
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>({
    serverAddress: "",
    token: "",
  });
  const [saved, setSaved] = useState(false);

  function loadSettings() {
    const serverAddress = localStorage.getItem("serverAddress") || "";
    const token = localStorage.getItem("token") || "";

    setSettings({ serverAddress, token });
  }

  const handleChange = (e: any) => {
    setSettings((state: any) => ({
      ...state,
      [e.target.dataset.field]: e.target.value,
    }));
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    localStorage.setItem("serverAddress", settings.serverAddress);
    localStorage.setItem("token", settings.token);

    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  useEffect(() => {
    loadSettings();
  }, []);

  return (
    <Page
      section="Settings"
      actions={
        <Link to="/" className="link">
          ← Back to live
        </Link>
      }
    >
      <form className="settings" onSubmit={onSubmit}>
        <label className="field">
          <span className="field-label">Server address</span>
          <input
            data-field="serverAddress"
            type="text"
            placeholder="189.73.174.41:8000"
            defaultValue={settings.serverAddress}
            onChange={handleChange}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="field-hint">
            IP address the client sends its requests to. Only necessary when the
            user is outside the local network.
          </span>
        </label>

        <label className="field">
          <span className="field-label">Access key</span>
          <input
            data-field="token"
            type="text"
            defaultValue={settings.token}
            onChange={handleChange}
            autoComplete="off"
          />
          <span className="field-hint">
            Sent with every request to the server. Only necessary when the user
            is outside the local network.
          </span>
        </label>

        <div className="settings-actions">
          {saved && <span className="settings-saved">Saved</span>}
          <button type="submit">Save</button>
        </div>
      </form>
    </Page>
  );
}
