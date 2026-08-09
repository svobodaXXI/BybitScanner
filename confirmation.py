"""
confirmation.py

Confirmation Engine v1.4

Проверяет качество пробоя структуры:

- breakout detection
- ATR breakout distance
- early / late breakout
- retest detection
- support hold
- confirmation scoring
"""


import pandas as pd
import numpy as np



# ===============================
# ATR
# ===============================

def calculate_atr(df, period=14):

    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low

    tr2 = abs(
        high - close.shift(1)
    )

    tr3 = abs(
        low - close.shift(1)
    )

    tr = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    atr = (
        tr
        .rolling(period)
        .mean()
    )

    return atr



# ===============================
# Trendline price
# ===============================

def line_price(line, index):

    if line is None:
        return None

    return (
        line["slope"] * index
        +
        line["intercept"]
    )



# ===============================
# Breakout detection
# ===============================

def detect_breakout(
        df,
        wedge
):

    last = df.iloc[-1]

    index = len(df)-1

    upper = line_price(
        wedge.get("upper_line"),
        index
    )

    lower = line_price(
        wedge.get("lower_line"),
        index
    )


    if upper is None:
        return {
            "breakout": False
        }


    price = last["close"]


    if price > upper:

        return {

            "breakout": True,

            "direction": "LONG",

            "level": upper,

            "distance": price-upper

        }


    if price < lower:

        return {

            "breakout": True,

            "direction": "SHORT",

            "level": lower,

            "distance": lower-price

        }


    return {

        "breakout": False,

        "direction": "WAIT"

    }



# ===============================
# Breakout quality
# ===============================

def evaluate_breakout_quality(
        df,
        breakout
):


    if not breakout.get("breakout"):

        return {

            "status": "NO_BREAKOUT",

            "quality": "NONE"

        }


    atr_series = calculate_atr(df)

    atr = atr_series.iloc[-1]


    if atr is None or np.isnan(atr):

        atr = 0


    distance = breakout["distance"]


    extension = (
        distance / atr
        if atr > 0
        else 0
    )


    if extension <= 2:

        quality = "GOOD"
        status = "EARLY"


    elif extension <= 5:

        quality = "ACCEPTABLE"
        status = "NORMAL"


    else:

        quality = "TOO_LATE"
        status = "MISSED_BREAKOUT"



    return {

        "status": status,

        "distance": round(
            distance,
            3
        ),

        "atr": round(
            atr,
            4
        ),

        "extension_atr": round(
            extension,
            2
        ),

        "quality": quality

    }



# ===============================
# Retest detection
# ===============================

def detect_retest(
        df,
        breakout
):


    if not breakout.get("breakout"):

        return {

            "retest": False,

            "support_hold": False,

            "retest_score": 0

        }


    level = breakout["level"]


    recent = df.tail(10)


    touched = False
    hold = False


    for _, candle in recent.iterrows():


        if (
            candle["low"]
            <= level
            <= candle["high"]
        ):

            touched = True


            if candle["close"] > level:

                hold = True



    score = 0


    if touched:
        score += 5


    if hold:
        score += 5



    return {

        "retest": touched,

        "support_hold": hold,

        "retest_score": score

    }



# ===============================
# Volume
# ===============================

def volume_confirmation(df):

    avg = (
        df["volume"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )


    current = df["volume"].iloc[-1]


    if current > avg * 1.5:

        return True, 5


    return False, 0



# ===============================
# Main engine
# ===============================

def confirm_signal(
        df,
        wedge
):


    result = {}


    breakout = detect_breakout(
        df,
        wedge
    )


    result.update(
        breakout
    )


    quality = evaluate_breakout_quality(
        df,
        breakout
    )


    result["breakout_quality"] = quality



    retest = detect_retest(
        df,
        breakout
    )


    result.update(
        retest
    )



    volume, volume_score = volume_confirmation(
        df
    )


    result["volume"] = volume


    score = 0



    # breakout

    if breakout.get("breakout"):

        if quality["quality"] == "GOOD":

            score += 5


        elif quality["quality"] == "ACCEPTABLE":

            score += 2



    # volume

    score += volume_score



    # volatility

    volatility_score = 0


    atr = calculate_atr(df).iloc[-1]


    candle_range = (
        df["high"].iloc[-1]
        -
        df["low"].iloc[-1]
    )


    if candle_range > atr:

        volatility_score = 5


    score += volatility_score



    # retest

    score += result.get(
        "retest_score",
        0
    )



    # FOMO penalty

    if quality.get("status") == "MISSED_BREAKOUT":

        score = 0



    result["breakout_score"] = (
        5
        if breakout.get("breakout")
        else 0
    )


    result["volume_score"] = volume_score


    result["volatility_score"] = volatility_score


    result["confirmation_score"] = min(
        score,
        25
    )


    result["confirmed"] = (
        result["confirmation_score"]
        >=
        15
    )


    if not breakout.get("breakout"):

        result["direction"] = "WAIT"



    return result