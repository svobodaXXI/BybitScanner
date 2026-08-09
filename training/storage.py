"""
storage.py

BybitScanner Annotation Storage Layer

Отвечает за:

- сохранение Human Annotation;
- загрузку Human Annotation;
- работу с Dataset файлами.

Не выполняет:

- импорт TradingView;
- расчёт Geometry;
- Validation;
- Score;
- Trainer логику.
"""


import json
from pathlib import Path
from datetime import datetime


ANNOTATIONS_DIR = Path(
    "training/annotations"
)


def ensure_storage():
    """
    Создаёт директорию хранения,
    если её нет.
    """

    ANNOTATIONS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )



def generate_annotation_filename(
    contract
):
    """
    Создаёт имя файла
    для Human Annotation.
    """

    symbol = contract.get(
        "symbol",
        "UNKNOWN"
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return (
        f"{symbol}_"
        f"{timestamp}.json"
    )



def save_annotation(
    contract
):
    """
    Сохраняет Annotation Contract
    в Dataset.
    """

    ensure_storage()


    filename = generate_annotation_filename(
        contract
    )


    path = (
        ANNOTATIONS_DIR /
        filename
    )


    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            contract,
            file,
            indent=4,
            ensure_ascii=False
        )


    return str(path)



def load_annotation(
    path
):
    """
    Загружает сохранённую Annotation.
    """

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )



def list_annotations():
    """
    Возвращает список
    сохранённых разметок.
    """

    ensure_storage()


    return [
        str(file)
        for file in ANNOTATIONS_DIR.glob(
            "*.json"
        )
    ]