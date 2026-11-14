import { useEffect, useState } from "react";
import { DiaryOverlay, type DiaryAccountMenuProps, type DiarySection } from "./DiaryOverlay";

type DiaryLaunch = {
  section: DiarySection;
  tradeEpisodeId: string | null;
};

export function AutopilotDiaryControls({
  accountKey,
  tradeEpisodeId = null,
  requestedTradeEpisodeId = null,
  onRequestConsumed,
  requestedStatisticsCount = 0,
  hideActions = false,
  accountMenu = null,
}: {
  accountKey: string;
  tradeEpisodeId?: string | null;
  requestedTradeEpisodeId?: string | null;
  onRequestConsumed?: () => void;
  requestedStatisticsCount?: number;
  hideActions?: boolean;
  accountMenu?: DiaryAccountMenuProps | null;
}) {
  const [launch, setLaunch] = useState<DiaryLaunch | null>(null);
  useEffect(() => {
    if (!requestedTradeEpisodeId) return;
    setLaunch({ section: "TRADES", tradeEpisodeId: requestedTradeEpisodeId });
    onRequestConsumed?.();
  }, [requestedTradeEpisodeId, onRequestConsumed]);

  useEffect(() => {
    if (requestedStatisticsCount > 0) setLaunch({ section: "FINREZ", tradeEpisodeId: null });
  }, [requestedStatisticsCount]);

  return (
    <>
      {!hideActions ? <div className="autopilot-diary-actions" aria-label="Дневник автопилота">
        <button
          type="button"
          onClick={() => setLaunch({ section: "FINREZ", tradeEpisodeId: null })}
        >
          Статистика
        </button>
        <button
          type="button"
          disabled={tradeEpisodeId === null}
          title={tradeEpisodeId === null ? "Нет связи с эпизодом сделки" : undefined}
          onClick={() => {
            if (tradeEpisodeId === null) return;
            setLaunch({ section: "TRADES", tradeEpisodeId });
          }}
        >
          Подробности сделки
        </button>
      </div> : null}

      {launch ? (
        <DiaryOverlay
          key={`${accountKey}:${launch.section}:${launch.tradeEpisodeId ?? ""}`}
          accountKey={accountKey}
          accountMenu={accountMenu}
          statisticsScope={{ accountId: "paper", owner: "ROBOT" }}
          initialSection={launch.section}
          initialTradeEpisodeId={launch.tradeEpisodeId}
          onClose={() => setLaunch(null)}
        />
      ) : null}
    </>
  );
}
