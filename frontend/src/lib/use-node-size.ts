import { useEffect, useRef, useState } from "react";

export type NodeSize = "compact" | "medium" | "expanded";

/**
 * Tracks a DOM element's size and returns a t-shirt size.
 * compact:  width < 200
 * medium:   200 <= width < 320
 * expanded: width >= 320
 */
export function useNodeSize(): [React.RefObject<HTMLDivElement | null>, NodeSize] {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<NodeSize>("medium");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width;
        if (w < 200) setSize("compact");
        else if (w < 320) setSize("medium");
        else setSize("expanded");
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, size];
}
