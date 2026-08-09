from geometry.engine import analyze_geometry


# искусственная структура клина

highs = [
    {
        "index": 10,
        "price": 105
    },
    {
        "index": 20,
        "price": 103
    },
    {
        "index": 30,
        "price": 101
    },
    {
        "index": 40,
        "price": 99
    }
]


lows = [
    {
        "index": 10,
        "price": 95
    },
    {
        "index": 20,
        "price": 96
    },
    {
        "index": 30,
        "price": 97
    },
    {
        "index": 40,
        "price": 98
    }
]


result = analyze_geometry(
    highs,
    lows
)


print(result)