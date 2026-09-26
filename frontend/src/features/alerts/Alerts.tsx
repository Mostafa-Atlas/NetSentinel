import React from "react";
import { api, type Alert, type ApiError, type Page } from "../../api";

function localTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function Alerts({ onDevice }: { onDevice: (id: number) => void }) {
  const [filter, setFilter] = React.useState("open");
  const [page, setPage] = React.useState<Page<Alert> | null>(null);
  const [offset, setOffset] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [busyId, setBusyId] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");
  const load = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPage(
        await api<Page<Alert>>(
          `/alerts?status=${filter}&limit=20&offset=${offset}`,
        ),
      );
    } catch (cause) {
      setError((cause as ApiError)?.message || "Unable to load alerts.");
    } finally {
      setLoading(false);
    }
  }, [filter, offset]);
  React.useEffect(() => {
    void load();
  }, [load]);

  async function act(alert: Alert, action: "acknowledge" | "resolve") {
    setBusyId(alert.id);
    setError("");
    try {
      await api<Alert>(`/alerts/${alert.id}/${action}`, { method: "POST" });
      await load();
    } catch (cause) {
      setError((cause as ApiError)?.message || `Unable to ${action} alert.`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">CHANGES THAT NEED REVIEW</p>
        <h1>Alerts</h1>
        <p>
          Each finding cites a scan observation. A reachable port is a probe
          result, not a vulnerability verdict.
        </p>
      </div>
      <div className="panel">
        <div className="device-toolbar">
          <label htmlFor="alert-filter">
            Show
            <select
              id="alert-filter"
              value={filter}
              onChange={(event) => {
                setOffset(0);
                setFilter(event.target.value);
              }}
            >
              <option value="open">Open alerts</option>
              <option value="active">Unacknowledged</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="all">All alerts</option>
            </select>
          </label>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {loading ? (
          <p role="status">Loading alerts…</p>
        ) : page?.items.length ? (
          <>
            <p className="result-count">
              {page.total} alerts · showing {offset + 1}–
              {offset + page.items.length}
            </p>
            <ul className="alert-list">
              {page.items.map((alert) => (
                <li key={alert.id}>
                  <div className="alert-heading">
                    <strong>{alert.summary}</strong>
                    <span className={`status-tag ${alert.status}`}>
                      {alert.status}
                    </span>
                  </div>
                  <p>{alert.details}</p>
                  <div className="alert-meta">
                    <span>First seen {localTime(alert.created_at)}</span>
                    <span>Last seen {localTime(alert.last_seen_at)}</span>
                    <span>Evidence: {alert.evidence_ref}</span>
                    <span>Severity: {alert.severity}</span>
                  </div>
                  <div className="button-row">
                    {alert.device_id !== null && (
                      <button
                        className="secondary"
                        onClick={() => onDevice(alert.device_id!)}
                      >
                        Inspect {alert.device_name || "device"}
                      </button>
                    )}
                    {alert.status === "active" && (
                      <button
                        className="secondary"
                        disabled={busyId === alert.id}
                        onClick={() => void act(alert, "acknowledge")}
                      >
                        Acknowledge
                      </button>
                    )}
                    {alert.status !== "resolved" && (
                      <button
                        className="secondary"
                        disabled={busyId === alert.id}
                        onClick={() => void act(alert, "resolve")}
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            <div className="button-row pager">
              <button
                className="secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Previous
              </button>
              <button
                className="secondary"
                disabled={offset + 20 >= page.total}
                onClick={() => setOffset(offset + 20)}
              >
                Next
              </button>
            </div>
          </>
        ) : (
          <p className="empty">
            {filter === "open"
              ? "No open alerts. New observations will appear here."
              : "No alerts match this filter."}
          </p>
        )}
      </div>
    </section>
  );
}
