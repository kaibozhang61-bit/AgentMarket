"use client";

import { useCallback, useEffect, useRef } from "react";

interface Props {
  onResize: (delta: number) => void;
  side: "left" | "right"; // which column the handle is attached to
}

export function ResizeHandle({ onResize, side }: Props) {
  const dragging = useRef(false);
  const startX = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      startX.current = e.clientX;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [],
  );

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      startX.current = e.clientX;
      // Left panel: drag right = wider (positive delta)
      // Right panel: drag left = wider (negative delta, so invert)
      onResize(side === "left" ? delta : -delta);
    }

    function onMouseUp() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [onResize, side]);

  return (
    <div
      onMouseDown={onMouseDown}
      className="group relative z-10 flex w-1 flex-shrink-0 cursor-col-resize items-center justify-center hover:bg-blue-200"
    >
      <div className="h-8 w-1 rounded-full bg-neutral-200 group-hover:bg-blue-400" />
    </div>
  );
}
