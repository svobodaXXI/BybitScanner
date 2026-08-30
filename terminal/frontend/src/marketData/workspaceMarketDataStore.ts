import type { MarketDataSnapshot } from "../contracts/marketData";
import { createDemoMarketData } from "./demoFeed";
import type { MarketDataPort } from "./marketDataStore";
import { BYBIT_INTERVAL_BY_TIMEFRAME, type ChartTimeframe } from "./timeframes";
import { applyWorkspaceEvent, type WorkspaceProjectionState } from "./workspaceProjection";

type SocketFactory = (url: string) => WebSocket;

const initialSnapshot = (): MarketDataSnapshot => ({
  ...createDemoMarketData(),
  book: {
    symbol: "ONGUSDT", bids: [], asks: [], health: "NOT_READY",
    receivedAt: "", availableDepth: 0,
  },
  candles: [],
  tickSize: null,
  trades: [],
  ownOrders: [],
});

const websocketUrl = (path: string): string => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
};

const workspaceStreamPath = (
  symbol: string,
  interval: string,
  streamId?: string,
  afterSequence?: number,
): string => {
  const query = new URLSearchParams({ symbol, interval });
  if (streamId && afterSequence !== undefined) {
    query.set("stream_id", streamId);
    query.set("after_sequence", String(afterSequence));
  }
  return `/api/workspace/stream?${query}`;
};

export class BackendWorkspaceMarketDataStore implements MarketDataPort {
  private symbol = "ONGUSDT";
  private timeframe: ChartTimeframe = "5m";
  private projection: WorkspaceProjectionState = { authority: null, snapshot: initialSnapshot() };
  private listeners = new Set<() => void>();
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private started = false;

  constructor(private readonly socketFactory: SocketFactory = (url) => new WebSocket(url)) {}

  start = () => {
    if (this.started) return;
    this.started = true;
    this.connect(true);
  };

  dispose = () => {
    this.started = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  };

  getSnapshot = () => this.projection.snapshot;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setTimeframe = (timeframe: ChartTimeframe) => {
    if (timeframe === this.timeframe) return;
    this.timeframe = timeframe;
    this.replaceConnection(false);
  };

  setSymbol = (symbol: string) => {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized || normalized === this.symbol) return;
    this.symbol = normalized;
    this.replaceConnection(false);
  };

  private connect(allowResume: boolean) {
    if (!this.started) return;
    const symbol = this.symbol;
    const interval = BYBIT_INTERVAL_BY_TIMEFRAME[this.timeframe];
    const authority = allowResume
      && this.projection.authority?.symbol === symbol
      && this.projection.authority.interval === interval
      ? this.projection.authority
      : null;
    const path = workspaceStreamPath(
      symbol, interval,
      authority?.streamId,
      authority?.eventSequence,
    );
    const socket = this.socketFactory(websocketUrl(path));
    this.socket = socket;

    socket.onmessage = (message) => {
      if (this.socket !== socket || this.symbol !== symbol
        || BYBIT_INTERVAL_BY_TIMEFRAME[this.timeframe] !== interval) return;
      let event: unknown;
      try {
        event = JSON.parse(String(message.data));
      } catch {
        this.requireFreshSnapshot(socket);
        return;
      }
      const result = applyWorkspaceEvent(this.projection, event, symbol, interval);
      if (result.decision === "RESNAPSHOT_REQUIRED") {
        this.requireFreshSnapshot(socket);
        return;
      }
      if (result.decision === "IGNORED_STALE") return;
      this.projection = result.state;
      this.emit();
    };

    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.markDisconnected();
      this.scheduleReconnect(true);
    };
  }

  private requireFreshSnapshot(socket: WebSocket) {
    if (this.socket !== socket) return;
    this.socket = null;
    socket.close();
    this.projection = {
      authority: null,
      snapshot: {
        ...this.projection.snapshot,
        book: { ...this.projection.snapshot.book, health: "DEGRADED" },
        workspace: undefined,
      },
    };
    this.emit();
    this.scheduleReconnect(false);
  }

  private replaceConnection(allowResume: boolean) {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    if (this.started) this.connect(allowResume);
  }

  private scheduleReconnect(allowResume: boolean) {
    if (!this.started) return;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect(allowResume);
    }, 1000);
  }

  private markDisconnected() {
    this.projection = {
      ...this.projection,
      snapshot: {
        ...this.projection.snapshot,
        book: { ...this.projection.snapshot.book, health: "STALE" },
      },
    };
    this.emit();
  }

  private emit() {
    for (const listener of this.listeners) listener();
  }
}
