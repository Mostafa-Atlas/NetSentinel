import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/main";

afterEach(() => vi.unstubAllGlobals());

test("shows backend health", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ json: async () => ({ status: "ok" }) }),
  );
  render(<App />);
  expect(await screen.findByText("API connected")).toBeTruthy();
});
