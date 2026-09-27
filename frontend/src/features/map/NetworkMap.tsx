import React from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import {
  api,
  type ApiError,
  type Comparison,
  type LinkAnnotation,
  type Topology,
  type TopologyNode,
} from "../../api";

function localTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Unknown";
}

export function NetworkMap({ onConfigure }: { onConfigure: () => void }) {
  const [topology, setTopology] = React.useState<Topology | null>(null);
  const [error, setError] = React.useState("");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [graphAvailable, setGraphAvailable] = React.useState(true);
  const [annotations, setAnnotations] = React.useState<LinkAnnotation[]>([]);
  const [sourceId, setSourceId] = React.useState(0);
  const [targetId, setTargetId] = React.useState(0);
  const [label, setLabel] = React.useState("");
  const [note, setNote] = React.useState("");
  const [comparison, setComparison] = React.useState<Comparison | null>(null);
  const [actionError, setActionError] = React.useState("");
  const graphRef = React.useRef<HTMLDivElement>(null);
  const cyRef = React.useRef<Core | null>(null);
  React.useEffect(() => {
    api<Topology>("/topology")
      .then(setTopology)
      .catch((cause) =>
        setError((cause as ApiError)?.message || "Unable to load topology."),
      );
  }, []);
  React.useEffect(() => {
    api<LinkAnnotation[]>("/topology/annotations")
      .then(setAnnotations)
      .catch((cause) =>
        setActionError(
          (cause as ApiError)?.message || "Unable to load annotations.",
        ),
      );
  }, []);
  const deviceNodes =
    topology?.nodes.filter((node) => node.kind === "device") ?? [];
  React.useEffect(() => {
    if (!topology || deviceNodes.length === 0 || !graphRef.current) return;
    const elements: ElementDefinition[] = [
      ...topology.nodes.map((node) => ({
        data: {
          id: node.id,
          label: node.label,
          kind: node.kind,
          status: node.status,
        },
      })),
      ...topology.links.map((link, index) => ({
        data: {
          id: `edge:${index}`,
          source: link.source,
          target: link.target,
          kind: link.kind,
        },
      })),
    ];
    let cy: Core | null = null;
    try {
      cy = cytoscape({
        container: graphRef.current,
        elements,
        layout: { name: "breadthfirst", directed: true, spacingFactor: 1.4 },
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#1b4058",
              "border-color": "#68cbe8",
              "border-width": 2,
              label: "data(label)",
              color: "#e8f2f8",
              "font-size": 13,
              "text-valign": "bottom",
              "text-margin-y": 10,
              "text-wrap": "wrap",
              "text-max-width": "125px",
              width: 46,
              height: 46,
            },
          },
          {
            selector: 'node[kind = "subnet"]',
            style: {
              shape: "round-rectangle",
              width: 92,
              height: 52,
              "background-color": "#24546b",
            },
          },
          {
            selector: 'node[status = "unconfirmed"]',
            style: { "border-color": "#e5bd6b" },
          },
          {
            selector: 'node[status = "offline"]',
            style: { "border-color": "#dd8c88" },
          },
          {
            selector: "edge",
            style: {
              width: 2,
              "line-color": "#57768b",
              "line-style": "dashed",
              "target-arrow-shape": "none",
              "curve-style": "bezier",
            },
          },
          {
            selector: 'edge[kind = "owner_annotation"]',
            style: { "line-style": "solid", "line-color": "#8ee7c1", width: 3 },
          },
          {
            selector: ":selected",
            style: { "border-width": 4, "border-color": "#a7ebfb" },
          },
        ],
      });
      cy.on("tap", 'node[kind = "device"]', (event) =>
        setSelectedId(event.target.id()),
      );
      cyRef.current = cy;
    } catch {
      setGraphAvailable(false);
    }
    return () => {
      cy?.destroy();
      cyRef.current = null;
    };
  }, [topology, deviceNodes.length]);
  function selectNode(node: TopologyNode) {
    setSelectedId(node.id);
    const cy = cyRef.current;
    if (cy) {
      cy.elements().unselect();
      const item = cy.getElementById(node.id);
      item.select();
      cy.center(item);
    }
  }
  const selected = topology?.nodes.find((node) => node.id === selectedId);
  async function refreshMap() {
    const [nextTopology, nextAnnotations] = await Promise.all([
      api<Topology>("/topology"),
      api<LinkAnnotation[]>("/topology/annotations"),
    ]);
    setTopology(nextTopology);
    setAnnotations(nextAnnotations);
  }
  async function addAnnotation(event: React.FormEvent) {
    event.preventDefault();
    setActionError("");
    try {
      await api("/topology/annotations", {
        method: "POST",
        body: JSON.stringify({
          source_id: sourceId,
          target_id: targetId,
          label,
          note,
        }),
      });
      setLabel("");
      setNote("");
      await refreshMap();
    } catch (cause) {
      setActionError(
        (cause as ApiError)?.message || "Unable to save annotation.",
      );
    }
  }
  async function removeAnnotation(id: number) {
    setActionError("");
    try {
      await api(`/topology/annotations/${id}`, { method: "DELETE" });
      await refreshMap();
    } catch (cause) {
      setActionError(
        (cause as ApiError)?.message || "Unable to remove annotation.",
      );
    }
  }
  async function compare() {
    setActionError("");
    try {
      setComparison(
        await api<Comparison>(
          `/devices/compare?left_id=${sourceId}&right_id=${targetId}`,
        ),
      );
    } catch (cause) {
      setActionError(
        (cause as ApiError)?.message || "Unable to compare devices.",
      );
    }
  }
  if (error)
    return (
      <section>
        <h1>Network map</h1>
        <p className="error" role="alert">
          {error}
        </p>
      </section>
    );
  if (!topology)
    return (
      <section className="loading-inline" role="status">
        Loading network map…
      </section>
    );
  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">TOPOLOGY</p>
        <h1>Network map</h1>
        <p>
          Observed devices grouped by approved subnet. Dashed links are inferred
          from IP addresses; they are not verified physical connections.
        </p>
      </div>
      <div className="map-legend">
        <span className="legend-line" /> Inferred subnet grouping{" "}
        <span className="legend-note">· Physical path unknown</span>
        <span className="legend-note">
          {" "}
          · Solid green: owner annotation, unverified
        </span>
      </div>
      {deviceNodes.length === 0 ? (
        <div className="panel empty-panel">
          <h2>No observed devices yet</h2>
          <p>Run discovery on an approved private range to populate the map.</p>
          <button className="primary" onClick={onConfigure}>
            Go to Settings
          </button>
        </div>
      ) : (
        <div className="map-layout">
          <div className="panel map-panel">
            {graphAvailable ? (
              <div ref={graphRef} className="map-canvas" aria-hidden="true" />
            ) : (
              <p className="empty">
                Graph rendering is unavailable in this browser. Use the device
                list to inspect the same observations.
              </p>
            )}
          </div>
          <div className="panel map-list">
            <h2>Devices in map</h2>
            <p className="helper">
              Use this list to explore the map with a keyboard or screen reader.
            </p>
            <ul>
              {deviceNodes.map((node) => (
                <li key={node.id}>
                  <button
                    className={
                      selectedId === node.id
                        ? "map-device selected"
                        : "map-device"
                    }
                    onClick={() => selectNode(node)}
                  >
                    <strong>{node.label}</strong>
                    <span>
                      {node.status} · {node.addresses?.[0] ?? "Address unknown"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {selected && (
              <div className="map-detail">
                <h3>{selected.label}</h3>
                <p>Status: {selected.status}</p>
                <p>
                  Identity:{" "}
                  {selected.identity_confidence === "observed_mac"
                    ? "Observed MAC; may change or be spoofed"
                    : "Provisional IP identity"}
                </p>
                <p>Last observation: {localTime(selected.last_observed_at)}</p>
                <p>Addresses: {selected.addresses?.join(", ") || "Unknown"}</p>
                <p className="helper">
                  Subnet grouping is inferred. No switch, router, or Wi-Fi link
                  was verified.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
      {deviceNodes.length > 1 && (
        <div className="panel investigation-panel">
          <h2>Investigate devices</h2>
          <p className="helper">
            Compare saved observations or annotate a relationship you know. An
            annotation is an owner claim, not a verified physical link.
          </p>
          {actionError && (
            <p className="error" role="alert">
              {actionError}
            </p>
          )}
          <div className="investigation-grid">
            <label>
              First device
              <select
                value={sourceId}
                onChange={(event) => {
                  setSourceId(Number(event.target.value));
                  setComparison(null);
                }}
              >
                <option value={0}>Select device</option>
                {deviceNodes.map((node) => (
                  <option key={node.id} value={node.device_id}>
                    {node.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Second device
              <select
                value={targetId}
                onChange={(event) => {
                  setTargetId(Number(event.target.value));
                  setComparison(null);
                }}
              >
                <option value={0}>Select device</option>
                {deviceNodes.map((node) => (
                  <option key={node.id} value={node.device_id}>
                    {node.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button
            className="secondary"
            disabled={!sourceId || !targetId || sourceId === targetId}
            onClick={compare}
          >
            Compare observations
          </button>
          {comparison && (
            <div className="investigation-grid" aria-label="Device comparison">
              {[comparison.left, comparison.right].map((device) => (
                <div key={device.id}>
                  <h3>{device.display_name}</h3>
                  <p>
                    Status: {device.status} · Identity:{" "}
                    {device.identity_confidence}
                  </p>
                  <p>Last observed: {localTime(device.last_observed_at)}</p>
                  <p>
                    Addresses:{" "}
                    {device.addresses.map((address) => address.ip).join(", ") ||
                      "None"}
                  </p>
                  <p>
                    Latest service states:{" "}
                    {device.services
                      .map(
                        (service) =>
                          `${service.port}/${service.protocol} ${service.state} (${localTime(service.observed_at)})`,
                      )
                      .join(", ") || "None"}
                  </p>
                </div>
              ))}
              <p className="helper">{comparison.provenance}</p>
            </div>
          )}
          <form onSubmit={addAnnotation}>
            <label>
              Relationship label
              <input
                maxLength={100}
                required
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="e.g. connected through switch"
              />
            </label>
            <label>
              Owner note
              <input
                maxLength={500}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={!sourceId || !targetId || sourceId === targetId}
            >
              Save owner annotation
            </button>
          </form>
          <h3>Saved annotations</h3>
          {annotations.length ? (
            <ul className="evidence-list">
              {annotations.map((link) => (
                <li key={link.id}>
                  <strong>{link.label}</strong>
                  <span>
                    Devices #{link.source_id} and #{link.target_id} · Owner
                    supplied, unverified
                  </span>
                  {link.note && <p>{link.note}</p>}
                  <button
                    className="text-button"
                    onClick={() => removeAnnotation(link.id)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">No owner annotations saved.</p>
          )}
        </div>
      )}
    </section>
  );
}
