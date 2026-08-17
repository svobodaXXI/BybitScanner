"""
wedge.detector

РћРїСЂРµРґРµР»РµРЅРёРµ РіРµРѕРјРµС‚СЂРёС‡РµСЃРєРѕР№ СЃС‚СЂСѓРєС‚СѓСЂС‹.

РћС‚РІРµС‡Р°РµС‚ С‚РѕР»СЊРєРѕ Р·Р°:
- РЅР°Р»РёС‡РёРµ СЃС‚СЂСѓРєС‚СѓСЂС‹;
- РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅСѓСЋ РєР»Р°СЃСЃРёС„РёРєР°С†РёСЋ;
- РѕРїРёСЃР°РЅРёРµ РїСЂРёР·РЅР°РєРѕРІ.

РќРµ РѕС‚РІРµС‡Р°РµС‚ Р·Р°:
- Validation;
- Score;
- Quality;
- С‚РѕСЂРіРѕРІСѓСЋ Р»РѕРіРёРєСѓ.

Architecture v2.4:

GeometryModel
    в†“
Detector
    в†“
Classifier
    в†“
Quality
    в†“
Score
"""


from .integrity import evaluate_directional_envelope


def _normalize_geometry(
    geometry
):
    """
    РџСЂРёРІРѕРґРёС‚ GeometryModel
    РёР»Рё dict Рє РµРґРёРЅРѕРјСѓ С„РѕСЂРјР°С‚Сѓ.

    РџРѕРґРґРµСЂР¶РёРІР°РµС‚:

    РЅРѕРІС‹Р№ С„РѕСЂРјР°С‚:
        GeometryModel

    СЃС‚Р°СЂС‹Р№ С„РѕСЂРјР°С‚:
        dict
    """


    if geometry is None:

        return None



    if hasattr(
        geometry,
        "to_dict"
    ):

        return geometry.to_dict()



    if isinstance(
        geometry,
        dict
    ):

        return geometry



    return None




def _max_consecutive_run(indices):
    """
    ???????????? ????? ???????????????? ????? candle indices.
    """

    if not indices:
        return 0

    values = sorted(
        set(
            int(index)
            for index in indices
        )
    )

    best = 1
    current = 1

    for previous, index in zip(
        values,
        values[1:]
    ):

        if index == previous + 1:

            current += 1

            best = max(
                best,
                current
            )

        else:

            current = 1

    return best


def detect_structure(
    geometry
):
    """
    РћРїСЂРµРґРµР»СЏРµС‚, РїРѕС…РѕР¶Р° Р»Рё Geometry Model
    РЅР° РєР»РёРЅ РёР»Рё РґСЂСѓРіСѓСЋ СЃР¶РёРјР°СЋС‰СѓСЋСЃСЏ СЃС‚СЂСѓРєС‚СѓСЂСѓ.

    Validation РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ С‚РѕР»СЊРєРѕ РєР°Рє РёСЃС‚РѕС‡РЅРёРє
    РґРёР°РіРЅРѕСЃС‚РёС‡РµСЃРєРѕР№ РёРЅС„РѕСЂРјР°С†РёРё.

    РћРЅ РќР• Р±Р»РѕРєРёСЂСѓРµС‚ РѕР±РЅР°СЂСѓР¶РµРЅРёРµ.
    """


    geometry = _normalize_geometry(
        geometry
    )


    if geometry is None:

        return {

            "detected": False,

            "candidate": None,

            "pattern": "No wedge",

            "reason": "Geometry missing"

        }



    upper = geometry.get(
        "upper_line"
    )


    lower = geometry.get(
        "lower_line"
    )


    if (
        not upper
        or
        not lower
    ):

        return {

            "detected": False,

            "candidate": None,

            "pattern": "No wedge",

            "reason": "Trendlines missing"

        }



    upper_slope = upper.get(
        "slope",
        0
    )


    lower_slope = lower.get(
        "slope",
        0
    )



    compression = geometry.get(
        "compression",
        {}
    )


    touches = geometry.get(
        "touches",
        {}
    )


    validation = geometry.get(
        "validation",
        {}
    )



    #
    # Classification
    #


    if (
        upper_slope < 0
        and
        lower_slope < 0
    ):

        pattern = "Falling Wedge"


    elif (
        upper_slope > 0
        and
        lower_slope > 0
    ):

        pattern = "Rising Wedge"


    elif (
        upper_slope < 0
        and
        lower_slope > 0
    ):

        pattern = "Triangle Compression"


    else:

        pattern = "Unknown"


    directional_envelope = (
        evaluate_directional_envelope(
            geometry,
            pattern
        )
    )



    #
    # Directional Candle Containment
    #

    envelope_metrics = geometry.get(
        "envelope_metrics",
        {}
    )

    candle_containment = (
        envelope_metrics.get(
            "candle_containment"
        )
        or {}
    )

    fully_above_upper = (
        candle_containment.get(
            "fully_above_upper_indices",
            []
        )
    )

    fully_below_lower = (
        candle_containment.get(
            "fully_below_lower_indices",
            []
        )
    )

    upper_severe_run = _max_consecutive_run(
        fully_above_upper
    )

    lower_severe_run = _max_consecutive_run(
        fully_below_lower
    )

    # ???? ????????? ???????? ??? ??????
    # ????????? ???????? ????? ?? ??????? ???????.
    max_strict_severe_run = 2

    strict_sides = tuple(
        directional_envelope.get(
            "strict_sides",
            []
        )
    )

    if strict_sides == ("upper",):

        strict_side = "upper"

        strict_severe_run = (
            upper_severe_run
        )

        containment_valid = (
            strict_severe_run
            <= max_strict_severe_run
        )

    elif strict_sides == ("lower",):

        strict_side = "lower"

        strict_severe_run = (
            lower_severe_run
        )

        containment_valid = (
            strict_severe_run
            <= max_strict_severe_run
        )

    elif set(strict_sides) == {
        "upper",
        "lower"
    }:

        strict_side = "both"

        strict_severe_run = max(
            upper_severe_run,
            lower_severe_run
        )

        containment_valid = (
            upper_severe_run
            <= max_strict_severe_run
            and
            lower_severe_run
            <= max_strict_severe_run
        )

    else:

        strict_side = "none"
        strict_severe_run = 0
        containment_valid = False


    #
    # Geometry Features
    #


    current_index = geometry.get(
        "current_index"
    )

    end_index = geometry.get(
        "end_index"
    )

    apex = geometry.get(
        "apex",
        {}
    )

    apex_index = (
        apex.get("index")
        if isinstance(apex, dict)
        else None
    )

    freshness_bars = None

    if (
        current_index is not None
        and end_index is not None
    ):
        freshness_bars = (
            current_index
            -
            end_index
        )

    before_apex = bool(
        current_index is not None
        and apex_index is not None
        and current_index <= apex_index
    )

    features = {

        "compression":

            bool(
                compression.get(
                    "is_compressing",
                    False
                )
            ),

        "touches":

            bool(
                touches.get(
                    "valid",
                    False
                )
            ),

        "apex":

            geometry.get(
                "apex"
            )
            is not None,

        "validation":

            bool(
                validation.get(
                    "valid",
                    False
                )
            ),

        "freshness":

            bool(
                freshness_bars is not None
                and 0 <= freshness_bars <= 15
                and before_apex
            ),

        "containment":

            bool(
                containment_valid
            ),

        "containment_strict_side":

            strict_side,

        "containment_strict_run":

            strict_severe_run,

        "containment_upper_run":

            upper_severe_run,

        "containment_lower_run":

            lower_severe_run,

        "directional_envelope":

            directional_envelope

    }
    structure_points = sum(

            [

                features["compression"],

                features["touches"],

                features["apex"]

            ]

        )

    #
    # Decision
    #

    if (
        structure_points >= 2
        and
        features["validation"]
        and
        features["freshness"]
        and
        features["containment"]
    ):

        return {

            "detected": True,


            "candidate":

                "geometry_candidate",


            "pattern":

                pattern,


            "reason":

                "Geometry resembles structure",


            "features":

                features,


            "directional_envelope":

                directional_envelope

        }



    return {

        "detected": False,


        "candidate":

            None,


        "pattern":

            "No wedge",


        "reason":

            "Insufficient geometry features",


        "features":

            features,


        "directional_envelope":

            directional_envelope

    }
