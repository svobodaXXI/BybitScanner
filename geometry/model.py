"""
geometry.model

Geometry Model

Единая структура хранения
геометрической модели.

Отвечает только за:
- линии;
- Apex;
- Compression;
- Touches;
- Validation;
- границы структуры;
- текущий индекс рынка.

Не содержит:
- Score;
- Signal;
- Trading logic.
"""


class GeometryModel:

    def __init__(
        self,
        upper_line,
        lower_line,
        apex,
        compression,
        touches,
        validation,
        start_index=None,
        end_index=None,
        current_index=None,
        candidate_points=None
    ):

        self.upper_line = upper_line
        self.lower_line = lower_line

        self.apex = apex

        self.compression = compression
        self.touches = touches

        self.validation = validation

        self.start_index = start_index
        self.end_index = end_index
        self.current_index = current_index

        self.candidate_points = (
            candidate_points
            or {}
        )


    def to_dict(self):

        return {

            "upper_line":
                self.upper_line,

            "lower_line":
                self.lower_line,

            "apex":
                self.apex,

            "compression":
                self.compression,

            "touches":
                self.touches,

            "validation":
                self.validation,

            "start_index":
                self.start_index,

            "end_index":
                self.end_index,

            "current_index":
                self.current_index,

            "candidate_points":
                self.candidate_points

        }