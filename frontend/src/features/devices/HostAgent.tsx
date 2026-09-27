import React from "react";
import {
  api,
  type AgentEnrollment,
  type AgentReport,
  type ApiError,
  type Page,
} from "../../api";

function message(cause: unknown): string {
  return (cause as ApiError)?.message || "The host agent request failed.";
}

export function HostAgent({ deviceId }: { deviceId: number }) {
  const [enrollments, setEnrollments] = React.useState<AgentEnrollment[]>([]);
  const [reports, setReports] = React.useState<AgentReport[]>([]);
  const [name, setName] = React.useState("");
  const [expiresDays, setExpiresDays] = React.useState(90);
  const [issuedToken, setIssuedToken] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const reload = React.useCallback(() => {
    Promise.all([
      api<AgentEnrollment[]>(`/devices/${deviceId}/agent-enrollments`),
      api<Page<AgentReport>>(`/devices/${deviceId}/agent-reports?limit=10`),
    ])
      .then(([nextEnrollments, page]) => {
        setEnrollments(nextEnrollments);
        setReports(page.items);
      })
      .catch((cause) => setError(message(cause)));
  }, [deviceId]);
  React.useEffect(reload, [reload]);

  async function enroll(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setIssuedToken("");
    try {
      const result = await api<AgentEnrollment & { token: string }>(
        `/devices/${deviceId}/agent-enrollments`,
        {
          method: "POST",
          body: JSON.stringify({ name, expires_days: expiresDays }),
        },
      );
      setIssuedToken(result.token);
      setName("");
      reload();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(enrollment: AgentEnrollment) {
    if (
      !window.confirm(
        `Revoke agent ${enrollment.name}? It will no longer report for this device.`,
      )
    )
      return;
    setError("");
    try {
      await api(`/agent-enrollments/${enrollment.id}/revoke`, {
        method: "POST",
      });
      setIssuedToken("");
      reload();
    } catch (cause) {
      setError(message(cause));
    }
  }

  return (
    <section className="history-section">
      <h3>Optional host agent</h3>
      <p className="muted">
        Enroll this device to receive outbound host reports. The agent sends no
        commands and requires HTTPS when reporting remotely. Docker details are
        included only if the host agent is run with its Docker option. Reports
        identify the enrolled credential, not the physical host independently.
      </p>
      <form onSubmit={enroll} className="settings-fields">
        <label>
          Agent name
          <input
            maxLength={100}
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          Credential lifetime (days)
          <input
            type="number"
            min={1}
            max={365}
            value={expiresDays}
            onChange={(event) => setExpiresDays(Number(event.target.value))}
          />
        </label>
        <button className="secondary" disabled={busy}>
          {busy ? "Creating…" : "Create agent credential"}
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {issuedToken && (
        <div className="agent-token" role="status">
          <strong>Copy this token now; it is shown once.</strong>
          <code>{issuedToken}</code>
          <span>
            Set it as NETSENTINEL_AGENT_TOKEN on the host, then run
            backend/scripts/host_agent.py with your server origin.
          </span>
        </div>
      )}
      {enrollments.length ? (
        <ul className="evidence-list">
          {enrollments.map((enrollment) => (
            <li key={enrollment.id}>
              <strong>{enrollment.name}</strong>
              <span>
                {enrollment.revoked_at
                  ? "Revoked"
                  : `Expires ${new Date(enrollment.expires_at).toLocaleString()}`}
              </span>
              {!enrollment.revoked_at && (
                <button
                  className="secondary"
                  onClick={() => revoke(enrollment)}
                >
                  Revoke credential
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">No host agent enrolled.</p>
      )}
      <h4>Recent host reports</h4>
      {reports.length ? (
        <ul className="evidence-list">
          {reports.map((report) => (
            <li key={report.id}>
              <strong>
                {report.hostname} · {report.os_name}
              </strong>
              <span>
                One-minute load: {report.load_1m ?? "unavailable"} · Docker
                containers: {report.containers.length}
              </span>
              <small>
                Received {new Date(report.received_at).toLocaleString()}
              </small>
              {report.containers.length > 0 && (
                <ul>
                  {report.containers.map((container) => (
                    <li key={container.name}>
                      {container.name}: {container.state}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">No host reports yet.</p>
      )}
    </section>
  );
}
