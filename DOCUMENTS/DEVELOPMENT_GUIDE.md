# DEVELOPMENT_GUIDE.md

# BybitScanner — Development Guide

Версия документа: 1.1
Дата актуализации: 2026-08-28

---

# 0. Назначение документа

Этот документ описывает правила разработки проекта BybitScanner.

Он определяет:

- порядок внесения изменений;
- правила работы с кодом;
- правила рефакторинга;
- порядок тестирования;
- порядок обновления документации.

---

# 1. SOURCE OF TRUTH REFERENCE

Главный источник правил проекта:

```
PROJECT_RULES.md
```

Все изменения должны соответствовать:

- архитектуре проекта;
- правилам разработки;
- принципам разделения ответственности.

---

# 2. Главный принцип разработки

Основной принцип:

```
Сначала стабильная архитектура,
потом новые возможности.
```

---

Запрещено:

- добавлять функциональность хаотично;
- ломать существующие интерфейсы без необходимости;
- смешивать ответственность модулей;
- исправлять симптом вместо причины.

---

# 3. Перед изменением кода

Перед внесением изменений необходимо определить:

## 1. Цель изменения

Что должно измениться?

Пример:

```
Улучшить определение Compression
```

---

## 2. Ответственный слой

Где должна находиться логика?

Пример:

Правильно:

```
geometry/compression.py
```

Неправильно:

```
telegram_formatter.py
```

---

## 3. Возможное влияние

Проверить:

- какие модули используют этот код;
- какие результаты зависят от него;
- какие тесты могут измениться.

---

# 4. Правило одного модуля

Каждый модуль имеет одну ответственность.

---

Пример:

## geometry

Можно:

- линии;
- расстояния;
- формы.

Нельзя:

- Telegram;
- торговые решения.

---

## telegram_bot

Можно:

- отправка сообщений.

Нельзя:

- анализ сигналов.

---

## signal

Можно:

- Score;
- качество;
- фильтрация.

Нельзя:

- строить линии.

---

# 5. Создание нового модуля

Перед созданием файла ответить:

```
Зачем он нужен?

Кто его вызывает?

Какие данные получает?

Какие данные возвращает?
```

---

Если нельзя ответить:

новый модуль создавать нельзя.

---

# 6. Правила изменения существующего кода

При изменении:

## Сначала

прочитать:

- текущий код;
- связанные модули;
- документацию.

---

## Потом

сделать изменение.

---

## После

проверить:

- запуск;
- ошибки;
- совместимость.

---

# 7. Правило маленьких изменений

Предпочтительно:

```
маленький шаг
+
проверка
+
следующий шаг
```

---

Не рекомендуется:

одновременно менять:

- архитектуру;
- Score;
- Telegram;
- анализ.

---

# 8. Правило рефакторинга

Рефакторинг выполняется этапами:

```
Понять старую структуру

↓

Создать новую структуру

↓

Перенести ответственность

↓

Сохранить совместимость

↓

Удалить старое
```

---

# 9. Legacy Compatibility Rule

При возможности:

старые интерфейсы сохраняются.

---

Причина:

не ломать:

- отчёты;
- графики;
- интеграции;
- сохранённые данные.

---

# 10. Работа с Geometry Engine

Geometry является фундаментальным слоем.

---

Любые изменения геометрии требуют проверки:

- линии;
- apex;
- compression;
- touches;
- validation.

---

Нельзя улучшать Score,
если Geometry ещё нестабилен.

---

# 11. Работа с результатами анализа

Формат результата должен оставаться понятным.

Пример:

```
{
    "pattern": "...",
    "score": 0,
    "geometry": {},
    "confirmation": {}
}
```

---

Не рекомендуется:

- скрытые поля;
- неявные изменения структуры;
- случайные новые форматы.

---

# 12. Тестирование изменений

После изменения необходимо:

## Минимальная проверка

Запустить:

```
python main.py
```

---

Проверить:

- проект стартует;
- анализ выполняется;
- результаты выводятся;
- Telegram не ломается.

---

# 13. Проверка больших изменений

После больших изменений:

создать:

```
SNAPSHOT
```

обновить:

```
PROJECT_STATE.md
```

при необходимости обновить:

```
CHANGELOG.md
```

---

# 14. Работа с документацией

Любое значимое изменение должно отражаться:

---

Архитектура:

```
ARCHITECTURE.md
```

---

Состояние:

```
PROJECT_STATE.md
```

---

История:

```
CHANGELOG.md
```

---

План:

```
ROADMAP.md
```

---

# 15. Работа с архивами

Перед большим этапом создавать архив:

Формат:

```
BybitScanner_backup_DATE_STAGE.zip
```

Пример:

```
BybitScanner_backup_2026-07-25_geometry-calibration.zip
```

---

# 16. Работа с Git (будущая рекомендация)

При дальнейшем развитии рекомендуется:

```
main
 |
 ├── develop
 |
 └── feature/*
```

---

Изменения:

не сразу в основную ветку.

---

# 17. Правила исправления ошибок

Ошибка должна исправляться:

не там, где проявилась,

а там, где возникла.

---

Пример:

Если Telegram показывает неправильный Score:

проверять:

```
signal
```

а не:

```
telegram_formatter
```

---

# 18. Приоритеты разработки

Текущий порядок:

```
1. Geometry correctness

2. Pattern quality

3. Confirmation

4. Signal intelligence

5. Market context

6. Automation
```

---

# 19. Что нельзя делать

Запрещено:

❌ добавлять торговую логику в Telegram  
❌ считать Score внутри Geometry  
❌ строить графики внутри Analyzer  
❌ хранить конфигурацию в коде  
❌ удалять документацию без замены  
❌ ломать интерфейсы без причины  

---

# 20. Контрольная формула проекта

Архитектурное правило:

```
Data
↓
Analysis
↓
Geometry
↓
Signal
↓
Notification
```

Каждый слой делает только свою работу.

---

# 21. Planned central VPS development workflow

Status: `PLANNED / APPROVED DIRECTION / NOT IMPLEMENTED`.

VPS migration does not interrupt the current logical frontend and Trading Workspace stage. First complete that
stage, perform manual acceptance, create a clean project checkpoint and verify local/GitHub repository state.
The VPS migration then becomes the next major operational task.

Intended migration sequence:

1. Finish the current logical frontend/Trading Workspace stage.
2. Complete manual acceptance.
3. Create a clean project checkpoint.
4. Verify repository and GitHub state.
5. Inspect hosting type, VPS/VDS versus shared hosting, Linux version, CPU, RAM, storage, network/IP, SSH and root/sudo access.
6. Establish safe SSH access.
7. Create appropriate non-root server users.
8. Configure minimal appropriate server security/firewall controls.
9. Install Git, Python, project Python dependencies, Node.js, npm and Codex CLI.
10. Create or clone the DEV repository on the VPS.
11. Restore dependencies.
12. Run existing project verification/tests.
13. Run the frontend build.
14. Start and test the Trading Workspace from the VPS.
15. Test phone access over mobile internet.
16. Establish an always-on service strategy for Scanner, backend and frontend where appropriate.
17. Only after DEV is verified, establish separate PROD through controlled promotion.
18. Perform an additional security review before enabling future live trading/Robot secrets or runtime.

Development occurs in VPS DEV; Codex must not edit live PROD directly. Exact paths and service choices follow
server inspection. SSH remains a direct path and no proprietary phone-access transport is mandatory.

---

# END OF DEVELOPMENT GUIDE
