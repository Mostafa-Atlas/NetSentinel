import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => vi.unstubAllGlobals());

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
