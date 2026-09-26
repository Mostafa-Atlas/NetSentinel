import React from "react";
import { api, type ApiError, type Overview as OverviewData } from "../../api";

function localTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "No observations yet";
}

export function Overview({
  onNavigate,
}: {
  onNavigate: (
    view: "devices" | "map" | "alerts" | "timeline" | "settings",
  ) => void;
}) {
  const [data, setData] = React.useState<OverviewData | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    api<OverviewData>("/overview")
      .then(setData)
      .catch((cause) =>
        setError((cause as ApiError)?.message || "Unable to load overview."),
      );
  }, []);
  if (error)
    return (
      <section>
        <h1>Overview</h1>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  if (!data)
    return (
      <section className="loading-inline" role="status">
        Loading overview…
      </section>
    );
  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">OVERVIEW</p>
        <h1>Your network, in view.</h1>
        <p>
          Evidence from approved scans, with timestamps and uncertainty kept
          visible.
        </p>
      </div>
      <div className="metrics">
        <article className="metric-card">
          <span>Observed devices</span>
          <strong>{data.device_count}</strong>
          <small>Updated {localTime(data.updated_at)}</small>
        </article>
        <article className="metric-card">
          <span>Last responded</span>
          <strong>{data.online_count}</strong>
          <small>Updated {localTime(data.updated_at)}</small>
        </article>
        <article className="metric-card">
          <span>Needs review</span>
          <strong>{data.review_count}</strong>
          <small>Updated {localTime(data.updated_at)}</small>
        </article>
        <article className="metric-card">
          <span>Active alerts</span>
          <strong>{data.active_alert_count}</strong>
          <small>Updated {localTime(data.updated_at)}</small>
          <button
            className="text-button metric-link"
            onClick={() => onNavigate("alerts")}
          >
            Review alerts
          </button>
        </article>
      </div>
      {data.device_count === 0 ? (
        <div className="panel empty-panel">
          <div className="empty-icon">◎</div>
          <h2>Ready to discover</h2>
          <p>
            Approve a private network range and run discovery. Devices will
            appear only after an actual observation.
          </p>
          <button className="primary" onClick={() => onNavigate("settings")}>
            Configure network scope
          </button>
        </div>
      ) : (
        <div className="overview-grid">
          <div className="panel">
            <h2>Inventory snapshot</h2>
            <p>
              {data.online_count} last responded · {data.offline_count} met the
              missed-scan threshold · {data.review_count} need review.
            </p>
            <div className="button-row">
              <button className="primary" onClick={() => onNavigate("devices")}>
                Review devices
              </button>
              <button className="secondary" onClick={() => onNavigate("map")}>
                Open network map
              </button>
            </div>
          </div>
          <div className="panel">
            <h2>Recent scans</h2>
            {data.recent_scans.length ? (
              <ul className="evidence-list">
                {data.recent_scans.map((scan) => (
                  <li key={scan.id}>
                    <strong>
                      Scan #{scan.id} · {scan.status}
                    </strong>
                    <span>
                      {scan.host_count} addresses probed · {scan.type}
                    </span>
                    <small>
                      {localTime(scan.finished_at || scan.started_at)}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty">No scans have run yet.</p>
            )}
          </div>
        </div>
      )}
      <div className="panel recent-events">
        <div className="detail-heading">
          <div>
            <h2>Recent changes</h2>
            <p>Latest timestamped activity from scans and owner actions.</p>
          </div>
          <button className="secondary" onClick={() => onNavigate("timeline")}>
            View timeline
          </button>
        </div>
        {data.recent_events.length ? (
          <ul className="evidence-list">
            {data.recent_events.map((event) => (
              <li key={event.id}>
                <strong>{event.summary}</strong>
                <span>
                  {event.event_type.replaceAll("_", " ")} · {event.actor}
                </span>
                <small>{localTime(event.occurred_at)}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">No changes recorded yet.</p>
        )}
      </div>
    </section>
  );
}
