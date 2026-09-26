import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => vi.unstubAllGlobals());

test("shows backend health", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url === "/health" ? { status: "ok" } : { needs_setup: true },
      }),
    ),
  );
  render(<App />);
  expect(await screen.findByText("Create administrator")).toBeTruthy();
});
