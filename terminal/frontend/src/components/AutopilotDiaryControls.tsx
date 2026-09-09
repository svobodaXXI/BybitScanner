import { useState } from "react";
import { DiaryOverlay, type DiarySection } from "./DiaryOverlay";

type DiaryLaunch = {
  section: DiarySection;
  tradeEpisodeId: string | null;
};

export function AutopilotDiaryControls({
  accountKey,
  tradeEpisodeId = null,
}: {
  accountKey: string;
  tradeEpisodeId?: string | null;
}) {
  const [launch, setLaunch] = useState<DiaryLaunch | null>(null);

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
          accountKey={accountKey}
          initialSection={launch.section}
          initialTradeEpisodeId={launch.tradeEpisodeId}
          onClose={() => setLaunch(null)}
        />
      ) : null}
    </>
  );
}
