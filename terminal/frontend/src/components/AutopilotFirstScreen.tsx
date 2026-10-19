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
  entryBasisFor,
  type Loadable,
  loadAutopilotMode,
  loadDiaryTrades,
  loadOpenPositions,
  loadPositionProtection,
  loadProtectionHealth,
  loadRuntimeHealth,
  type PositionProtection,
  type ProtectionHealth,
  type RuntimeHealth,
  summarizeDay,
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

function PositionCard({
  position,
  protection,
  entryBasis,
}: {
  position: PaperOpenPosition;
  protection: PositionProtection;
  entryBasis: Loadable<string | null>;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailsCloseRef = useRef<HTMLButtonElement>(null);
  const detailsTriggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!detailsOpen) return;
    detailsCloseRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Tab") {
        // The close action is the only interactive element in this read-only dialog.
        event.preventDefault();
        detailsCloseRef.current?.focus();
      } else if (event.key === "Escape") {
        event.preventDefault();
        setDetailsOpen(false);
        detailsTriggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [detailsOpen]);
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
      <button type="button" ref={detailsTriggerRef} onClick={() => setDetailsOpen(true)}>
        Подробности сделки
      </button>
      {detailsOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Подробности сделки ${position.symbol}`}
          className="autopilot-trade-details"
        >
          <header>
            <strong>{position.symbol} · {side}</strong>
            <button type="button" ref={detailsCloseRef} onClick={() => { setDetailsOpen(false); detailsTriggerRef.current?.focus(); }}>
              Закрыть подробности
            </button>
          </header>
          <dl>
            <SummaryItem label="Основание входа">
              <LoadState value={entryBasis} render={(value) =>
                value ?? <Missing source="Diary: decision_reason" />
              } />
            </SummaryItem>
            <SummaryItem label="Подтверждения при входе">
              <Missing source="API не предоставляет подтверждения исходного сигнала" />
            </SummaryItem>
            <SummaryItem label="Причина удержания">
              <Missing source="Robot API не предоставляет текущую причину удержания" />
            </SummaryItem>
            <SummaryItem label="Условия инвалидации">
              <Missing source="API не предоставляет условия инвалидации" />
            </SummaryItem>
            <SummaryItem label="Размер позиции">{position.position_quantity}</SummaryItem>
            <SummaryItem label="Live PnL">
              {Number.isFinite(pnl) ? formatUsdt(pnl) : <Missing source="Текущая цена недоступна" />}
            </SummaryItem>
            <SummaryItem label="STOP и TAKE">
              <LoadState value={protection} render={(value) => (
                value ? `STOP: ${price(value.stop_loss)} · TAKE: ${price(value.take_profit)}`
                      : <Missing source="Нет данных о защите позиции" />
              )} />
            </SummaryItem>
            <SummaryItem label="Статус защиты">
              <LoadState value={protection} render={(value) =>
                value?.status ?? <Missing source="Нет статуса защиты" />
              } />
            </SummaryItem>
            <SummaryItem label="Ограничения риска">
              <Missing source="Нет подтверждённых ограничений риска для этой сделки" />
            </SummaryItem>
            <SummaryItem label="Изменения после входа">
              <Missing source="Нет подтверждённого журнала событий позиции" />
            </SummaryItem>
          </dl>
        </div>
      ) : null}
    </article>
  );
}

export function AutopilotFirstScreen({
  now = () => Date.now(),
  onOpenPositions,
}: {
  now?: () => number;
  onOpenPositions?: () => void;
}) {
  const [autopilot, setAutopilot] = useState<Loadable<AutopilotModeState>>({
    status: "loading",
  });
  const [health, setHealth] = useState<Loadable<RuntimeHealth>>({
    status: "loading",
  });
  const [protection, setProtection] = useState<Loadable<ProtectionHealth>>({
    status: "loading",
  });
  const [positions, setPositions] = useState<Loadable<PaperOpenPosition[]>>({
    status: "loading",
  });
  const [trades, setTrades] = useState<Loadable<DiaryTradeSummaryRow[]>>({
    status: "loading",
  });
  const [positionProtection, setPositionProtection] = useState<
    Record<string, PositionProtection>
  >({});
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
    setProtection({ status: "loading" });
    setPositions({ status: "loading" });
    setTrades({ status: "loading" });
    setPositionProtection({});

    const positionsResult = settle(loadOpenPositions).then((result) => {
      apply(setPositions)(result);
      if (result.status !== "ready") return;
      for (const position of result.value) {
        apply(setPositionProtection)(
          (prior: Record<string, PositionProtection>) => ({
            ...prior,
            [position.symbol]: { status: "loading" },
          }),
        );
        void settle(() => loadPositionProtection(position.symbol)).then(
          (value) =>
            apply(setPositionProtection)(
              (prior: Record<string, PositionProtection>) => ({
                ...prior,
                [position.symbol]: value,
              }),
            ),
        );
      }
    });
    await Promise.all([
      settle(loadAutopilotMode).then(apply(setAutopilot)),
      settle(loadRuntimeHealth).then(apply(setHealth)),
      settle(loadProtectionHealth).then(apply(setProtection)),
      settle(loadDiaryTrades).then(apply(setTrades)),
      positionsResult,
    ]);
  }, []);

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
  const entryBasis = (symbol: string): Loadable<string | null> =>
    trades.status === "ready"
      ? { status: "ready", value: entryBasisFor(symbol, trades.value) }
      : trades;

  return (
    <section
      className="autopilot-first-screen"
      aria-label="Автопилот: первый экран"
    >
      <header className="autopilot-first-screen-header">
        <h3>Что робот сейчас делает</h3>
        <button type="button" onClick={() => void refresh()}>
          Обновить
        </button>
      </header>

      {backendOffline ? (
        <p className="autopilot-error" role="alert">
          PAPER backend недоступен. Запустите runtime ярлыком «Запуск робота».
        </p>
      ) : null}

      <dl className="autopilot-summary" aria-label="Сводка дня">
        <SummaryItem label="PnL за день">
          <LoadState
            value={trades}
            render={(value) => {
              const day = summarizeDay(value, now());
              return day.netPnl === null ? (
                <span className="autopilot-missing">
                  Нет данных: {day.tradesWithoutPnl} из {day.closedTrades}{" "}
                  сделок без PnL
                </span>
              ) : (
                formatUsdt(day.netPnl)
              );
            }}
          />
        </SummaryItem>
        <SummaryItem label="Сделок за день">
          <LoadState
            value={trades}
            render={(value) => summarizeDay(value, now()).closedTrades}
          />
        </SummaryItem>
        <SummaryItem label="Блок серии STOP">
          <Missing source="Серия STOP не реализована в runtime" />
        </SummaryItem>
        <SummaryItem label="Блок дневной просадки">
          <Missing source="Daily-loss gate есть только в решениях Autopilot, API нет" />
        </SummaryItem>
        <SummaryItem label="Уровень STOP-защиты">
          <Missing source="Уровень STOP-защиты не реализован в runtime" />
        </SummaryItem>
        <SummaryItem label="Autopilot">
          <LoadState value={autopilot} render={(value) => value.mode} />
        </SummaryItem>
        <SummaryItem label="Версия политики Autopilot">
          <LoadState value={autopilot} render={(value) => value.version > 0 ? String(value.version) : <Missing source="Версия политики недоступна" />} />
        </SummaryItem>
        <SummaryItem label="Причина режима">
          <LoadState value={autopilot} render={(value) => value.reason?.trim() || <Missing source="Причина режима не предоставлена" />} />
        </SummaryItem>
        <SummaryItem label="PAPER live-safe">
          <LoadState value={health} render={(value) =>
            value.paperLiveSafe === null ? <Missing source="Health: paper_live_safe" /> :
              value.paperLiveSafe ? "Да" : "Нет"
          } />
        </SummaryItem>
        <SummaryItem label="Допуск Robot">
          <LoadState
            value={health}
            render={(value) =>
              value.robotAdmissionReady === null
                ? "—"
                : value.robotAdmissionReady
                  ? "Открыт"
                  : "Закрыт"
            }
          />
        </SummaryItem>
        <SummaryItem label="Состояние Robot">
          <Missing source="GET-статус Robot (mode / recovery_status) не публикуется API" />
        </SummaryItem>
        <SummaryItem label="Защита">
          <LoadState
            value={protection}
            render={(value) =>
              value.healthy === null
                ? "—"
                : value.healthy
                  ? "HEALTHY"
                  : `UNHEALTHY ${value.unhealthySymbols.join(", ")}`.trim()
            }
          />
        </SummaryItem>
      </dl>

      <div className="autopilot-first-screen-header">
        <strong>Открытые позиции</strong>
        {onOpenPositions ? (
          <button type="button" onClick={onOpenPositions}>
            Все открытые позиции
          </button>
        ) : null}
      </div>
      <section className="autopilot-positions" aria-label="Открытые позиции">
        <LoadState
          value={positions}
          render={(value) =>
            value.length === 0 ? (
              <p className="autopilot-empty">Нет открытых позиций</p>
            ) : (
              value.map((position) => (
                <PositionCard
                  key={position.symbol}
                  position={position}
                  protection={
                    positionProtection[position.symbol] ?? { status: "loading" }
                  }
                  entryBasis={entryBasis(position.symbol)}
                />
              ))
            )
          }
        />
      </section>

      <section
        className="autopilot-control-slot"
        aria-label="Управление и мониторинг"
      >
        <p>Управление и мониторинг будут добавлены на этапе UI-2.</p>
      </section>
    </section>
  );
}
