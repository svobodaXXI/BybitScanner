"""
wedge.detector

Определение геометрической структуры.

Отвечает только за:
- наличие структуры;
- предварительную классификацию;
- описание признаков.

Не отвечает за:
- Validation;
- Score;
- Quality;
- торговую логику.

Architecture v2.4:

GeometryModel
    ↓
Detector
    ↓
Classifier
    ↓
Quality
    ↓
Score
"""


def _normalize_geometry(
    geometry
):
    """
    Приводит GeometryModel
    или dict к единому формату.

    Поддерживает:

    новый формат:
        GeometryModel

    старый формат:
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
    Определяет, похожа ли Geometry Model
    на клин или другую сжимающуюся структуру.

    Validation используется только как источник
    диагностической информации.

    Он НЕ блокирует обнаружение.
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


    if structure_points >= 2:

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