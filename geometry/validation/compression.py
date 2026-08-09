"""
geometry.validation.compression

Проверка наличия сжатия структуры.

Validation Engine v2:

Возвращает диагностический результат,
а не только True/False.
"""


def validate_compression(
    compression,
    minimum_percent=5
):
    """
    Проверяет наличие сжатия.

    Условия:

    - данные compression должны существовать;
    - процент сжатия должен быть
      не меньше минимального значения.

    Возвращает:

    {
        "valid": bool,
        "reason": str,
        "details": dict
    }

    """


    if compression is None:

        return {

            "valid":
                False,

            "reason":
                "Missing compression data",

            "details":
                {}

        }


    compression_percent = float(
        compression.get(
            "compression_percent",
            0
        )
    )


    is_compressing = compression.get(
        "is_compressing",
        False
    )


    if not is_compressing:

        return {

            "valid":
                False,

            "reason":
                "Structure is not compressing",

            "details":
                {

                    "compression_percent":
                        compression_percent,

                    "is_compressing":
                        is_compressing

                }

        }


    if compression_percent < minimum_percent:

        return {

            "valid":
                False,

            "reason":
                "Compression below minimum threshold",

            "details":
                {

                    "compression_percent":
                        compression_percent,

                    "minimum_percent":
                        minimum_percent

                }

        }


    return {

        "valid":
            True,

        "reason":
            "Compression acceptable",

        "details":
            {

                "compression_percent":
                    compression_percent,

                "minimum_percent":
                    minimum_percent,

                "is_compressing":
                    is_compressing

            }

    }