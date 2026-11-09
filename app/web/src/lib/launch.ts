/*
 * Reads the three meta tags the server writes into index.html. Each one falls back to a safe
 * value so tests and the Vite dev server work without them.
 */
export interface Launch {
  /** Per-request CSP nonce, "" when absent. */
  nonce: string;
  /** Instance id of the server that served this page, "" when unknown. */
  instance: string;
  /** The preview command shown on gate pages. */
  command: string;
}

export const DEFAULT_COMMAND = "/bartab-preview";

function meta(doc: Document, name: string): string {
  const content = doc.querySelector(`meta[name="${name}"]`)?.getAttribute("content");
  return content ?? "";
}

export function readLaunch(doc: Document = document): Launch {
  return {
    nonce: meta(doc, "csp-nonce"),
    instance: meta(doc, "bartab-instance"),
    command: meta(doc, "bartab-command") || DEFAULT_COMMAND,
  };
}
