export function DrawingClearConfirmation({
  onCancel,
  onConfirm,
}: {
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="drawing-clear-confirmation"
      role="alertdialog"
      aria-modal="true"
      aria-label="Удалить все фигуры?"
    >
      <p>Удалить все фигуры?</p>
      <div>
        <button type="button" onClick={onCancel}>Отмена</button>
        <button className="danger" type="button" onClick={onConfirm}>Удалить</button>
      </div>
    </div>
  );
}
