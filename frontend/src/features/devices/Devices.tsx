import React from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  type ApiError,
  type Device,
  type Observation,
  type Page,
  type ServiceObservation,
} from "../../api";

function errorMessage(cause: unknown): string {
  return (cause as ApiError)?.message || "Unable to load device data.";
}
function localTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Never";
}

export function Devices() {
  const [devices, setDevices] = React.useState<Device[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [known, setKnown] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [detail, setDetail] = React.useState<Device | null>(null);
  const [observations, setObservations] = React.useState<Observation[]>([]);
  const [services, setServices] = React.useState<ServiceObservation[]>([]);
  const [name, setName] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [knownState, setKnownState] = React.useState<"known" | "unknown">(
    "unknown",
  );
  const [saving, setSaving] = React.useState(false);
  const [notice, setNotice] = React.useState("");

  const load = React.useCallback(() => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ limit: "100", search });
    if (known) params.set("known_state", known);
    if (status) params.set("status", status);
    api<Page<Device>>(`/devices?${params}`)
      .then((page) => {
        setDevices(page.items);
        setTotal(page.total);
      })
      .catch((cause) => setError(errorMessage(cause)))
      .finally(() => setLoading(false));
  }, [search, known, status]);
  React.useEffect(load, [load]);
  React.useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    Promise.all([
      api<Device>(`/devices/${selectedId}`),
      api<Page<Observation>>(`/devices/${selectedId}/observations?limit=30`),
      api<Page<ServiceObservation>>(`/devices/${selectedId}/services?limit=30`),
    ])
      .then(([device, observationsPage, servicesPage]) => {
        setDetail(device);
        setName(device.display_name);
        setNotes(device.notes);
        setKnownState(device.known_state);
        setObservations(observationsPage.items);
        setServices(servicesPage.items);
      })
      .catch((cause) => setError(errorMessage(cause)));
  }, [selectedId]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const updated = await api<Device>(`/devices/${detail.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: name,
          notes,
          known_state: knownState,
        }),
      });
      setDetail(updated);
      setNotice("Device details saved.");
      load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSaving(false);
    }
  }

  const latencyPoints = [...observations]
    .reverse()
    .filter((row) => row.latency_ms !== null)
    .map((row) => ({
      time: new Date(row.observed_at).toLocaleTimeString(),
      latency: row.latency_ms,
    }));
  const missedCount = observations.filter(
    (row) => row.reachable === false,
  ).length;

  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">INVENTORY</p>
        <h1>Devices</h1>
        <p>
          Devices appear only after an actual network observation. Identity is
          based on available evidence and may need review.
        </p>
      </div>
      <div className="panel">
        <div className="device-toolbar">
          <label htmlFor="device-search">
            Search name or IP
            <input
              id="device-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search inventory"
            />
          </label>
          <label htmlFor="known-filter">
            Familiarity
            <select
              id="known-filter"
              value={known}
              onChange={(event) => setKnown(event.target.value)}
            >
              <option value="">All</option>
              <option value="known">Known</option>
              <option value="unknown">Needs review</option>
            </select>
          </label>
          <label htmlFor="status-filter">
            Reachability
            <select
              id="status-filter"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All</option>
              <option value="online">Online</option>
              <option value="unconfirmed">Unconfirmed</option>
              <option value="offline">Offline</option>
            </select>
          </label>
        </div>
        {loading ? (
          <p role="status">Loading devices…</p>
        ) : devices.length === 0 ? (
          <p className="empty">
            {search || known || status
              ? "No devices match these filters."
              : "No devices observed yet. Run discovery from Settings."}
          </p>
        ) : (
          <>
            <p className="result-count">
              {total} device{total === 1 ? "" : "s"}
            </p>
            <ul className="device-list">
              {devices.map((device) => (
                <li key={device.id}>
                  <button
                    className="device-row"
                    onClick={() => setSelectedId(device.id)}
                    aria-label={`Open ${device.display_name}`}
                  >
                    <span className="device-row-main">
                      <strong>{device.display_name}</strong>
                      <small>
                        {device.addresses[0]?.ip ?? "Address unknown"} ·{" "}
                        {device.identity_confidence === "observed_mac"
                          ? "Observed MAC"
                          : "Provisional identity"}
                      </small>
                    </span>
                    <span className={`status-tag ${device.status}`}>
                      {device.status}
                    </span>
                    <span className="known-tag">
                      {device.known_state === "known" ? "Known" : "Review"}
                    </span>
                    <time dateTime={device.last_observed_at ?? undefined}>
                      {localTime(device.last_observed_at)}
                    </time>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {detail && (
        <div className="panel detail-panel">
          <div className="detail-heading">
            <div>
              <p className="eyebrow">DEVICE #{detail.id}</p>
              <h2>{detail.display_name}</h2>
              <p>
                {detail.status} ·{" "}
                {detail.identity_confidence === "observed_mac"
                  ? "Identity linked by an observed MAC, which can change or be spoofed."
                  : "Provisional IP-based identity; verify before assuming it is the same device."}
              </p>
            </div>
            <button className="secondary" onClick={() => setSelectedId(null)}>
              Close details
            </button>
          </div>
          <div className="split-grid">
            <section>
              <h3>Owner details</h3>
              <form onSubmit={save}>
                <label htmlFor="device-name">Display name</label>
                <input
                  id="device-name"
                  maxLength={100}
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
                <label htmlFor="device-known">Familiarity</label>
                <select
                  id="device-known"
                  value={knownState}
                  onChange={(event) =>
                    setKnownState(event.target.value as "known" | "unknown")
                  }
                >
                  <option value="unknown">Needs review</option>
                  <option value="known">Known device</option>
                </select>
                <label htmlFor="device-notes">Notes</label>
                <textarea
                  id="device-notes"
                  rows={4}
                  maxLength={2000}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
                <button className="primary" disabled={saving}>
                  {saving ? "Saving…" : "Save details"}
                </button>
                {notice && (
                  <p className="success" role="status">
                    {notice}
                  </p>
                )}
              </form>
            </section>
            <section>
              <h3>Address history</h3>
              <ul className="evidence-list">
                {detail.addresses.map((address, index) => (
                  <li key={`${address.ip}-${index}`}>
                    <strong>{address.ip}</strong>
                    <span>
                      {address.mac
                        ? `Observed MAC ${address.mac}`
                        : "MAC unavailable"}
                    </span>
                    <small>
                      First {localTime(address.first_seen_at)} · Last{" "}
                      {localTime(address.last_seen_at)}
                    </small>
                  </li>
                ))}
              </ul>
            </section>
          </div>
          <section className="history-section">
            <h3>Reachability history</h3>
            <p>
              {observations.length} recent observations · {missedCount} without
              a response. Times are shown in your local timezone.
            </p>
            {latencyPoints.length >= 2 ? (
              <>
                <div
                  className="latency-chart"
                  role="img"
                  aria-label={`Latency chart with ${latencyPoints.length} response samples in milliseconds`}
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={latencyPoints}
                      margin={{ top: 8, right: 18, left: 0, bottom: 8 }}
                    >
                      <CartesianGrid stroke="#294157" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="time"
                        stroke="#9db1c3"
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis
                        stroke="#9db1c3"
                        tick={{ fontSize: 11 }}
                        unit="ms"
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#102235",
                          border: "1px solid #365268",
                          borderRadius: 8,
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="latency"
                        stroke="#66cce9"
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="helper">
                  Latest response:{" "}
                  {latencyPoints[latencyPoints.length - 1].latency} ms.
                </p>
              </>
            ) : (
              <p className="empty">
                More responding scans are needed for a latency chart.
              </p>
            )}
          </section>
          <div className="split-grid evidence-grid">
            <section>
              <h3>Reachability evidence</h3>
              {observations.length ? (
                <ul className="evidence-list">
                  {observations.map((row) => (
                    <li key={row.id}>
                      <strong>
                        {row.reachable === true
                          ? "Responded"
                          : row.reachable === false
                            ? "No response"
                            : "Unconfirmed"}
                      </strong>
                      <span>
                        {row.source} ·{" "}
                        {row.latency_ms === null
                          ? "Latency unavailable"
                          : `${row.latency_ms} ms`}
                      </span>
                      <small>
                        {localTime(row.observed_at)} · Scan #{row.scan_run_id}
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty">No observations yet.</p>
              )}
            </section>
            <section>
              <h3>TCP service observations</h3>
              {services.length ? (
                <ul className="evidence-list">
                  {services.map((row) => (
                    <li key={row.id}>
                      <strong>
                        TCP {row.port} · {row.state}
                      </strong>
                      <span>{row.ip}</span>
                      <small>
                        {localTime(row.observed_at)} · Scan #{row.scan_run_id}
                      </small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty">No port observations yet.</p>
              )}
            </section>
          </div>
        </div>
      )}
    </section>
  );
}
