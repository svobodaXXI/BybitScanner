/** Local manual-annotation undo, isolated from the strategy/geometry replay.
 * One drag (including many pointermove commits) or one two-click figure is
 * one undoable action. No chart/paper/replay events are ever stored here.
 */
import type { DrawingObject } from "../chart/drawingModel";

const snapshot = (items: readonly DrawingObject[]): DrawingObject[] =>
  items.map(item => ({
    ...item,
    anchors: item.anchors.map(anchor => ({ ...anchor })),
    style: { ...item.style },
  }));

export class ReplayDrawingUndo {
  private current: DrawingObject[] = [];
  private history: DrawingObject[][] = [];
  private inGesture = false;
  private capturedGesture = false;

  get drawings(): DrawingObject[] { return this.current; }
  get canUndo(): boolean { return this.history.length > 0; }
  get undoDepth(): number { return this.history.length; }

  beginGesture(): void {
    // The drawing overlay calls this at the beginning of a gesture, before
    // any mutation; do not reset an unfinished multi-click action.
    if (!this.inGesture) {
      this.inGesture = true;
      this.capturedGesture = false;
    }
  }

  commit(next: DrawingObject[]): boolean {
    if (JSON.stringify(next) === JSON.stringify(this.current)) return false;
    if (!this.inGesture || !this.capturedGesture) {
      this.history.push(snapshot(this.current));
      this.capturedGesture = this.inGesture;
    }
    this.current = snapshot(next);
    return true;
  }

  endGesture(): void {
    this.inGesture = false;
    this.capturedGesture = false;
  }

  undo(): DrawingObject[] | null {
    const previous = this.history.pop();
    if (previous === undefined) return null;
    this.endGesture();
    this.current = snapshot(previous);
    return this.current;
  }

  reset(): void {
    this.current = [];
    this.history = [];
    this.endGesture();
  }
}
