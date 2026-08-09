from geometry.candidate import generate_candidates


points = [

    {
        "index": 1,
        "price": 100
    },

    {
        "index": 2,
        "price": 98
    },

    {
        "index": 3,
        "price": 96
    },

    {
        "index": 4,
        "price": 94
    },

    {
        "index": 5,
        "price": 93
    },

    {
        "index": 6,
        "price": 91
    },

]


candidates = generate_candidates(points)


print(
    "Candidates:",
    len(candidates)
)

print()


for i, c in enumerate(
    candidates,
    1
):

    print(
        "Candidate",
        i
    )

    print(
        "Points:"
    )

    print(
        c
    )

    print()