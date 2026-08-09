"""
tests.test_wedge_pipeline

Проверка границы:

GeometryModel
    ↓
Wedge Detector
    ↓
Quality
    ↓
Classifier
    ↓
Score
    ↓
Result
"""


from geometry.engine import analyze_geometry

from wedge.detector import detect_structure

from wedge.quality import evaluate_quality

from wedge.classifier import classify_structure

from wedge.scoring import calculate_score

from wedge.result import (
    create_result,
    attach_legacy_geometry
)



def run():

    highs = [

        {
            "index": 0,
            "price": 110
        },

        {
            "index": 5,
            "price": 105
        },

        {
            "index": 10,
            "price": 100
        },

        {
            "index": 15,
            "price": 95
        }

    ]


    lows = [

        {
            "index": 0,
            "price": 90
        },

        {
            "index": 5,
            "price": 94
        },

        {
            "index": 10,
            "price": 97
        },

        {
            "index": 15,
            "price": 100
        }

    ]



    #
    # 1. Geometry
    #

    geometry = analyze_geometry(
        highs,
        lows
    )


    assert geometry is not None


    print(
        "GEOMETRY: OK"
    )



    #
    # 2. Detector
    #

    detection = detect_structure(
        geometry
    )


    print(
        "DETECTION:",
        detection
    )


    assert detection["detected"] is True



    #
    # 3. Quality
    #

    validation = geometry.validation


    quality = evaluate_quality(
        validation
    )


    print(
        "QUALITY:",
        quality
    )



    #
    # 4. Classifier
    #

    classification = classify_structure(
        detection["pattern"]
    )


    print(
        "CLASS:",
        classification
    )



    #
    # 5. Score
    #

    score = calculate_score(

        detection["pattern"],

        geometry.compression,

        geometry.touches,

        quality

    )


    print(
        "SCORE:",
        score
    )



    #
    # 6. Result
    #

    result = create_result(

        pattern=classification["pattern"],

        reason=classification["reason"],

        score=score["score"],

        geometry=geometry,

        validation=validation,

        quality=quality

    )


    result = attach_legacy_geometry(

        result,

        geometry

    )


    print(
        "RESULT:"
    )


    print(
        result
    )



    assert result["geometry"] is not None

    assert result["validation"] is not None

    assert result["quality"] is not None

    assert result["score"] >= 0



    print(
        "\nWEDGE PIPELINE: OK"
    )



if __name__ == "__main__":

    run()