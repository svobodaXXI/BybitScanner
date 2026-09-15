from pathlib import Path

path = Path("tests/test_terminal_paper_runtime.py")
text = path.read_text(encoding="utf-8")
old = "    Category, ExecutionId, OrderId, OrderSide, PositionKey, PositionSide, Price, Quantity, Symbol,\n"
new = "    Category, ExecutionDedupKey, ExecutionId, OrderId, OrderSide, PositionKey, PositionSide,\n    Price, Quantity, Symbol,\n"
if text.count(old) != 1:
    raise SystemExit(f"expected one import match, got {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
