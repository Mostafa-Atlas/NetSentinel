import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("inventory opens evidence and saves an owner label", async () => {
  const device = {
    id: 1,
    display_name: "10.0.0.7",
    identity_confidence: "observed_mac",
    known_state: "unknown",
    notes: "",
    first_seen_at: "2026-09-27T00:00:00Z",
    last_seen_at: "2026-09-27T00:00:00Z",
    last_observed_at: "2026-09-27T00:00:00Z",
    status: "online",
    addresses: [
      {
        ip: "10.0.0.7",
        mac: "aa:bb:cc:dd:ee:ff",
        hostname: null,
        first_seen_at: "2026-09-27T00:00:00Z",
        last_seen_at: "2026-09-27T00:00:00Z",
      },
    ],
  };
  const fetchMock = vi
    .fn()
    .mockImplementation((url: string, options?: RequestInit) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url === "/health"
            ? { status: "ok" }
            : url.endsWith("bootstrap-status")
              ? { needs_setup: false }
              : url.endsWith("/auth/me")
                ? { username: "owner" }
                : url.includes("/devices?")
                  ? { items: [device], total: 1, limit: 100, offset: 0 }
                  : url.endsWith("/devices/1/identity-review")
                    ? {
                        device_id: 1,
                        candidates: [],
                        addresses: [
                          { id: 1, ip: "10.0.0.7", mac: "aa:bb:cc:dd:ee:ff" },
                        ],
                      }
                    : url.endsWith("/devices/1/check-rules") &&
                        options?.method === "POST"
                      ? {
                          id: 1,
                          device_id: 1,
                          port: 80,
                          enabled: true,
                          failure_threshold: 2,
                        }
                      : url.endsWith("/devices/1/check-rules")
                        ? []
                        : url.endsWith("/devices/1/agent-enrollments") &&
                            options?.method === "POST"
                          ? {
                              id: 1,
                              device_id: 1,
                              name: "Desk agent",
                              token: "one-time-test-token",
                              created_at: "2026-09-27T00:00:00Z",
                              expires_at: "2026-12-27T00:00:00Z",
                              revoked_at: null,
                            }
                          : url.endsWith("/devices/1/agent-enrollments")
                            ? []
                            : url.includes("/devices/1/agent-reports?")
                              ? { items: [], total: 0 }
                              : url.includes("/devices/1/hints?")
                                ? {
                                    items: [
                                      {
                                        id: 1,
                                        scan_run_id: 1,
                                        ip: "10.0.0.7",
                                        source: "mdns",
                                        kind: "hostname",
                                        value: "desk.local",
                                        confidence: "unverified_advertisement",
                                        observed_at: "2026-09-27T00:00:00Z",
                                      },
                                    ],
                                    total: 1,
                                  }
                                : url.endsWith(
                                      "/devices/1/observations?limit=30",
                                    )
                                  ? {
                                      items: [
                                        {
                                          id: 1,
                                          scan_run_id: 1,
                                          observed_at: "2026-09-27T00:00:00Z",
                                          source: "tcp",
                                          reachable: true,
                                          latency_ms: 4,
                                          raw_summary: "Mocked connect",
                                        },
                                      ],
                                      total: 1,
                                    }
                                  : url.includes("/services?")
                                    ? { items: [], total: 0 }
                                    : url.includes("/events?device_id=1")
                                      ? {
                                          items: [
                                            {
                                              id: 5,
                                              summary: "New device observed",
                                              event_type: "alert_triggered",
                                              actor: "system",
                                              occurred_at:
                                                "2026-09-27T00:00:00Z",
                                              evidence_ref: "alert:1",
                                            },
                                          ],
                                          total: 1,
                                        }
                                      : url.endsWith("/devices/1") &&
                                          options?.method === "PATCH"
                                        ? {
                                            ...device,
                                            display_name: "Desk",
                                            known_state: "known",
                                          }
                                        : device,
      }),
    );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Devices" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open 10.0.0.7" }));
  expect(
    await screen.findByText("Observed MAC aa:bb:cc:dd:ee:ff"),
  ).toBeTruthy();
  expect(screen.getByText("Reachability evidence")).toBeTruthy();
  expect(screen.getByText("desk.local")).toBeTruthy();
  expect(screen.getByText(/MDNS · unverified/)).toBeTruthy();
  expect(screen.getByText("Device events")).toBeTruthy();
  expect(screen.getByText("Service check rules")).toBeTruthy();
  expect(screen.getByText("Optional host agent")).toBeTruthy();
  expect(screen.getByText("New device observed")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Alerts"), {
    target: { value: "open" },
  });
  expect(
    fetchMock.mock.calls.some(([url]) =>
      String(url).includes("alert_filter=open"),
    ),
  ).toBe(true);
  fireEvent.change(screen.getByLabelText("Display name"), {
    target: { value: "Desk" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save details" }));
  expect(await screen.findByText("Device details saved.")).toBeTruthy();
  expect(
    fetchMock.mock.calls.some(
      ([url, options]) =>
        url === "/api/v1/devices/1" && options?.method === "PATCH",
    ),
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Add check rule" }));
  expect(await screen.findByText(/TCP 80 rule added/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "Desk agent" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Create agent credential" }),
  );
  expect(await screen.findByText("one-time-test-token")).toBeTruthy();
});
