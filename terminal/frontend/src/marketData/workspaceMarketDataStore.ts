import type { MarketDataSnapshot } from "../contracts/marketData";
import { createDemoMarketData } from "./demoFeed";
import type { MarketDataPort } from "./marketDataStore";
import { BYBIT_INTERVAL_BY_TIMEFRAME, type ChartTimeframe } from "./timeframes";
import { applyWorkspaceEvent, type WorkspaceProjectionState } from "./workspaceProjection";

type SocketFactory = (url: string) => WebSocket;

// A silent socket may never deliver onclose. Bound one recovery attempt
// during symbol navigation; normal reconnect/resnapshot remains unchanged.
export const FIRST_SNAPSHOT_DEADLINE_MS = 2000;
type NavigationTransport = {
  attempts: number; opens: number; closes: number; rejected: number; timeouts: number;
};

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
  private expectedGeneration: number | null = null;
  private projection: WorkspaceProjectionState = { authority: null, snapshot: initialSnapshot() };
  private listeners = new Set<() => void>();
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private started = false;
  private fastSwitchRetryAvailable = false;
  private firstSnapshotTimer: ReturnType<typeof setTimeout> | null = null;
  private firstSnapshotRecoveryAvailable = false;
  private navigationTransport: NavigationTransport | null = null;
  private awaitingFirstSnapshot = false;

  constructor(private readonly socketFactory: SocketFactory = (url) => new WebSocket(url)) {}

  start = () => {
    if (this.started) return;
    this.started = true;
    this.connect(true);
  };

  dispose = () => {
    this.started = false;
    this.clearFirstSnapshotTimer();
    this.firstSnapshotRecoveryAvailable = false;
    this.awaitingFirstSnapshot = false;
    this.navigationTransport = null;
    this.fastSwitchRetryAvailable = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  };

  getSnapshot = () => this.projection.snapshot;

  getNavigationTransportTiming = () => {
    const value = this.navigationTransport;
    return value ? `WS ${value.attempts} попыток / ${value.opens} открытий / ${value.closes} закрытий / ${value.rejected} отклонений / ${value.timeouts} тайм-аутов` : null;
  };

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setTimeframe = (timeframe: ChartTimeframe) => {
    if (timeframe === this.timeframe) return;
    this.timeframe = timeframe;
    this.awaitingFirstSnapshot = false;
    this.firstSnapshotRecoveryAvailable = false;
    this.navigationTransport = null;
    this.fastSwitchRetryAvailable = false;
    this.replaceConnection(false);
  };

  setSymbol = (symbol: string, generation?: number) => {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized || normalized === this.symbol) return;
    this.symbol = normalized;
    this.expectedGeneration = Number.isInteger(generation) && Number(generation) > 0
      ? Number(generation) : null;
    // The activation ACK can precede the selected interval's first snapshot.
    // Permit one faster retry, then return to the normal reconnect cadence.
    this.fastSwitchRetryAvailable = true;
    this.awaitingFirstSnapshot = true;
    this.firstSnapshotRecoveryAvailable = true;
    this.navigationTransport = { attempts: 0, opens: 0, closes: 0, rejected: 0, timeouts: 0 };
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
    if (this.awaitingFirstSnapshot && this.navigationTransport) this.navigationTransport.attempts++;
    socket.onopen = () => {
      if (this.socket === socket && this.awaitingFirstSnapshot && this.navigationTransport) this.navigationTransport.opens++;
    };
    if (this.awaitingFirstSnapshot && this.firstSnapshotRecoveryAvailable) {
      this.firstSnapshotTimer = setTimeout(() => {
        this.firstSnapshotTimer = null;
        if (this.socket !== socket || !this.awaitingFirstSnapshot) return;
        this.firstSnapshotRecoveryAvailable = false;
        this.fastSwitchRetryAvailable = false;
        if (this.navigationTransport) this.navigationTransport.timeouts++;
        this.markDisconnected();
        this.replaceConnection(false);
      }, FIRST_SNAPSHOT_DEADLINE_MS);
    }

    socket.onmessage = (message) => {
      if (this.socket !== socket || this.symbol !== symbol
        || BYBIT_INTERVAL_BY_TIMEFRAME[this.timeframe] !== interval) return;
      let event: unknown;
      try {
        event = JSON.parse(String(message.data));
      } catch {
        if (this.awaitingFirstSnapshot && this.navigationTransport) this.navigationTransport.rejected++;
        this.requireFreshSnapshot(socket);
        return;
      }
      const result = applyWorkspaceEvent(
        this.projection, event, symbol, interval, Date.now(), this.expectedGeneration,
      );
      if (result.decision !== "APPLIED" && this.awaitingFirstSnapshot && this.navigationTransport) this.navigationTransport.rejected++;
      if (result.decision === "RESNAPSHOT_REQUIRED") {
        this.requireFreshSnapshot(socket);
        return;
      }
      if (result.decision === "IGNORED_STALE") return;
      if (this.awaitingFirstSnapshot) {
        this.clearFirstSnapshotTimer();
        this.awaitingFirstSnapshot = false;
        this.firstSnapshotRecoveryAvailable = false;
      }
      this.fastSwitchRetryAvailable = false;
      this.projection = result.state;
      this.emit();
    };

    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.clearFirstSnapshotTimer();
      if (this.awaitingFirstSnapshot && this.navigationTransport) this.navigationTransport.closes++;
      this.markDisconnected();
      const delayMs = this.fastSwitchRetryAvailable ? 250 : 1000;
      this.fastSwitchRetryAvailable = false;
      this.scheduleReconnect(true, delayMs);
    };
  }

  private requireFreshSnapshot(socket: WebSocket) {
    if (this.socket !== socket) return;
    this.clearFirstSnapshotTimer();
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
    this.fastSwitchRetryAvailable = false;
    this.scheduleReconnect(false);
  }

  private clearFirstSnapshotTimer() {
    if (this.firstSnapshotTimer !== null) clearTimeout(this.firstSnapshotTimer);
    this.firstSnapshotTimer = null;
  }

  private replaceConnection(allowResume: boolean) {
    this.clearFirstSnapshotTimer();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    if (this.started) this.connect(allowResume);
  }

  private scheduleReconnect(allowResume: boolean, delayMs = 1000) {
    if (!this.started) return;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect(allowResume);
    }, delayMs);
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
