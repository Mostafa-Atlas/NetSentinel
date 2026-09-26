import React from "react";
import { api, type ApiError, type Page, type Scan, type Scope } from "./api";
import { MonitoringSettings } from "./features/settings/MonitoringSettings";
import { ScopePolicy } from "./features/settings/ScopePolicy";

type User = { username: string };
type View = "overview" | "devices" | "map" | "settings";
const Devices = React.lazy(() =>
  import("./features/devices/Devices").then((module) => ({
    default: module.Devices,
  })),
);
const Overview = React.lazy(() =>
  import("./features/overview/Overview").then((module) => ({
    default: module.Overview,
  })),
);
const NetworkMap = React.lazy(() =>
  import("./features/map/NetworkMap").then((module) => ({
    default: module.NetworkMap,
  })),
);

function messageOf(error: unknown): string {
  return (error as ApiError)?.message || "The request failed. Try again.";
}

function AuthForm({
  mode,
  onSuccess,
}: {
  mode: "setup" | "login";
  onSuccess: (user: User) => void;
}) {
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await api<User>(
        `/auth/${mode === "setup" ? "bootstrap" : "login"}`,
        { method: "POST", body: JSON.stringify({ username, password }) },
      );
      onSuccess(user);
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <div className="auth-intro">
        <span className="brand-mark">
          N<span>·</span>
        </span>
        <p className="eyebrow">LOCAL NETWORK OPERATIONS</p>
        <h1>Know what’s on your network.</h1>
        <p>
          Discover devices, follow changes, and review alerts from one private
          console.
        </p>
        <div className="auth-note">
          <strong>Local by default</strong>
          <span>
            No cloud account. No scan until you approve a private range.
          </span>
        </div>
      </div>
      <main className="auth-panel">
        <p className="eyebrow">
          {mode === "setup" ? "FIRST RUN" : "WELCOME BACK"}
        </p>
        <h2>{mode === "setup" ? "Create administrator" : "Sign in"}</h2>
        <p className="muted">
          {mode === "setup"
            ? "Choose your local account. There is no default password."
            : "Access your local NetSentinel console."}
        </p>
        <form onSubmit={submit}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            minLength={3}
            maxLength={80}
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete={
              mode === "setup" ? "new-password" : "current-password"
            }
            minLength={12}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <p className="helper">
            At least 12 characters. Password managers and paste are supported.
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy
              ? "Working…"
              : mode === "setup"
                ? "Create account"
                : "Sign in"}
          </button>
        </form>
      </main>
    </div>
  );
}

function ScopeSettings() {
  const [scopes, setScopes] = React.useState<Scope[]>([]);
  const [latestScan, setLatestScan] = React.useState<Scan | null>(null);
  const [editingScopeId, setEditingScopeId] = React.useState<number | null>(
    null,
  );
  const [name, setName] = React.useState("Home LAN");
  const [cidr, setCidr] = React.useState("");
  const [approved, setApproved] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const reload = React.useCallback(() => {
    api<Scope[]>("/scopes")
      .then(setScopes)
      .catch((cause) => setError(messageOf(cause)));
  }, []);
  React.useEffect(reload, [reload]);
  React.useEffect(() => {
    api<Page<Scan>>("/scans?limit=1")
      .then((page) => setLatestScan(page.items[0] ?? null))
      .catch((cause) => setError(messageOf(cause)));
  }, []);
  React.useEffect(() => {
    if (!latestScan || !["queued", "running"].includes(latestScan.status))
      return;
    const timer = window.setInterval(() => {
      api<Scan>(`/scans/${latestScan.id}`)
        .then(setLatestScan)
        .catch((cause) => setError(messageOf(cause)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [latestScan]);
  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api<Scope>("/scopes", {
        method: "POST",
        body: JSON.stringify({ name, cidr, approved }),
      });
      setNotice("Approved range saved. Discovery is ready to run.");
      setCidr("");
      setApproved(false);
      reload();
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }
  async function toggle(scope: Scope) {
    setError("");
    setNotice("");
    const approval = !scope.enabled
      ? window.confirm(
          `Enable scanning of ${scope.cidr}? Confirm that you administer this range.`,
        )
      : false;
    if (!scope.enabled && !approval) return;
    try {
      await api<Scope>(`/scopes/${scope.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !scope.enabled, approved: approval }),
      });
      reload();
    } catch (cause) {
      setError(messageOf(cause));
    }
  }
  async function startScan(scope: Scope) {
    const addresses = 2 ** (32 - Number(scope.cidr.split("/")[1]));
    if (
      !window.confirm(
        `Scan ${scope.cidr}? This may contact up to ${addresses} addresses on ${scope.ports.length} TCP ports with at most ${scope.max_concurrency} concurrent probes.`,
      )
    )
      return;
    setError("");
    setNotice("");
    try {
      setLatestScan(
        await api<Scan>("/scans", {
          method: "POST",
          body: JSON.stringify({ scope_id: scope.id }),
        }),
      );
    } catch (cause) {
      setError(messageOf(cause));
    }
  }
  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">CONFIGURATION</p>
        <h1>Network scopes</h1>
        <p>
          Only explicitly approved private IPv4 ranges can be scanned. Each
          scope is limited to 256 addresses.
        </p>
      </div>
      <div className="split-grid">
        <div className="panel">
          <h2>Add approved range</h2>
          <form onSubmit={add}>
            <label htmlFor="scope-name">Name</label>
            <input
              id="scope-name"
              maxLength={100}
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <label htmlFor="scope-cidr">Private IPv4 CIDR</label>
            <input
              id="scope-cidr"
              placeholder="192.168.1.0/24"
              required
              value={cidr}
              onChange={(event) => setCidr(event.target.value)}
            />
            <p className="helper">
              Examples: 10.0.0.0/24 or 192.168.1.0/24. Public, loopback, and
              larger ranges are refused.
            </p>
            <label className="check-row">
              <input
                type="checkbox"
                checked={approved}
                onChange={(event) => setApproved(event.target.checked)}
              />
              <span>
                I own or am authorized to administer this range and approve
                bounded scans.
              </span>
            </label>
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
            <button className="primary" disabled={busy || !approved}>
              {busy ? "Saving…" : "Approve range"}
            </button>
          </form>
        </div>
        <div className="panel">
          <h2>Approved ranges</h2>
          {scopes.length === 0 ? (
            <p className="empty">
              No ranges approved yet. Add one to enable discovery.
            </p>
          ) : (
            <ul className="scope-list">
              {scopes.map((scope) => (
                <li key={scope.id}>
                  <div>
                    <strong>{scope.name}</strong>
                    <code>{scope.cidr}</code>
                    <small>
                      {scope.enabled ? "Enabled" : "Paused"} ·{" "}
                      {scope.ports.length} TCP ports · {scope.max_concurrency}{" "}
                      concurrent probes
                    </small>
                  </div>
                  <div className="scope-actions">
                    {scope.enabled && (
                      <button
                        className="primary"
                        onClick={() => startScan(scope)}
                      >
                        Run discovery
                      </button>
                    )}
                    <button className="secondary" onClick={() => toggle(scope)}>
                      {scope.enabled ? "Pause" : "Enable"}
                    </button>
                    <button
                      className="secondary"
                      onClick={() =>
                        setEditingScopeId(
                          editingScopeId === scope.id ? null : scope.id,
                        )
                      }
                    >
                      {editingScopeId === scope.id
                        ? "Close policy"
                        : "Edit policy"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {scopes.find((scope) => scope.id === editingScopeId) && (
            <ScopePolicy
              scope={scopes.find((scope) => scope.id === editingScopeId)!}
              onSaved={() => {
                reload();
                setEditingScopeId(null);
                setNotice("Probe policy saved.");
              }}
            />
          )}
        </div>
      </div>
      <div className="panel scan-panel">
        <h2>Latest discovery</h2>
        {latestScan ? (
          <p role="status">
            Run #{latestScan.id}: <strong>{latestScan.status}</strong>
            {latestScan.status === "completed"
              ? ` · ${latestScan.host_count} addresses probed`
              : ""}
            {latestScan.error_summary ? ` · ${latestScan.error_summary}` : ""}
          </p>
        ) : (
          <p className="empty">No scan has run yet.</p>
        )}
      </div>
      <MonitoringSettings />
    </section>
  );
}

export function App() {
  const [bootstrapping, setBootstrapping] = React.useState<boolean | null>(
    null,
  );
  const [user, setUser] = React.useState<User | null>(null);
  const [view, setView] = React.useState<View>("overview");
  const [health, setHealth] = React.useState("Checking API…");
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let active = true;
    fetch("/health")
      .then((response) => response.json())
      .then((data) => {
        if (active)
          setHealth(data.status === "ok" ? "API connected" : "API unavailable");
      })
      .catch(() => {
        if (active) setHealth("API unavailable");
      });
    api<{ needs_setup: boolean }>("/auth/bootstrap-status")
      .then(async (data) => {
        if (!active) return;
        setBootstrapping(data.needs_setup);
        if (!data.needs_setup) {
          try {
            const current = await api<User>("/auth/me");
            if (active) setUser(current);
          } catch {
            /* signed out */
          }
        }
      })
      .catch((cause) => {
        if (active) setError(messageOf(cause));
      });
    return () => {
      active = false;
    };
  }, []);
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setUser(null);
    } catch (cause) {
      setError(messageOf(cause));
    }
  }
  if (error && bootstrapping === null)
    return (
      <main className="fatal">
        <h1>NetSentinel unavailable</h1>
        <p role="alert">{error}</p>
        <p>Check that the API and database migrations are running.</p>
      </main>
    );
  if (bootstrapping === null)
    return (
      <main className="loading" role="status">
        Loading NetSentinel…
      </main>
    );
  if (!user)
    return (
      <AuthForm
        mode={bootstrapping ? "setup" : "login"}
        onSuccess={(next) => {
          setUser(next);
          setBootstrapping(false);
        }}
      />
    );
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            N<span>·</span>
          </span>
          <span>NetSentinel</span>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <button
            className={view === "overview" ? "nav-item active" : "nav-item"}
            onClick={() => setView("overview")}
          >
            Overview
          </button>
          <button
            className={view === "devices" ? "nav-item active" : "nav-item"}
            onClick={() => setView("devices")}
          >
            Devices
          </button>
          <button
            className={view === "map" ? "nav-item active" : "nav-item"}
            onClick={() => setView("map")}
          >
            Network map
          </button>
          <button
            className={view === "settings" ? "nav-item active" : "nav-item"}
            onClick={() => setView("settings")}
          >
            Settings
          </button>
        </nav>
        <div className="sidebar-foot">
          <span className="service-dot" />
          {health}
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <span className="topbar-title">Home network</span>
          <div>
            <span className="username">{user.username}</span>
            <button className="text-button" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <main id="main" className="main-content">
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {view === "settings" ? (
            <ScopeSettings />
          ) : view === "devices" ? (
            <React.Suspense fallback={<p role="status">Loading inventory…</p>}>
              <Devices />
            </React.Suspense>
          ) : view === "map" ? (
            <React.Suspense fallback={<p role="status">Loading map…</p>}>
              <NetworkMap onConfigure={() => setView("settings")} />
            </React.Suspense>
          ) : (
            <React.Suspense fallback={<p role="status">Loading overview…</p>}>
              <Overview onNavigate={(next) => setView(next)} />
            </React.Suspense>
          )}
        </main>
      </div>
    </div>
  );
}
