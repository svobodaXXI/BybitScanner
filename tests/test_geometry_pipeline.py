"""
test_geometry_pipeline

Проверка полного Geometry Pipeline:

Pivot Points
    ↓
Candidate Engine
    ↓
Evaluation
    ↓
GeometryModel
    ↓
Ranking
"""


from geometry.engine import analyze_geometry



def main():

    #
    # Искусственные Pivot High
    # Верхняя линия с нисходящим уклоном
    #

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


    #
    # Искусственные Pivot Low
    # Нижняя линия с восходящим уклоном
    #

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



    geometry = analyze_geometry(
        highs,
        lows
    )


    if geometry is None:

        print(
            "GEOMETRY RESULT: None"
        )

        return



    print(
        "GEOMETRY RESULT: OK"
    )


    print(
        "TYPE:",
        type(geometry)
    )


    print(
        "UPPER:",
        geometry.upper_line
    )


    print(
        "LOWER:",
        geometry.lower_line
    )


    print(
        "APEX:",
        geometry.apex
    )


    print(
        "COMPRESSION:",
        geometry.compression
    )


    print(
        "TOUCHES:",
        geometry.touches
    )


    print(
        "VALIDATION:",
        geometry.validation
    )


    print(
        "DICT:",
        geometry.to_dict()
    )



if __name__ == "__main__":

    main()
