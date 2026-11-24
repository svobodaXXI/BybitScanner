import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

const paper = {
  ok: true, active_account_id: "paper", session_generation: 1,
  accounts: [{ id: "paper", display_name: "Paper / Virtual", provider: "PAPER", environment: "PAPER", status: "READY" }],
};

afterEach(() => vi.unstubAllGlobals());

describe("manual MAIN account provisioning failures", () => {
  it("shows sanitized owner-actionable gateway status without echoing credentials", async () => {
    for (const { status, expected } of [
      { status: 401, expected: "Terminal session expired" },
      { status: 413, expected: "request size" },
      { status: 502, expected: "HTTP 502" },
    ]) {
      const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
        if (url === "/api/accounts") return { ok: true, json: async () => paper };
        if (url === "/api/manual-main/accounts" && options?.method === "POST") {
          return {
            ok: false, status,
            json: async () => { throw new SyntaxError("gateway returned HTML"); },
          };
        }
        if (url === "/api/manual-main/accounts") {
          return { ok: true, json: async () => ({ ok: true, accounts: [] }) };
        }
        throw new Error("unexpected endpoint");
      });
      vi.stubGlobal("fetch", fetchMock);
      const { unmount } = render(<AccountMenu open onToggle={vi.fn()} mode="TERMINAL" selectedAccountId="paper" />);
      await screen.findByText("Current");
      fireEvent.click(screen.getByRole("button", { name: "+ Add New Account" }));
      fireEvent.click(screen.getByRole("button", { name: "Bybit MAIN · Real account" }));
      for (const [label, value] of [
        ["Account name", "Main"], ["API Key", "private-key"], ["API Secret", "private-secret"],
      ]) {
        fireEvent.change(screen.getByLabelText(label), { target: { value } });
      }
      const submit = screen.getByRole("button", { name: "Add Account" });
      expect(submit).toHaveClass("account-add-submit-button");
      fireEvent.click(submit);
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(expected);
      expect(alert).not.toHaveTextContent("private-key");
      expect(alert).not.toHaveTextContent("private-secret");
      expect(fetchMock.mock.calls.some(([url, options]) =>
        url === "/api/manual-main/accounts" && options?.method === "POST")).toBe(true);
      unmount();
    }
  });
});
