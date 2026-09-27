import React from "react";
import { api, type ApiError, type Scope } from "../../api";

export function ScopePolicy({
  scope,
  onSaved,
}: {
  scope: Scope;
  onSaved: () => void;
}) {
  const [ports, setPorts] = React.useState(scope.ports.join(", "));
  const [concurrency, setConcurrency] = React.useState(scope.max_concurrency);
  const [timeout, setTimeoutMs] = React.useState(scope.connect_timeout_ms);
  const [passiveEnabled, setPassiveEnabled] = React.useState(
    scope.passive_enabled,
  );
  const [approved, setApproved] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const parsed = ports.split(",").map((value) => Number(value.trim()));
    if (
      parsed.length < 1 ||
      parsed.length > 16 ||
      parsed.some(
        (value) => !Number.isInteger(value) || value < 1 || value > 65535,
      ) ||
      new Set(parsed).size !== parsed.length
    ) {
      setError("Enter 1–16 unique TCP ports between 1 and 65535.");
      return;
    }
    setBusy(true);
    try {
      await api<Scope>(`/scopes/${scope.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          ports: parsed,
          max_concurrency: concurrency,
          connect_timeout_ms: timeout,
          passive_enabled: passiveEnabled,
          approved,
        }),
      });
      onSaved();
    } catch (cause) {
      setError((cause as ApiError)?.message || "Unable to save probe policy.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="policy-form" onSubmit={save}>
      <h3>Probe policy for {scope.cidr}</h3>
      <div className="settings-fields">
        <label htmlFor={`ports-${scope.id}`}>
          TCP ports, comma separated
          <input
            id={`ports-${scope.id}`}
            value={ports}
            onChange={(event) => setPorts(event.target.value)}
          />
        </label>
        <label htmlFor={`concurrency-${scope.id}`}>
          Concurrent hosts
          <input
            id={`concurrency-${scope.id}`}
            type="number"
            min={1}
            max={32}
            value={concurrency}
            onChange={(event) => setConcurrency(Number(event.target.value))}
          />
        </label>
        <label htmlFor={`timeout-${scope.id}`}>
          Connect timeout (ms)
          <input
            id={`timeout-${scope.id}`}
            type="number"
            min={100}
            max={1000}
            value={timeout}
            onChange={(event) => setTimeoutMs(Number(event.target.value))}
          />
        </label>
      </div>
      <label className="check-row">
        <input
          type="checkbox"
          checked={passiveEnabled}
          onChange={(event) => setPassiveEnabled(event.target.checked)}
        />
        <span>
          Listen for mDNS and SSDP hints during scans (unverified metadata).
        </span>
      </label>
      <label className="check-row">
        <input
          type="checkbox"
          checked={approved}
          onChange={(event) => setApproved(event.target.checked)}
        />
        <span>I approve this bounded probe policy for this range.</span>
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="primary" disabled={!approved || busy}>
        {busy ? "Saving…" : "Save probe policy"}
      </button>
    </form>
  );
}
