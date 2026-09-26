import React from "react";
import { api, type ApiError, type Page, type TimelineEvent } from "../../api";

export function Timeline({ onDevice }: { onDevice: (id: number) => void }) {
  const [page, setPage] = React.useState<Page<TimelineEvent> | null>(null);
  const [offset, setOffset] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let active = true;
    setLoading(true);
    api<Page<TimelineEvent>>(`/events?limit=30&offset=${offset}`)
      .then((data) => {
        if (active) setPage(data);
      })
      .catch((cause) => {
        if (active)
          setError((cause as ApiError)?.message || "Unable to load timeline.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [offset]);
  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">AUDIT HISTORY</p>
        <h1>Timeline</h1>
        <p>Scans, device changes, alerts, and owner actions in time order.</p>
      </div>
      <div className="panel">
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {loading ? (
          <p role="status">Loading timeline…</p>
        ) : page?.items.length ? (
          <>
            <p className="result-count">
              {page.total} events · showing {offset + 1}–
              {offset + page.items.length}
            </p>
            <ol className="evidence-list timeline-list">
              {page.items.map((event) => (
                <li key={event.id}>
                  <strong>{event.summary}</strong>
                  <span>
                    {event.event_type.replaceAll("_", " ")} · {event.actor}
                  </span>
                  <small>
                    {new Date(event.occurred_at).toLocaleString()} ·{" "}
                    {event.evidence_ref || "No evidence reference"}
                  </small>
                  {event.device_id !== null && (
                    <button
                      className="text-button timeline-link"
                      onClick={() => onDevice(event.device_id!)}
                    >
                      Inspect device
                    </button>
                  )}
                </li>
              ))}
            </ol>
            <div className="button-row pager">
              <button
                className="secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 30))}
              >
                Previous
              </button>
              <button
                className="secondary"
                disabled={offset + 30 >= page.total}
                onClick={() => setOffset(offset + 30)}
              >
                Next
              </button>
            </div>
          </>
        ) : (
          <p className="empty">
            No events yet. Account, scope, and scan activity will appear here.
          </p>
        )}
      </div>
    </section>
  );
}
