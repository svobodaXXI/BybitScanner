"""
analyzer.py

РњРѕРґСѓР»СЊ Р°РЅР°Р»РёР·Р° РѕРґРЅРѕР№ С‚РѕСЂРіРѕРІРѕР№ РїР°СЂС‹.

Р’С‹РїРѕР»РЅСЏРµС‚ РїРѕР»РЅС‹Р№ С†РёРєР» Р°РЅР°Р»РёР·Р°:

- Р·Р°РіСЂСѓР·РєР° СЃРІРµС‡РµР№;
- РїРѕРёСЃРє Pivot High / Pivot Low;
- Р°РЅР°Р»РёР· СЃС‚СЂСѓРєС‚СѓСЂС‹;
- РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ СЃРёРіРЅР°Р»Р°;
- РїРѕСЃС‚СЂРѕРµРЅРёРµ РіСЂР°С„РёРєР°;
- СЃРѕС…СЂР°РЅРµРЅРёРµ РѕС‚С‡С‘С‚Р°.

Р’РѕР·РІСЂР°С‰Р°РµС‚ СЂРµР·СѓР»СЊС‚Р°С‚ Р°РЅР°Р»РёР·Р°.
"""


from bybit_api import get_candles
from pivots import find_pivots
from wedge import analyze_wedge
from confirmation import confirm_signal
from chart import draw_chart
from report import save_report

from config import (
    TIMEFRAME,
    CANDLE_LIMIT
)



def analyze_symbol(symbol):

    """
    РђРЅР°Р»РёР· РѕРґРЅРѕР№ С‚РѕСЂРіРѕРІРѕР№ РїР°СЂС‹.
    """


    try:

        # =========================
        # Load candles
        # =========================

        df = get_candles(
            symbol,
            TIMEFRAME,
            CANDLE_LIMIT
        )


        if df is None or len(df) < 50:

            print(
                f"{symbol}: РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ СЃРІРµС‡РµР№"
            )

            return {

                "symbol": symbol,
                "result": None,
                "highs": [],
                "lows": []

            }



        # =========================
        # Pivot detection
        # =========================


        highs, lows = find_pivots(
            df
        )


        if (
            len(highs) < 3
            or len(lows) < 3
        ):

            print(
                f"{symbol}: РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Pivot"
            )

            return {

                "symbol": symbol,
                "result": None,
                "highs": highs,
                "lows": lows

            }



        # =========================
        # Wedge analysis
        # =========================


        result = analyze_wedge(
            highs,
            lows
        )


        if result is None:


            return {

                "symbol": symbol,

                "result": None,

                "highs": highs,

                "lows": lows

            }



        # =========================
        # Confirmation Engine
        # =========================


        confirmation = confirm_signal(

            df,

            result

        )


        if confirmation is None:

            confirmation = {

                "breakout": False,

                "volume": False,

                "volatility": False,

                "breakout_score": 0,

                "volume_score": 0,

                "volatility_score": 0,

                "freshness_score": 0,

                "distance_score": 0,

                "confirmation_score": 0,

                "direction": "WAIT",

                "confirmed": False

            }



        result["confirmation"] = confirmation



        # =========================
        # Final score
        # =========================


        base_score = result.get(
            "score",
            0
        )


        confirmation_score = confirmation.get(
            "confirmation_score",
            0
        )


        result["final_score"] = min(

            base_score
            +
            confirmation_score,

            100

        )



        # =========================
        # Chart
        # =========================


        print("[DEBUG CHART GEOMETRY]", symbol, result.get("pattern"), result.get("geometry"))

        draw_chart(

            df,

            highs,

            lows,

            symbol,

            result

        )



        # =========================
        # Report
        # =========================


        save_report(

            symbol,

            TIMEFRAME,

            result,

            highs,

            lows

        )



        return {

            "symbol": symbol,

            "result": result,

            "highs": highs,

            "lows": lows,

            "data": df

        }



    except Exception as error:


        print(
            f"[ERROR] {symbol}: {error}"
        )


        return {

            "symbol": symbol,

            "result": None,

            "highs": [],

            "lows": []

        }

