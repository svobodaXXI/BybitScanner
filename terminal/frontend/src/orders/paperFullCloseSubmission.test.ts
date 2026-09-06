import { afterEach, describe, expect, it, vi } from "vitest";
import type { CommandMutationResponse, PaperState } from "../contracts/trading";
import { PaperFullCloseSubmissionController } from "./paperFullCloseSubmission";

const PAPER_STATE: PaperState = {
  ok: true,
  state_revision: 1,
  account_id: "paper-main",
  symbol: "BTCUSDT",
  initial_deposit_usdt: "1000",
  equity_usdt: "1000",
  one_wv_usdt: "50",
  position_side: "Flat",
  position_quantity: "0",
  average_entry: null,
  engaged_notional_usdt: "0",
  engaged_wv: "0",
  active_limit_orders: [],
};

const RESULT: CommandMutationResponse = {
  client_action_id: "close-1",
  status: "completed",
  reason_code: "completed",
  message: "completed",
  command_id: "cmd-1",
  reconciliation_required: false,
  paper_state: PAPER_STATE,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PaperFullCloseSubmissionController", () => {
  it("deduplicates the semantic close and allocates one durable client_action_id", async () => {
    let resolveFetch!: (value: Response) => void;
    const fetchPromise = new Promise<Response>((done) => { resolveFetch = done; });
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      () => fetchPromise,
    );
    vi.stubGlobal("fetch", fetchMock);
    const createClientActionId = vi.fn(() => "close-1");
    const runMutation = async <T>(_key: string, mutation: () => Promise<T>): Promise<T> => mutation();
    const runMutationSpy = vi.fn(runMutation);
    const applyPaperState = vi.fn(() => true);
    const controller = new PaperFullCloseSubmissionController();
    const dependencies = { createClientActionId, applyPaperState, runMutation: runMutationSpy as typeof runMutation };

    const first = controller.submit({ symbol: "BTCUSDT" }, dependencies);
    const duplicate = controller.submit({ symbol: "BTCUSDT" }, dependencies);

    expect(duplicate).toBe(first);
    expect(createClientActionId).toHaveBeenCalledTimes(1);
    expect(runMutationSpy).toHaveBeenCalledTimes(1);
    expect(runMutationSpy).toHaveBeenCalledWith("FULL_CLOSE", expect.any(Function));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      client_action_id: "close-1",
      symbol: "BTCUSDT",
    });

    resolveFetch(new Response(JSON.stringify(RESULT), { status: 200 }));
    await expect(first).resolves.toEqual(RESULT);
    expect(applyPaperState).toHaveBeenCalledWith(PAPER_STATE);
  });

  it("fails closed when completed state is rejected by the current PAPER session", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify(RESULT), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const applyPaperState = vi.fn(() => false);
    const controller = new PaperFullCloseSubmissionController();

    const attempt = controller.submit(
      { symbol: "BTCUSDT" },
      {
        createClientActionId: () => "close-stale-session",
        applyPaperState,
        runMutation: async <T>(_key: string, mutation: () => Promise<T>) => mutation(),
      },
    );

    await expect(attempt).rejects.toThrow("paper_full_close_authoritative_state_rejected");
    expect(applyPaperState).toHaveBeenCalledOnce();
    expect(applyPaperState).toHaveBeenCalledWith(PAPER_STATE);
  });

  it("releases ownership after completion", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify(RESULT), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    let id = 0;
    const controller = new PaperFullCloseSubmissionController();
    const dependencies = {
      createClientActionId: () => `close-${++id}`,
      applyPaperState: () => true,
      runMutation: async <T>(_key: string, mutation: () => Promise<T>) => mutation(),
    };

    await controller.submit({ symbol: "BTCUSDT" }, dependencies);
    await controller.submit({ symbol: "BTCUSDT" }, dependencies);

    expect(id).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clear lets a replacement own the same semantic close while an old completion arrives later", async () => {
    let resolveOld!: (value: Response) => void;
    let resolveNew!: (value: Response) => void;
    const oldFetch = new Promise<Response>((done) => { resolveOld = done; });
    const newFetch = new Promise<Response>((done) => { resolveNew = done; });
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockImplementationOnce(() => oldFetch)
      .mockImplementationOnce(() => newFetch);
    vi.stubGlobal("fetch", fetchMock);
    let id = 0;
    const controller = new PaperFullCloseSubmissionController();
    const dependencies = {
      createClientActionId: () => `close-${++id}`,
      applyPaperState: () => true,
      runMutation: async <T>(_key: string, mutation: () => Promise<T>) => mutation(),
    };

    const oldAttempt = controller.submit({ symbol: "BTCUSDT" }, dependencies);
    controller.clear();
    const replacement = controller.submit({ symbol: "BTCUSDT" }, dependencies);
    expect(id).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    resolveOld(new Response(JSON.stringify({ ...RESULT, client_action_id: "close-1" }), { status: 200 }));
    await oldAttempt;

    const duplicate = controller.submit({ symbol: "BTCUSDT" }, dependencies);
    expect(duplicate).toBe(replacement);
    expect(id).toBe(2);

    resolveNew(new Response(JSON.stringify({ ...RESULT, client_action_id: "close-2" }), { status: 200 }));
    await replacement;
  });
});
