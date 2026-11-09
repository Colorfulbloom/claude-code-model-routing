/// <reference types="node" />
/*
 * The production Content-Security-Policy from docs/rebuild/planning/m0-build.md section 10, spelled
 * out here on purpose so a change in the server shows up as a failing check.
 */
export function expectedCsp(nonce: string): string {
  return (
    "default-src 'none'; " +
    `script-src 'self' 'nonce-${nonce}'; ` +
    `style-src 'self' 'nonce-${nonce}'; ` +
    "img-src 'self' data:; " +
    "font-src 'self'; " +
    "connect-src 'self'; " +
    "base-uri 'none'; " +
    "form-action 'none'; " +
    "frame-ancestors 'none'"
  );
}

/**
 * Adds the nonce to every script and link tag and a csp-nonce meta tag, the way the server's index
 * rewrite does. React Aria reads that meta tag to nonce the style element it injects.
 */
export function addNonce(html: string, nonce: string): string {
  return html
    .replace(/<(script|link)\b/gi, (_m, name: string) => `<${name} nonce="${nonce}"`)
    .replace(/<head\b[^>]*>/i, (head) => `${head}<meta name="csp-nonce" content="${nonce}">`);
}
