import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckIcon, SpinnerIcon } from '../common/icons';
import { ShareMenu } from './ShareMenu';
import { answerToPreview, answerToText } from './answerText';
import { copyToClipboard } from './clipboard';
import type { ContentBlock } from '../../types';

type Rating = 1 | -1;

interface Props {
  /** The reply's prose. */
  text: string;
  /** The reply's rendered blocks — the substance of most answers. */
  blocks?: ContentBlock[];
  rating?: Rating;
  ratingPending?: boolean;
  onRate: (rating: Rating | null) => void;
  /** Called with the target id when the answer is actually shared. */
  onShare?: (target: string) => void;
  onCopy?: () => void;
}

/** Prefer the OS share sheet where it exists - on a phone it is where the
 *  student actually wants to send an answer - and fall back to the popout
 *  everywhere else. */
function hasNativeShare(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function';
}

export function MessageActions({ text, blocks, rating, ratingPending, onRate, onShare, onCopy }: Props) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  // The complete answer: rendered blocks *and* prose. Copying only the prose
  // copied the closing sentence and silently dropped the results table,
  // which is the part anyone pasting this actually wants.
  const full = answerToText(blocks, text);
  const preview = answerToPreview(blocks, text);
  const shareUrl = typeof window !== 'undefined' ? window.location.href : '';
  const shareTitle = preview || 'Omniscient answer';

  const handleCopy = useCallback(async () => {
    const ok = await copyToClipboard(full);
    if (!ok) return;
    setCopied(true);
    onCopy?.();
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [full, onCopy]);

  // Returns true only when the sheet actually opened. `navigator.share`
  // rejects both when the OS refuses and when the student dismisses it, and
  // the two need the same handling here: fall back to the explicit menu.
  const handleNativeShare = useCallback(async () => {
    if (!hasNativeShare()) return false;
    try {
      await navigator.share({ title: shareTitle, text: full, url: shareUrl });
      onShare?.('native');
      return true;
    } catch {
      return false;
    }
  }, [full, onShare, shareTitle, shareUrl]);

  const handleRate = useCallback(
    (value: Rating) => {
      // Pressing the lit thumb again clears it: a second tap means "actually
      // no", not "yes, twice".
      onRate(rating === value ? null : value);
    },
    [onRate, rating],
  );

  const nothingToActOn = !text && (!blocks || blocks.length === 0);

  return (
    <div className="message-actions">
      <button
        type="button"
        className="message-action"
        onClick={handleCopy}
        disabled={nothingToActOn}
        aria-label="Copy this answer"
        title="Copy the full answer"
      >
        {copied ? <CheckIcon className="message-action-icon is-done" /> : <CopyIcon />}
        <span className="message-action-text">{copied ? 'Copied' : 'Copy'}</span>
      </button>

      <ShareMenu
        text={full}
        preview={preview}
        title={shareTitle}
        url={shareUrl}
        onShared={onShare}
        onShareRequest={hasNativeShare() ? handleNativeShare : undefined}
      />

      <span className="message-actions-divider" aria-hidden="true" />

      <div className="message-rating" role="group" aria-label="Rate this answer">
        <button
          type="button"
          className={`message-action message-action-thumb${rating === 1 ? ' is-active' : ''}`}
          onClick={() => handleRate(1)}
          disabled={ratingPending}
          aria-pressed={rating === 1}
          aria-label="This answer was helpful"
          title="Helpful"
        >
          {ratingPending && rating === 1 ? (
            <SpinnerIcon className="message-action-icon" />
          ) : (
            <ThumbIcon direction="up" active={rating === 1} />
          )}
        </button>
        <button
          type="button"
          className={`message-action message-action-thumb${rating === -1 ? ' is-active is-down' : ''}`}
          onClick={() => handleRate(-1)}
          disabled={ratingPending}
          aria-pressed={rating === -1}
          aria-label="This answer was not helpful"
          title="Not helpful"
        >
          {ratingPending && rating === -1 ? (
            <SpinnerIcon className="message-action-icon" />
          ) : (
            <ThumbIcon direction="down" active={rating === -1} />
          )}
        </button>
      </div>
    </div>
  );
}

/* Local icons: the app re-exports Lucide under semantic names, and a
   filled/outlined pair like this is not in that set. Drawn on Lucide's 24x24
   grid at 2px stroke so they sit consistently beside the shared ones. */
function CopyIcon() {
  return (
    <svg
      className="message-action-icon"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function ThumbIcon({ direction, active }: { direction: 'up' | 'down'; active: boolean }) {
  return (
    <svg
      className="message-action-icon"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill={active ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={direction === 'down' ? { transform: 'rotate(180deg)' } : undefined}
    >
      <path d="M7 10v12" />
      <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
    </svg>
  );
}
