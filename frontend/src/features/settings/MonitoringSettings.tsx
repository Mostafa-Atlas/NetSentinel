import React from "react";
import {
  api,
  type ApiError,
  type MonitoringSettings as Settings,
} from "../../api";

export function MonitoringSettings() {
  const [settings, setSettings] = React.useState<Settings | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  React.useEffect(() => {
    api<Settings>("/settings")
      .then(setSettings)
      .catch((cause) =>
        setError(
          (cause as ApiError)?.message || "Unable to load monitoring settings.",
        ),
      )
      .finally(() => setLoading(false));
  }, []);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setSettings(
        await api<Settings>("/settings", {
          method: "PATCH",
          body: JSON.stringify(settings),
        }),
      );
      setNotice("Monitoring settings saved.");
    } catch (cause) {
      setError(
        (cause as ApiError)?.message || "Unable to save monitoring settings.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="panel scan-panel">
      <h2>Monitoring</h2>
      {loading ? (
        <p role="status">Loading monitoring settings…</p>
      ) : (
        settings && (
          <form onSubmit={save}>
            <label className="check-row">
              <input
                type="checkbox"
                checked={settings.schedule_enabled}
                onChange={(event) =>
                  setSettings({
                    ...settings,
                    schedule_enabled: event.target.checked,
                  })
                }
              />
              <span>
                Run discovery automatically on approved enabled ranges
              </span>
            </label>
            <p className="helper">
              Scheduling is off by default. Enabling it sends the configured
              bounded probes at the interval below.
            </p>
            <div className="settings-fields">
              <label htmlFor="interval-minutes">
                Minutes between scans
                <input
                  id="interval-minutes"
                  type="number"
                  min={15}
                  max={1440}
                  value={settings.interval_minutes}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      interval_minutes: Number(event.target.value),
                    })
                  }
                />
              </label>
              <label htmlFor="offline-threshold">
                Missed scans before offline
                <input
                  id="offline-threshold"
                  type="number"
                  min={2}
                  max={10}
                  value={settings.offline_threshold}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      offline_threshold: Number(event.target.value),
                    })
                  }
                />
              </label>
              <label htmlFor="retention-days">
                History retention (days)
                <input
                  id="retention-days"
                  type="number"
                  min={7}
                  max={365}
                  value={settings.retention_days}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      retention_days: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            {notice && (
              <p className="success" role="status">
                {notice}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? "Saving…" : "Save monitoring settings"}
            </button>
          </form>
        )
      )}
      {!loading && !settings && error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
