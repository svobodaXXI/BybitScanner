import { describe, expect, it } from "vitest";
import type { DrawingObject } from "../chart/drawingModel";
import { ReplayDrawingUndo } from "./replayDrawingUndo";

const make = (id: string, y = 10): DrawingObject => ({
  id, type: "trend",
  anchors: [{ logical: 100, price: y }, { logical: 110, price: y + 1 }],
  style: { color: "#fff", lineWidth: 1 }, locked: false, hidden: false,
});

describe("replay-only manual drawing undo", () => {
  it("undoes a multi-click line with dozens of draft moves as ONE action", () => {
    const history = new ReplayDrawingUndo();
    history.beginGesture();
    const first = make("line");
    expect(history.commit([{ ...first, anchors: [first.anchors[0]] }])).toBe(true);
    for (let i = 0; i < 35; i++) {
      history.commit([{ ...first, anchors: [first.anchors[0], { logical: 110, price: i }] }]);
    }
    history.commit([first]);
    history.endGesture();
    expect(history.drawings).toEqual([first]);
    expect(history.undoDepth).toBe(1);
    expect(history.undo()).toEqual([]);
    expect(history.canUndo).toBe(false);
  });

  it("undoes a whole-line drag or one moved anchor without removing the object", () => {
    const history = new ReplayDrawingUndo();
    const line = make("line");
    history.commit([line]);
    history.beginGesture();
    for (let i = 1; i <= 20; i++) {
      history.commit([{ ...line, anchors: line.anchors.map(a => ({
        logical: a.logical + i, price: a.price + i,
      })) }]);
    }
    history.endGesture();
    expect(history.undoDepth).toBe(2);
    expect(history.undo()).toEqual([line]);
    history.beginGesture();
    history.commit([{ ...line, anchors: [line.anchors[0], { logical: 110, price: 55 }] }]);
    history.endGesture();
    expect(history.undo()).toEqual([line]);
    expect(history.undo()).toEqual([]);
  });

  it("restores deleted objects, ignores no-op moves and resets on new archive", () => {
    const history = new ReplayDrawingUndo();
    const a = make("a"), b = make("b");
    history.commit([a]);
    history.commit([a, b]);
    history.commit([a]); // delete b
    expect(history.undo()).toEqual([a, b]);
    history.beginGesture();
    expect(history.commit([a, b])).toBe(false); // just clicked without a drag
    history.endGesture();
    expect(history.undoDepth).toBe(2);
    history.reset();
    expect(history.drawings).toEqual([]);
    expect(history.undo()).toBeNull();
    expect(history.canUndo).toBe(false);
  });
});
