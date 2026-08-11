from geometry.candidate import generate_candidates


points = [
    {"index": 6, "price": 0.1925},
    {"index": 64, "price": 0.1913},
    {"index": 112, "price": 0.1963},
    {"index": 123, "price": 0.1969},
    {"index": 138, "price": 0.1938},
    {"index": 147, "price": 0.1924},
    {"index": 159, "price": 0.1917},
    {"index": 169, "price": 0.1910},
    {"index": 181, "price": 0.1878},
    {"index": 187, "price": 0.1864},
]


candidates = generate_candidates(
    points
)


candidates.sort(
    key=lambda item: (
        item.get(
            "confirmations",
            0
        ),
        item.get(
            "structure_span",
            0
        ),
        item.get(
            "support_ratio",
            0.0
        ),
        -item.get(
            "line",
            {}
        ).get(
            "confirmation_error_percent",
            999999
        )
    ),
    reverse=True
)


print(
    "Candidates:",
    len(candidates)
)

print()


for i, candidate in enumerate(
    candidates[:10],
    1
):

    line = candidate.get(
        "line",
        {}
    )

    print(
        "Candidate",
        i
    )

    print(
        "Anchor:",
        candidate.get(
            "anchor_index"
        )
    )

    print(
        "Second:",
        candidate.get(
            "second_index"
        )
    )

    print(
        "Confirmations:",
        candidate.get(
            "confirmations"
        )
    )

    print(
        "Support ratio:",
        candidate.get(
            "support_ratio"
        )
    )

    print(
        "Structure span:",
        candidate.get(
            "structure_span"
        )
    )

    print(
        "Slope:",
        line.get(
            "slope"
        )
    )

    print(
        "Error percent:",
        line.get(
            "confirmation_error_percent"
        )
    )

    print(
        "Confirmed points:",
        [
            point["index"]
            for point in candidate.get(
                "points",
                []
            )
        ]
    )

    print()