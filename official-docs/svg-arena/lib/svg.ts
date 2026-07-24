import DOMPurify from "isomorphic-dompurify";

/**
 * Pull an <svg>...</svg> block out of arbitrary model output. Models often wrap
 * SVG in markdown code fences or add prose before/after; we grab the first
 * well-formed svg element.
 */
export function extractSvg(raw: string): string | null {
  if (!raw) return null;
  // Strip code fences if present.
  const fenced = raw.match(/```(?:svg|xml|html)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1] : raw;
  const match = candidate.match(/<svg[\s\S]*<\/svg>/i);
  return match ? match[0].trim() : null;
}

/**
 * Sanitize model-generated SVG so it is safe to render in the browser. SVG is
 * untrusted code: it can carry <script>, event handlers, and external
 * references (XSS / data exfiltration). We run DOMPurify with the SVG profile,
 * which strips scripts and on* handlers, then defensively drop a few more
 * vectors. Returns null if nothing usable remains.
 */
export function sanitizeSvg(raw: string): string | null {
  const extracted = extractSvg(raw);
  if (!extracted) return null;

  const clean = DOMPurify.sanitize(extracted, {
    USE_PROFILES: { svg: true, svgFilters: true },
    // Belt and suspenders on top of the SVG profile.
    FORBID_TAGS: ["script", "foreignObject", "a"],
    FORBID_ATTR: ["onload", "onclick", "onmouseover", "href", "xlink:href"],
    ADD_ATTR: ["viewBox"],
  });

  const trimmed = clean.trim();
  if (!trimmed.toLowerCase().startsWith("<svg")) return null;
  return trimmed;
}
