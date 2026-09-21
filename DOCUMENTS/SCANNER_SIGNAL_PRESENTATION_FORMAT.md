# BybitScanner — Scanner Signal Presentation Format

Version: 1.0
Date: 2026-09-21
Status: ACTIVE

Authoritative description of the **Scanner** Wedge/Triangle Telegram signal post and the Wedge/Triangle chart header.

Before this document no repository documentation described either format; both existed only as code in `notification.py` and `chart_clean.py`. This document records the approved presentation and distinguishes what is implemented from what is not.

## Scope

Owned surfaces:

- `notification.py:format_signal()` — the Scanner Telegram signal post;
- `chart_clean.py:build_chart_title()` — the Wedge/Triangle chart header.

Explicit non-goals — these formats are **not** covered and must not be changed by this document:

- Robot position cards (`robot_position_view.py`, `DOCUMENTS/AUTOPILOT_ROBOT_V0_1_TELEGRAM_POSITION_CARD_SPEC.md`);
- Telegram Monitoring posts (`telegram_monitoring.py`);
- Ikigai Box cards (`geometry/ikigai_box_chart.py`, `ikigai_box_scanner.py`).

Those surfaces keep their own `Паттерн:` labelling where they already use it. Only the two Scanner surfaces above are in scope.

## 1. Telegram Scanner signal post — CURRENT (implemented)

Status: **IMPLEMENTED on `main`** — the `Паттерн:` prefix was dropped in commit `90368d4` (PR #171, "fix: drop the pattern label from the Scanner signal card").

Owner: `notification.py:format_signal()`. Russian pattern labels come from `PATTERN_LABELS_RU`.

Format:

```text
{SCANNER_EMOJI} Сканер: {symbol} {circle}
{pattern_label}
Таймфрейм: {timeframe_label}

Баллы: {score}
```

`SCANNER_EMOJI` is `📡` (`telegram_labels.SCANNER_EMOJI`). `{circle}` is one of the four existing stage circles from `notification.py:signal_stage_circle()`:

- `🟢` FORMING — no breakout, not mature;
- `🟡` MATURE / NEAR APEX / PRE-BREAKOUT — no breakout, mature;
- `🟠` POST-BREAKOUT / WAITING RETEST — breakout only;
- `🔴` POST-RETEST / LATE ENTRY — breakout and retest.

Example:

```text
📡 Сканер: AEVOUSDT 🟢
Восходящий клин
Таймфрейм: 5м

Баллы: 90
```

Acceptance criteria:

1. The pattern name appears on its own line with no `Паттерн:` prefix.
2. The symbol, status emoji (`signal_stage_circle`), timeframe line and score line are unchanged.
3. `🧪 TEST MODE` continues to append after the timeframe line in test mode.
4. Robot, Telegram Monitoring and Ikigai Box card formats are unaffected.

## 2. Wedge/Triangle chart header — CURRENT vs TARGET

Owner: `chart_clean.py:build_chart_title()`.

### 2.1 CURRENT (deployed — do not treat the target below as live)

```text
{symbol} · {timeframe}
СТРУКТУРА: {structure_name}
ГЕОМЕТРИЯ: {geometry_name}
ПАТТЕРН: {detection_name}
КАЧЕСТВО СТРУКТУРЫ: {score}/100
ПОТЕНЦИАЛ ДВИЖЕНИЯ: {potential_name}
ОБУЧЕНИЕ: {training_name}
```

`tests/test_chart_clean_title.py` currently asserts this CURRENT form.

### 2.2 TARGET (approved 2026-09-21 — NOT IMPLEMENTED)

The renderer change is **not** authorized or performed by this document. Until it lands, charts render the CURRENT form above.

Wedges (Falling Wedge / Rising Wedge):

```text
{symbol} · {timeframe}
{structure_name}
КАЧЕСТВО СТРУКТУРЫ: {score}/100
ПОТЕНЦИАЛ ДВИЖЕНИЯ: {potential_name}
Тип клина: не определено
```

Triangles (Triangle Compression) — identical, but with **no** `Тип клина` line:

```text
{symbol} · {timeframe}
{structure_name}
КАЧЕСТВО СТРУКТУРЫ: {score}/100
ПОТЕНЦИАЛ ДВИЖЕНИЯ: {potential_name}
```

Changes from CURRENT:

- the `СТРУКТУРА:` prefix is removed; the pattern name is shown directly;
- the whole `ПАТТЕРН: {detection_name}` line is removed (both `ПОДТВЕРЖДЕН` and `НЕ ПОДТВЕРЖДЕН`);
- the `ГЕОМЕТРИЯ:` line is removed;
- the `ОБУЧЕНИЕ:` line is removed;
- wedges gain a fixed `Тип клина: не определено` placeholder until wedge-type classification is implemented;
- symbol/timeframe, quality score and movement potential are preserved, including the `РАСЧЁТ НЕДОСТУПЕН` fallback when `potential.signed_percent` is absent.

Acceptance criteria for the future renderer change:

1. No chart header contains `СТРУКТУРА:`, `ГЕОМЕТРИЯ:`, `ОБУЧЕНИЕ:` or a `ПАТТЕРН:` line.
2. The pattern name is the second line, rendered directly.
3. A Falling Wedge or Rising Wedge header contains exactly one `Тип клина: не определено` line.
4. A Triangle Compression header contains no `Тип клина` line.
5. Symbol/timeframe, `КАЧЕСТВО СТРУКТУРЫ` and `ПОТЕНЦИАЛ ДВИЖЕНИЯ` lines are byte-identical to CURRENT.
6. `tests/test_chart_clean_title.py` is updated in the same change; no detector, scoring, geometry or Robot behavior changes.

### 2.3 Open point

The approval does not fix the position of the `Тип клина` line. This document places it last. If a different position is wanted, decide it before the renderer change.

## Ownership boundary

This document is presentation-only. It does not alter pattern classification, detection, geometry, scoring, training eligibility, Robot/PAPER/LIVE behavior or any data written to the diary, `signals/` or `review_queue/`. `geometry_mode` and `detection.detected` remain available in `result` and keep their existing non-presentational consumers; only their appearance in the chart header changes.

# END_OF_DOCUMENT
