import { useId, useLayoutEffect, useRef, useState } from "react";

/** A visual preview of the original answer, never a rewritten or shortened report. */
export function ExecutiveAnswer({ text }: { text: string }) {
  const id = useId();
  const paragraph = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useLayoutEffect(() => {
    const element = paragraph.current;
    if (!element) return;
    const measure = () => {
      const style = getComputedStyle(element);
      const lines = Number.parseInt(style.getPropertyValue("--answer-preview-lines"), 10);
      const previewHeight = Number.parseFloat(style.lineHeight) * lines;
      // scrollHeight includes the clipped lines, even when the preview is collapsed.
      // Compare against the preview budget rather than clientHeight so the toggle
      // remains available while expanded and updates when the viewport changes.
      setOverflows(element.scrollHeight > previewHeight + 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text]);

  return (
    <section className="executive-answer" aria-labelledby={`${id}-heading`}>
      <div className="executive-answer-mark" aria-hidden="true">✓</div>
      <div className="executive-answer-body">
        <h2 className="executive-answer-heading" id={`${id}-heading`}>Answer at a glance</h2>
        <p
          className={`executive-answer-text${expanded ? " is-expanded" : ""}`}
          id={`${id}-text`}
          ref={paragraph}
        >
          {text}
        </p>
        {overflows ? (
          <button
            className="executive-answer-toggle"
            type="button"
            aria-expanded={expanded}
            aria-controls={`${id}-text`}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "Show less" : "Read full answer"}
            <span aria-hidden="true">{expanded ? "↑" : "↓"}</span>
          </button>
        ) : null}
      </div>
    </section>
  );
}
