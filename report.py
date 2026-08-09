"""
report.py

BybitScanner

Формирование расширенного отчёта анализа.

Сохраняет:

- торговую пару;
- таймфрейм;
- найденную структуру;
- Pattern Score;
- Score Breakdown;
- Quality Engine;
- Validation Details;
- Confirmation Engine;
- Confirmation Score;
- направление;
- итоговый рейтинг;
- Pivot точки.
"""


import os



def status(value):
    """
    Преобразование логического статуса.
    """

    if value:
        return "PASS"

    return "FAIL"





def get_quality(score):
    """
    Классическая оценка итогового сигнала.
    """

    if score >= 90:
        return "***** ELITE SIGNAL"

    elif score >= 75:
        return "**** STRONG"

    elif score >= 60:
        return "*** WATCHLIST"

    return "NO TRADE"





def save_report(
    symbol,
    timeframe,
    result,
    highs,
    lows
):

    os.makedirs(
        "reports",
        exist_ok=True
    )


    filename = f"reports/{symbol}.txt"


    lines = []


    lines.append("=" * 60)
    lines.append("BybitScanner Signal Report")
    lines.append("=" * 60)

    lines.append("")

    lines.append(
        f"Symbol      : {symbol}"
    )

    lines.append(
        "Market      : Bybit Linear USDT Futures"
    )

    lines.append(
        f"Timeframe   : {timeframe}"
    )

    lines.append("")



    if not result:

        lines.append(
            "Not enough data."
        )


    else:


        # =========================
        # Pattern Analysis
        # =========================

        lines.append(
            "PATTERN ANALYSIS"
        )

        lines.append(
            "-" * 40
        )


        lines.append(
            f"Pattern       : {result.get('pattern')}"
        )


        lines.append(
            f"Pattern Score : {result.get('score', 0)}/100"
        )


        if "reason" in result:

            lines.append(
                f"Reason        : {result['reason']}"
            )


        lines.append("")


        geometry = result.get(
            "geometry",
            {}
        )


        validation = result.get(
            "validation"
        )


        if validation is None:

            validation = geometry.get(
                "validation"
            )


        # =========================
        # Validation Details
        # =========================

        if validation:


            lines.append(
                "VALIDATION DETAILS"
            )

            lines.append(
                "-" * 40
            )


            lines.append(
                f"Geometry Valid : {status(validation.get('valid'))}"
            )


            failed = validation.get(
                "failed_checks",
                []
            )


            if failed:

                lines.append(
                    f"Failed checks  : {', '.join(failed)}"
                )

            else:

                lines.append(
                    "Failed checks  : none"
                )


            checks = validation.get(
                "checks",
                {}
            )


            for name, check in checks.items():

                lines.append("")


                lines.append(
                    f"{name.upper()}"
                )


                lines.append(
                    f"  Status : {status(check.get('valid'))}"
                )


                lines.append(
                    f"  Reason : {check.get('reason','')}"
                )


            lines.append("")


        # =========================
        # Quality Engine
        # =========================

        quality = result.get(
            "quality"
        )


        if quality:


            lines.append(
                "QUALITY ENGINE"
            )

            lines.append(
                "-" * 40
            )


            lines.append(
                f"Quality : {quality.get('quality', 'Unknown')}"
            )


            lines.append(
                f"Reason  : {quality.get('reason', '')}"
            )


            lines.append("")


        # =========================
        # Pattern Breakdown
        # =========================

        breakdown = result.get(
            "score_breakdown"
        )


        if breakdown:


            lines.append(
                "SCORE BREAKDOWN"
            )


            lines.append(
                f"  Structure     : {breakdown.get('structure',0)}"
            )


            lines.append(
                f"  Touches       : {breakdown.get('touches',0)}"
            )


            lines.append(
                f"  Compression   : {breakdown.get('compression',0)}"
            )


            lines.append(
                f"  Trend Quality : {breakdown.get('trend_quality',0)}"
            )


            lines.append(
                f"  Bonus         : {breakdown.get('bonus',0)}"
            )


            lines.append("")


        # =========================
        # Confirmation Engine
        # =========================

        confirmation = result.get(
            "confirmation"
        )


        if confirmation:


            lines.append(
                "CONFIRMATION ENGINE"
            )

            lines.append(
                "-" * 40
            )


            lines.append(
                f"Breakout         : {status(confirmation.get('breakout'))}"
            )


            lines.append(
                f"Breakout Score   : {confirmation.get('breakout_score',0)}"
            )


            lines.append(
                f"Volume           : {status(confirmation.get('volume'))}"
            )


            lines.append(
                f"Volume Score     : {confirmation.get('volume_score',0)}"
            )


            lines.append(
                f"Volatility       : {status(confirmation.get('volatility'))}"
            )


            lines.append(
                f"Volatility Score : {confirmation.get('volatility_score',0)}"
            )


            lines.append(
                f"Freshness Score  : {confirmation.get('freshness_score',0)}"
            )


            lines.append(
                f"Distance Score   : {confirmation.get('distance_score',0)}"
            )


            lines.append("")


            lines.append(
                f"Confirmation Total: "
                f"{confirmation.get('confirmation_score',0)}/35"
            )


            lines.append(
                f"Direction         : "
                f"{confirmation.get('direction','WAIT')}"
            )


            lines.append("")


        # =========================
        # Final Score
        # =========================

        final_score = result.get(
            "final_score",
            result.get("score", 0)
        )


        lines.append(
            "FINAL SIGNAL QUALITY"
        )


        lines.append(
            "-" * 40
        )


        lines.append(
            f"Final Score : {final_score}/100"
        )


        lines.append(
            f"Rating      : {get_quality(final_score)}"
        )


        lines.append("")


        # =========================
        # Trend Structure
        # =========================

        upper_line = geometry.get(
            "upper_line",
            {}
        )

        lower_line = geometry.get(
            "lower_line",
            {}
        )

        compression = geometry.get(
            "compression",
            {}
        )


        lines.append(
            "TREND STRUCTURE"
        )


        lines.append(
            f"High slope  : {upper_line.get('slope')}"
        )


        lines.append(
            f"Low slope   : {lower_line.get('slope')}"
        )


        lines.append(
            f"Compression : {compression.get('compression_percent')} %"
        )


        lines.append("")


        # =========================
        # Pivot points
        # =========================

        lines.append(
            "HIGH PIVOTS"
        )


        for p in highs:

            lines.append(
                f"index={p['index']:3d} price={p['price']}"
            )


        lines.append("")


        lines.append(
            "LOW PIVOTS"
        )


        for p in lows:

            lines.append(
                f"index={p['index']:3d} price={p['price']}"
            )


    lines.append("")

    lines.append(
        "=" * 60
    )


    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "\n".join(lines)
        )


    print(
        f"Отчёт сохранён: {filename}"
    )