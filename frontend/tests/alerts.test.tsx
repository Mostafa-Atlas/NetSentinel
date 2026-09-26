import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Alerts } from "../src/features/alerts/Alerts";
import { Timeline } from "../src/features/timeline/Timeline";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("an owner can acknowledge an evidence-backed alert and inspect its device", async () => {
  let status = "active";
  const alert = {
    id: 7,
    device_id: 4,
    device_name: "Desk",
    rule_key: "new_device",
    severity: "attention",
    summary: "New device observed: Desk",
    details: "192.168.1.7 responded during scan #3; identity needs review.",
    evidence_ref: "observation:9",
    created_at: "2026-09-27T00:00:00Z",
    last_seen_at: "2026-09-27T00:00:00Z",
    acknowledged_at: null,
    resolved_at: null,
  };
  const fetchMock = vi
    .fn()
    .mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith("/acknowledge") && options?.method === "POST")
        status = "acknowledged";
      return Promise.resolve({
        ok: true,
        json: async () =>
          url.endsWith("/acknowledge")
            ? { ...alert, status }
            : { items: [{ ...alert, status }], total: 1, limit: 20, offset: 0 },
      });
    });
  vi.stubGlobal("fetch", fetchMock);
  const onDevice = vi.fn();
  render(<Alerts onDevice={onDevice} />);
  expect(await screen.findByText("New device observed: Desk")).toBeTruthy();
  expect(screen.getByText(/observation:9/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Inspect Desk" }));
  expect(onDevice).toHaveBeenCalledWith(4);
  fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
  expect(await screen.findByText("acknowledged")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Acknowledge" })).toBeNull();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/alerts/7/acknowledge",
    expect.objectContaining({ method: "POST" }),
  );
});

test("empty alert and timeline views explain what will appear", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 30, offset: 0 }),
    }),
  );
  const onDevice = vi.fn();
  const { unmount } = render(<Alerts onDevice={onDevice} />);
  expect(await screen.findByText(/No open alerts/)).toBeTruthy();
  unmount();
  render(<Timeline onDevice={onDevice} />);
  expect(await screen.findByText(/No events yet/)).toBeTruthy();
});

test("timeline gives each change a timestamp, source and device link", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            id: 3,
            device_id: 4,
            event_type: "alert_triggered",
            actor: "system",
            summary: "New device observed: Desk",
            evidence_ref: "alert:7",
            occurred_at: "2026-09-27T00:00:00Z",
          },
        ],
        total: 1,
        limit: 30,
        offset: 0,
      }),
    }),
  );
  const onDevice = vi.fn();
  render(<Timeline onDevice={onDevice} />);
  expect(await screen.findByText("New device observed: Desk")).toBeTruthy();
  expect(screen.getByText(/alert triggered · system/)).toBeTruthy();
  expect(screen.getByText(/alert:7/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Inspect device" }));
  expect(onDevice).toHaveBeenCalledWith(4);
});
