# Machine Time — owner-approved strategy selector and Telegram trade hydration

Date: 2026-11-23. Scope: **Machine Time replay UI only**. This document is an implementation contract, not evidence that the UI has been changed.

## Acceptance criteria

1. Render all strategy selectors in **one unframed, uniform field**, with exact owner-requested order and Russian labels:
   1. Все стратегии
   2. Миррор-комплекс
   3. Зеркальные уровни
   4. Граница паттерна
   5. Клинья
   6. Коробка Икигай
   7. Г-образная
   8. Треугольник
   Other currently supported options must not disappear silently; reconcile against the existing registry.
2. Remove the old «Голая свеча: возврат» and «Голая свеча: ретест» **UI categories**. Replace them with two separately selectable mechanisms: «Зеркальные уровни» = naked-candle setup at a **horizontal mirror level**; «Граница паттерна» = naked-candle setup at a **frozen pattern boundary**, e.g. a wedge or triangle. A UI rename must **not** silently alias different back-end strategy IDs, alter execution policies, or backfill unknown historical evidence.
3. «Миррор-комплекс» is one **composite selector** adjacent to its member options, not a bordered group. Activating it selects its verified supported members. The proposed membership includes the two mechanisms, клинья, коробка Икигай, Г-образная and owner-mentioned треугольник; reconcile membership with owning technical specifications before wiring (avoid changing trading classification by UI alone). Composite selection must not create a synthetic strategy ID.
4. «Все стратегии» is a bulk selector; «Снять все» is retained and clears selections. Remove «Только клинья», the «Универсальный симулятор» heading and «Настройки прогона» subtitle. Translate remaining user-facing labels to Russian; preserve underlying stable identifiers.
5. On Telegram → closed PAPER trade → Machine Time, hydrate the **ticker, replay start/end inputs and exactly one source pattern selection** from the verified episode payload, without enabling the composite or defaulting to both wedge directions. Explicitly distinguish the specific pattern identity from the simulation's broad family filter. If trade metadata lacks a trusted pattern/dates, show unavailable rather than guessing.
6. Show the **original signal-time pattern geometry** when supplied with verified provenance and SHA-256. Do not reconstruct from later candles. The protected bridge/facts route work is separately tracked in PR #1284; the UI must degrade honestly when geometry is absent. Preserve actual execution prices, timestamps and PAPER provenance.
7. Do not introduce a new tab on repeated trade opens if reuse is possible within existing launch semantics; do not use this as a reason to break direct opening.
8. No Scanner/Robot logic, trading execution, admission, risk, PAPER or LIVE behavior, VPS state, data schema or persisted trade history changed. No runtime restart or release without separate authority.

## Focused verification

- A Rising Wedge episode selects only «Восходящий клин» at the **specific pattern selection** level, not both orientations and not «Миррор-комплекс». Equivalent Falling Wedge control.
- Episode ticker and exact trusted source date range populate every visible «Исторический период» input. Missing metadata remains visibly unresolved.
- All eight requested selectors appear in order, Russian names, one field, no group frames; bulk select/clear works; Mirror selects only validated members.
- Horizontal mirror level and pattern boundary stay distinct in the UI and map to existing supported semantics, not invented trading rules.
- Original geometry is drawn only with verified source facts; unknown signal shows a clear absence state. Existing candle/execution rendering unaffected.
- One scoped UI regression and mandatory repository checks before review; do not claim PASS without execution evidence.

## Delivery gate

Implement in an independent focused code PR or extend this branch with a reviewed minimum patch after identifying the owning component. PR review + focused checks first. Merge, desktop release and VPS changes require separate permissions. This spec alone does not close the quest.
