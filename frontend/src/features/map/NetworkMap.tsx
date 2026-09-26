import React from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import {
  api,
  type ApiError,
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
  const graphRef = React.useRef<HTMLDivElement>(null);
  const cyRef = React.useRef<Core | null>(null);
  React.useEffect(() => {
    api<Topology>("/topology")
      .then(setTopology)
      .catch((cause) =>
        setError((cause as ApiError)?.message || "Unable to load topology."),
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
    const cy = cytoscape({
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
          selector: ":selected",
          style: { "border-width": 4, "border-color": "#a7ebfb" },
        },
      ],
    });
    cy.on("tap", 'node[kind = "device"]', (event) =>
      setSelectedId(event.target.id()),
    );
    cyRef.current = cy;
    return () => {
      cy.destroy();
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
            <div ref={graphRef} className="map-canvas" aria-hidden="true" />
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
    </section>
  );
}
