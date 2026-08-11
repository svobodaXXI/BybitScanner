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
            )

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

                features

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

            features

    }
