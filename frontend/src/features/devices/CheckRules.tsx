import React from "react";
import {
  api,
  type ApiError,
  type CheckRule,
  type MonitorCheck,
  type Page,
} from "../../api";

function message(cause: unknown): string {
  return (cause as ApiError)?.message || "The check rule request failed.";
}

function maintenanceInput(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function RuleItem({ rule, onSaved }: { rule: CheckRule; onSaved: () => void }) {
  const [enabled, setEnabled] = React.useState(rule.enabled);
  const [threshold, setThreshold] = React.useState(rule.failure_threshold);
  const [quietStart, setQuietStart] = React.useState(
    rule.quiet_start_hour?.toString() ?? "",
  );
  const [quietEnd, setQuietEnd] = React.useState(
    rule.quiet_end_hour?.toString() ?? "",
  );
  const [maintenance, setMaintenance] = React.useState(
    maintenanceInput(rule.maintenance_until),
  );
  const [history, setHistory] = React.useState<MonitorCheck[] | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api<CheckRule>(`/check-rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          enabled,
          failure_threshold: threshold,
          quiet_start_hour: quietStart === "" ? null : Number(quietStart),
          quiet_end_hour: quietEnd === "" ? null : Number(quietEnd),
          maintenance_until: maintenance
            ? new Date(maintenance).toISOString()
            : null,
        }),
      });
      onSaved();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory() {
    setError("");
    try {
      const page = await api<Page<MonitorCheck>>(
        `/check-rules/${rule.id}/history?limit=20`,
      );
      setHistory(page.items);
    } catch (cause) {
      setError(message(cause));
    }
  }

  return (
    <li>
      <strong>TCP {rule.port}</strong>
      <form onSubmit={save}>
        <label className="check-row">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <span>Enabled</span>
        </label>
        <label>
          Consecutive misses
          <input
            type="number"
            min={2}
            max={10}
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
          />
        </label>
        <div className="settings-fields">
          <label>
            Quiet from (UTC hour)
            <input
              type="number"
              min={0}
              max={23}
              value={quietStart}
              onChange={(event) => setQuietStart(event.target.value)}
            />
          </label>
          <label>
            Quiet until (UTC hour)
            <input
              type="number"
              min={0}
              max={23}
              value={quietEnd}
              onChange={(event) => setQuietEnd(event.target.value)}
            />
          </label>
          <label>
            Maintenance ends (local time)
            <input
              type="datetime-local"
              value={maintenance}
              onChange={(event) => setMaintenance(event.target.value)}
            />
          </label>
        </div>
        <button className="secondary" disabled={busy}>
          {busy ? "Saving…" : "Save rule"}
        </button>
      </form>
      <button className="text-button" onClick={loadHistory}>
        Show check history
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {history &&
        (history.length ? (
          <ul className="evidence-list">
            {history.map((check) => (
              <li key={check.id}>
                <span>
                  {check.state}{" "}
                  {check.suppressed ? "· quiet or maintenance" : ""}
                </span>
                <small>
                  {new Date(check.observed_at).toLocaleString()} · Scan #
                  {check.scan_run_id}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">No checks yet. Run an approved scan.</p>
        ))}
    </li>
  );
}

export function CheckRules({ deviceId }: { deviceId: number }) {
  const [rules, setRules] = React.useState<CheckRule[]>([]);
  const [port, setPort] = React.useState(80);
  const [threshold, setThreshold] = React.useState(2);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const reload = React.useCallback(() => {
    api<CheckRule[]>(`/devices/${deviceId}/check-rules`)
      .then(setRules)
      .catch((cause) => setError(message(cause)));
  }, [deviceId]);
  React.useEffect(reload, [reload]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api<CheckRule>(`/devices/${deviceId}/check-rules`, {
        method: "POST",
        body: JSON.stringify({ port, failure_threshold: threshold }),
      });
      setNotice(`TCP ${port} rule added. It uses approved scan results.`);
      reload();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="history-section">
      <h3>Service check rules</h3>
      <p className="muted">
        Each rule evaluates an approved TCP port during normal scans. A missed
        check can also mean a firewall or sleeping host. Quiet hours and
        maintenance suppress new alerts while preserving check history.
      </p>
      <form onSubmit={add} className="settings-fields">
        <label>
          TCP port
          <input
            type="number"
            min={1}
            max={65535}
            value={port}
            onChange={(event) => setPort(Number(event.target.value))}
          />
        </label>
        <label>
          Consecutive misses
          <input
            type="number"
            min={2}
            max={10}
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
          />
        </label>
        <button className="secondary" disabled={busy}>
          {busy ? "Adding…" : "Add check rule"}
        </button>
      </form>
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
      {rules.length ? (
        <ul className="evidence-list">
          {rules.map((rule) => (
            <RuleItem key={rule.id} rule={rule} onSaved={reload} />
          ))}
        </ul>
      ) : (
        <p className="empty">No service check rules for this device.</p>
      )}
    </section>
  );
}
