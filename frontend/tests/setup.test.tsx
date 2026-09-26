import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("setup leads to approved-scope form without showing fake devices", async () => {
  const fetchMock = vi.fn().mockImplementation((url: string) =>
    Promise.resolve({
      ok: true,
      json: async () =>
        url === "/health"
          ? { status: "ok" }
          : url.endsWith("bootstrap-status")
            ? { needs_setup: true }
            : url.endsWith("bootstrap")
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
                : url.includes("/scans")
                  ? { items: [], total: 0, limit: 1, offset: 0 }
                  : [],
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Username"), {
    target: { value: "owner" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "a-long-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(await screen.findByText("Ready to discover")).toBeTruthy();
  expect(screen.queryByText("Device online")).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "Configure network scope" }),
  );
  expect(await screen.findByText("Network scopes")).toBeTruthy();
  expect(screen.getByLabelText("Private IPv4 CIDR")).toBeTruthy();
});

test("discovery requires a visible confirmation before queuing", async () => {
  const scope = {
    id: 1,
    name: "Home",
    cidr: "192.168.1.0/24",
    enabled: true,
    approved_at: "2026-09-27T00:00:00Z",
    max_concurrency: 32,
    connect_timeout_ms: 1000,
    ports: [22, 80, 443],
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
                    ? [scope]
                    : url.includes("/scans") && options?.method === "POST"
                      ? { id: 1, scope_id: 1, status: "queued", host_count: 0 }
                      : { items: [], total: 0, limit: 1, offset: 0 },
      }),
    );
  vi.stubGlobal("fetch", fetchMock);
  const confirm = vi.fn(() => false);
  vi.stubGlobal("confirm", confirm);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Settings" }));
  fireEvent.click(await screen.findByRole("button", { name: "Run discovery" }));
  expect(confirm).toHaveBeenCalledOnce();
  expect(
    fetchMock.mock.calls.filter(
      ([url, options]) => url === "/api/v1/scans" && options?.method === "POST",
    ),
  ).toHaveLength(0);
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Run discovery" }));
  expect(await screen.findByText(/Run #1:/)).toBeTruthy();
});
