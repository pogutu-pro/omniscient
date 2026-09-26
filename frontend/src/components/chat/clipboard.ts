/**
 * Copying text, with a fallback for the case the async Clipboard API cannot
 * cover.
 *
 * `navigator.clipboard` is unavailable on an insecure origin (any plain
 * http:// host, which includes a phone hitting a dev server by LAN IP) and is
 * refused outright without a user gesture or a permission grant. When that
 * happens the button must still do something, so it falls back to a
 * selection-based copy rather than failing silently.
 */
export async function copyToClipboard(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      // Rejects rather than throws synchronously when permission is denied.
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }

  try {
    // execCommand is deprecated but remains the only synchronous option on
    // an insecure origin, which is exactly where the API is missing.
    const area = document.createElement('textarea');
    area.value = value;
    area.setAttribute('readonly', '');
    // Kept in the layout but invisible: a display:none element cannot be
    // selected, and an off-screen one can scroll the page on focus.
    area.style.position = 'fixed';
    area.style.top = '0';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}
