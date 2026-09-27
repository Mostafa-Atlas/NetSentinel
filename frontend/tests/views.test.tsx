import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/App";

vi.mock("cytoscape", () => ({
  default: () => ({
    on: () => undefined,
    destroy: () => undefined,
    elements: () => ({ unselect: () => undefined }),
    getElementById: () => ({ select: () => undefined }),
    center: () => undefined,
  }),
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("overview and keyboard map list show observed data and inferred provenance", async () => {
  const overview = {
    device_count: 1,
    online_count: 1,
    review_count: 1,
    offline_count: 0,
    active_alert_count: 0,
    updated_at: "2026-09-27T00:00:00Z",
    latest_scan: null,
    recent_scans: [],
    recent_events: [],
  };
  const topology = {
    nodes: [
      {
        id: "scope:1",
        kind: "subnet",
        label: "Home · 192.168.1.0/24",
        status: "group",
        last_observed_at: null,
      },
      {
        id: "device:1",
        kind: "device",
        device_id: 1,
        label: "Desk",
        status: "online",
        identity_confidence: "observed_mac",
        last_observed_at: "2026-09-27T00:00:00Z",
        addresses: ["192.168.1.7"],
      },
    ],
    links: [
      {
        source: "scope:1",
        target: "device:1",
        kind: "inferred",
        provenance: "IP observed in approved subnet; physical link unknown",
      },
    ],
    legend: { inferred: "Subnet link inferred from IP" },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url === "/health"
            ? { status: "ok" }
            : url.endsWith("bootstrap-status")
              ? { needs_setup: false }
              : url.endsWith("/auth/me")
                ? { username: "owner" }
                : url.endsWith("/overview")
                  ? overview
                  : topology,
      }),
    ),
  );
  render(<App />);
  expect(await screen.findByText("Observed devices")).toBeTruthy();
  expect(screen.getByText("Inventory snapshot")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Network map" }));
  expect(await screen.findByText("Devices in map")).toBeTruthy();
  expect(screen.getByText(/Dashed links are inferred/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Desk/ }));
  expect(await screen.findByRole("heading", { name: "Desk" })).toBeTruthy();
  expect(
    screen.getByText(/No switch, router, or Wi-Fi link was verified/),
  ).toBeTruthy();
});

test("empty map explains how to populate it", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url === "/health"
            ? { status: "ok" }
            : url.endsWith("bootstrap-status")
              ? { needs_setup: false }
              : url.endsWith("/auth/me")
                ? { username: "owner" }
                : url.endsWith("/overview")
                  ? {
                      device_count: 0,
                      online_count: 0,
                      review_count: 0,
                      offline_count: 0,
                      active_alert_count: 0,
                      updated_at: null,
                      latest_scan: null,
                      recent_scans: [],
                      recent_events: [],
                    }
                  : url.endsWith("/scopes")
                    ? []
                    : url.endsWith("/profiles")
                      ? [
                          {
                            id: 1,
                            name: "Default",
                            description: "",
                            scope_count: 0,
                            created_at: "2026-09-27T00:00:00Z",
                          },
                        ]
                      : url.endsWith("/settings")
                        ? {
                            schedule_enabled: false,
                            interval_minutes: 30,
                            offline_threshold: 2,
                            retention_days: 30,
                          }
                        : url.includes("/scans")
                          ? { items: [], total: 0, limit: 1, offset: 0 }
                          : {
                              nodes: [],
                              links: [],
                              legend: { inferred: "No physical link verified" },
                            },
      }),
    ),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Network map" }));
  expect(await screen.findByText("No observed devices yet")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Go to Settings" }));
  expect(await screen.findByText("Network scopes")).toBeTruthy();
});
