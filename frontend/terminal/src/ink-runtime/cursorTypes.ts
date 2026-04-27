export type DeclaredCursor = {
  anchorId: string;
  relativeX: number;
  relativeY: number;
  active: boolean;
};

export type AnchorRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type CaretCellPosition = {
  line: number;
  column: number;
};
