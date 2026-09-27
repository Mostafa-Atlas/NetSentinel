import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("scheduled monitoring and a port policy require explicit opt-in", async () => {
  const scope = {
    id: 1,
    name: "Home",
    cidr: "192.168.1.0/24",
    enabled: true,
    approved_at: "2026-09-27T00:00:00Z",
    profile_id: 1,
    max_concurrency: 32,
    connect_timeout_ms: 1000,
    ports: [22, 80, 443],
  };
  const settings = {
    schedule_enabled: false,
    interval_minutes: 30,
    offline_threshold: 2,
    retention_days: 30,
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
                : url.endsWith("/scopes")
                  ? [scope]
                  : url.endsWith("/profiles")
                    ? [
                        {
                          id: 1,
                          name: "Default",
                          description: "",
                          scope_count: 1,
                          created_at: "2026-09-27T00:00:00Z",
                        },
                      ]
                    : url.endsWith("/scopes/1") && options?.method === "PATCH"
                      ? scope
                      : url.endsWith("/settings")
                        ? settings
                        : { items: [], total: 0, limit: 1, offset: 0 },
      }),
    );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Settings" }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit policy" }));
  fireEvent.change(screen.getByLabelText("TCP ports, comma separated"), {
    target: { value: "22, 8080" },
  });
  const policySave = screen.getByRole("button", { name: "Save probe policy" });
  expect(policySave.hasAttribute("disabled")).toBe(true);
  fireEvent.click(
    screen.getByLabelText(
      "I approve this bounded probe policy for this range.",
    ),
  );
  fireEvent.click(policySave);
  expect(await screen.findByText("Probe policy saved.")).toBeTruthy();
  expect(
    fetchMock.mock.calls.some(
      ([url, options]) =>
        url === "/api/v1/scopes/1" &&
        JSON.parse(String(options?.body)).ports[1] === 8080,
    ),
  ).toBe(true);
  fireEvent.click(
    screen.getByLabelText(
      "Run discovery automatically on approved enabled ranges",
    ),
  );
  fireEvent.change(screen.getByLabelText("Minutes between scans"), {
    target: { value: "15" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save monitoring settings" }),
  );
  expect(await screen.findByText("Monitoring settings saved.")).toBeTruthy();
  expect(
    fetchMock.mock.calls.some(
      ([url, options]) =>
        url === "/api/v1/settings" &&
        options?.method === "PATCH" &&
        JSON.parse(String(options.body)).schedule_enabled === true,
    ),
  ).toBe(true);
});
