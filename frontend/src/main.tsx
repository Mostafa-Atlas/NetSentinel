import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

export function App() {
  const [health, setHealth] = React.useState("Checking API…");
  React.useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((data) =>
        setHealth(data.status === "ok" ? "API connected" : "API unavailable"),
      )
      .catch(() => setHealth("API unavailable"));
  }, []);
  return (
    <main>
      <h1>NetSentinel</h1>
      <p>Local network operations console</p>
      <p role="status">{health}</p>
    </main>
  );
}

const root = document.getElementById("root");
if (root)
  createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
