import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppVersionControl } from "./AppVersionControl";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("lightweight local version control", () => {
  it("reads installed version once, never polls GitHub on mount or render", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      installed_sha: "a".repeat(40), build_status: "MANIFEST_HASH_MATCH",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AppVersionControl />);
    expect(await screen.findByText(/Версия: aaaaaaaaaaaa/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/local-replay/app-version", expect.objectContaining({
      method: "GET", cache: "no-store",
    }));
  });

  it("checks GitHub only after the owner clicks and does not install", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/local-replay/app-version") return new Response(JSON.stringify({
        installed_sha: null, build_status: "UNVERIFIED",
      }));
      return new Response(JSON.stringify({
        status: "PUBLISHED_CANDIDATE", available_sha: "b".repeat(40),
      }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AppVersionControl />);
    await screen.findByText("Версия: не определена");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Проверить обновления" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Автоустановка ещё не подключена");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/local-replay/update/check", expect.objectContaining({
        method: "POST",
        headers: { "X-Local-Update-Check": "1" },
      }),
    );
  });
});
