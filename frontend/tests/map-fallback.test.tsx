import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { NetworkMap } from "../src/features/map/NetworkMap";

vi.mock("cytoscape", () => ({
  default: () => {
    throw new Error("Canvas unavailable");
  },
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("device list remains usable when graph rendering fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [
          {
            id: "device:1",
            kind: "device",
            label: "Desk",
            status: "online",
            identity_confidence: "provisional",
            last_observed_at: null,
            addresses: ["10.0.0.7"],
          },
        ],
        links: [],
        legend: { inferred: "No physical path verified" },
      }),
    }),
  );
  render(<NetworkMap onConfigure={() => undefined} />);
  expect(
    await screen.findByText(
      "Graph rendering is unavailable in this browser. Use the device list to inspect the same observations.",
    ),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Desk/ }));
  expect(screen.getByRole("heading", { name: "Desk" })).toBeTruthy();
});
