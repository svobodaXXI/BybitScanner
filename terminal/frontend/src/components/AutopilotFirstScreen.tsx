import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  type AutopilotModeState,
  type DiaryTradeSummaryRow,
  type Loadable,
  loadAutopilotMode,
  loadDiaryTrades,
  loadOpenPositions,
  loadRobotDaySummary,
  type RobotDaySummary,
  loadRuntimeHealth,
  type PositionProtection,
  type RuntimeHealth,
  uniqueOpenEpisodeId,
} from "../autopilot/autopilotFirstScreenData";
import type { PaperOpenPosition } from "../contracts/trading";
import {
  formatPositionPnlPercent,
  formatPositionPrice,
  positionPnlPercent,
} from "../marketData/positionPnl";
import "./AutopilotFirstScreen.css";

/**
 * AUTOPILOT first screen (UI-1): read-only summary and open-trade cards.
 *
 * Refresh is explicit (mount + button): every request is served by the PAPER
 * owner thread, so this screen must not add a background polling load to a
 * running PAPER_AUTO session.
 */

const NO_SOURCE = "Нет источника данных";

async function settle<T>(load: () => Promise<T>): Promise<Loadable<T>> {
  try {
    return { status: "ready", value: await load() };
  } catch {
    return { status: "error" };
  }
}

function formatUsdt(value: number) {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)} USDT`;
}

function SummaryItem({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="autopilot-summary-item">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Missing({ source }: { source?: string }) {
  return (
    <span className="autopilot-missing" title={source}>
      {NO_SOURCE}
    </span>
  );
}

function LoadState<T>({
  value,
  render,
}: {
  value: Loadable<T>;
  render: (value: T) => ReactNode;
}) {
  if (value.status === "loading")
    return <span className="autopilot-loading">Загрузка…</span>;
  if (value.status === "error")
    return <span className="autopilot-error">Данные недоступны</span>;
  return <>{render(value.value)}</>;
}

export function PositionCard({
  position,
  protection,
  entryBasis,
  episodeId,
  onTradeDetails,
}: {
  position: PaperOpenPosition;
  protection: PositionProtection;
  entryBasis: Loadable<string | null>;
  episodeId: string | null;
  onTradeDetails?: (episodeId: string) => void;
}) {
  const side = position.position_side === "Long" ? "LONG" : "SHORT";
  const pnl =
    position.unrealized_pnl === null
      ? Number.NaN
      : Number(position.unrealized_pnl);
  const pnlPercent = positionPnlPercent(
    position.position_side,
    position.average_entry === null ? null : Number(position.average_entry),
    position.current_price === null ? null : Number(position.current_price),
  );
  const price = (value: string | null) =>
    value === null ? "—" : formatPositionPrice(value, position.tick_size);

  return (
    <article
      className="autopilot-trade-card"
      aria-label={`Сделка ${position.symbol}`}
    >
      <header>
        <strong>{position.symbol}</strong>
        <span
          className={
            side === "LONG" ? "autopilot-side-long" : "autopilot-side-short"
          }
        >
          {side}
        </span>
      </header>
      <dl>
        <SummaryItem label="Объём">
          {position.position_quantity} ·{" "}
          {Number(position.engaged_notional_usdt).toFixed(2)} USDT
        </SummaryItem>
        <SummaryItem label="Live PnL">
          {Number.isFinite(pnl) ? (
            <>
              {formatUsdt(pnl)}
              {pnlPercent === null
                ? null
                : ` (${formatPositionPnlPercent(pnlPercent)})`}
            </>
          ) : (
            <span className="autopilot-error">Нет текущей цены</span>
          )}
        </SummaryItem>
        <SummaryItem label="STOP">
          <LoadState
            value={protection}
            render={(value) =>
              value?.stop_loss ? (
                price(value.stop_loss)
              ) : (
                <span className="autopilot-error">Не установлен</span>
              )
            }
          />
        </SummaryItem>
        <SummaryItem label="TAKE">
          <LoadState
            value={protection}
            render={(value) =>
              value?.take_profit ? (
                price(value.take_profit)
              ) : (
                <span className="autopilot-error">Не установлен</span>
              )
            }
          />
        </SummaryItem>
        <SummaryItem label="Защита">
          <LoadState
            value={protection}
            render={(value) => value?.status ?? "—"}
          />
        </SummaryItem>
        <SummaryItem label="Основание входа">
          <LoadState
            value={entryBasis}
            render={(value) =>
              value ?? <Missing source="Diary: decision_reason" />
            }
          />
        </SummaryItem>
        <SummaryItem label="Почему удерживается">
          <Missing source="Robot: состояние удержания позиции не публикуется API" />
        </SummaryItem>
      </dl>
      <button
        type="button"
        disabled={!episodeId || !onTradeDetails}
        title={!episodeId ? "Нет однозначной связи с эпизодом сделки" : undefined}
        onClick={() => { if (episodeId) onTradeDetails?.(episodeId); }}
      >
        Подробности сделки
      </button>
    </article>
  );
}

export function AutopilotFirstScreen({
  now = () => Date.now(),
  onOpenPositions,
  accountKey,
  onTradeDetails,
  onStatistics,
  onTerminal,
  accountControl,
  onRobotControls,
}: {
  now?: () => number;
  onOpenPositions?: () => void;
  accountKey?: string;
  onTradeDetails?: (episodeId: string) => void;
  onStatistics?: () => void;
  onTerminal?: () => void;
  accountControl?: ReactNode;
  onRobotControls?: () => void;
}) {
  const [autopilot, setAutopilot] = useState<Loadable<AutopilotModeState>>({
    status: "loading",
  });
  const [health, setHealth] = useState<Loadable<RuntimeHealth>>({
    status: "loading",
  });
  const [positions, setPositions] = useState<Loadable<PaperOpenPosition[]>>({
    status: "loading",
  });
  const [trades, setTrades] = useState<Loadable<DiaryTradeSummaryRow[]>>({
    status: "loading",
  });
  const [robotDay, setRobotDay] = useState<Loadable<RobotDaySummary>>({ status: "loading" });
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const current = ++generation.current;
    const apply =
      <T,>(setter: (value: T) => void) =>
      (value: T) => {
        if (current === generation.current) setter(value);
      };
    setAutopilot({ status: "loading" });
    setHealth({ status: "loading" });
    setPositions({ status: "loading" });
    setTrades({ status: "loading" });
    setRobotDay({ status: "loading" });

    await Promise.all([
      settle(loadAutopilotMode).then(apply(setAutopilot)),
      settle(loadRuntimeHealth).then(apply(setHealth)),
      settle(() => loadDiaryTrades(accountKey)).then(apply(setTrades)),
      settle(loadRobotDaySummary).then(apply(setRobotDay)),
      settle(loadOpenPositions).then(apply(setPositions)),
    ]);
  }, [accountKey]);

  useEffect(() => {
    void refresh();
    return () => {
      generation.current += 1;
    };
  }, [refresh]);

  const backendOffline =
    health.status === "error" &&
    autopilot.status === "error" &&
    positions.status === "error";

  return (
    <section
      className="autopilot-first-screen"
      aria-label="Автопилот: первый экран"
    >
      {backendOffline ? (
        <p className="autopilot-error" role="alert">
          PAPER backend недоступен. Запустите runtime ярлыком «Запуск робота».
        </p>
      ) : null}

      <dl className="autopilot-summary" aria-label="Сводка дня">
        <SummaryItem label="PnL за день">
          <LoadState
            value={robotDay}
            render={(day) => day.netPnl === null ? (
              <span className="autopilot-missing">
                Нет данных: {day.tradesWithoutPnl} из {day.closedTrades} сделок без полного PnL
              </span>
            ) : (
              <span title="PAPER Robot: закрытые сделки за день (МСК), результат за вычетом записанных комиссий">
                {formatUsdt(day.netPnl)}
              </span>
            )}
          />
        </SummaryItem>
        <SummaryItem label="Сделок за день">
          <LoadState value={robotDay} render={(day) => day.closedTrades} />
        </SummaryItem>
      </dl>

      <nav className="autopilot-utility-stack" aria-label="Панель управления Автопилотом">
        <button className="workspace-nav-button" type="button" aria-label="Подробности сделки" title="Подробности сделки"
          disabled={trades.status !== "ready" || positions.status !== "ready" ||
            positions.value.length !== 1 ||
            uniqueOpenEpisodeId(positions.value[0].symbol, trades.value) === null || !onTradeDetails}
          onClick={() => {
            if (trades.status !== "ready" || positions.status !== "ready" || positions.value.length !== 1) return;
            const id = uniqueOpenEpisodeId(positions.value[0].symbol, trades.value);
            if (id) onTradeDetails?.(id);
          }}>
          <span className="workspace-nav-icon" aria-hidden="true">◎</span>
        </button>
        <button className="workspace-nav-button" type="button" aria-label="Все открытые позиции" title="Все открытые позиции" disabled={!onOpenPositions} onClick={onOpenPositions}>
          <span className="workspace-nav-icon" aria-hidden="true">☷</span>
        </button>
        <button className="workspace-nav-button" type="button" aria-label="Статистика" title="Статистика" disabled={!onStatistics} onClick={onStatistics}>
          <span className="workspace-nav-icon" aria-hidden="true">▂▅▇</span>
        </button>
        <button className="workspace-nav-button" type="button" aria-label="Терминал" title="Терминал" disabled={!onTerminal} onClick={onTerminal}>
          <span className="workspace-nav-icon" aria-hidden="true">$</span>
        </button>
        <button className="workspace-nav-button" type="button" aria-label="Управление роботом" title="Управление роботом" disabled={!onRobotControls} onClick={onRobotControls}><svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M14.7 6.3a5 5 0 0 0-6.4 6.4L3 18l3 3 5.3-5.3a5 5 0 0 0 6.4-6.4l-3.3 3.3-3-3z"/></svg></button>
        {accountControl ? <div className="workspace-nav-account">{accountControl}</div> : null}
      </nav>


    </section>
  );
}
