import { useEffect, useState } from "react";
import { DiaryOverlay, type DiarySection } from "./DiaryOverlay";

type DiaryLaunch = {
  section: DiarySection;
  tradeEpisodeId: string | null;
};

export function AutopilotDiaryControls({
  accountKey,
  tradeEpisodeId = null,
  requestedTradeEpisodeId = null,
  onRequestConsumed,
}: {
  accountKey: string;
  tradeEpisodeId?: string | null;
  requestedTradeEpisodeId?: string | null;
  onRequestConsumed?: () => void;
}) {
  const [launch, setLaunch] = useState<DiaryLaunch | null>(null);
  useEffect(() => {
    if (!requestedTradeEpisodeId) return;
    setLaunch({ section: "TRADES", tradeEpisodeId: requestedTradeEpisodeId });
    onRequestConsumed?.();
  }, [requestedTradeEpisodeId, onRequestConsumed]);

  return (
    <>
      <div className="autopilot-diary-actions" aria-label="Дневник автопилота">
        <button
          type="button"
          onClick={() => setLaunch({ section: "STATISTICS", tradeEpisodeId: null })}
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
      </div>

      {launch ? (
        <DiaryOverlay
          key={`${accountKey}:${launch.section}:${launch.tradeEpisodeId ?? ""}`}
          accountKey={accountKey}
          initialSection={launch.section}
          initialTradeEpisodeId={launch.tradeEpisodeId}
          onClose={() => setLaunch(null)}
        />
      ) : null}
    </>
  );
}
