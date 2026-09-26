import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckIcon, MessageIcon } from '../common/icons';
import { copyToClipboard } from './clipboard';

export interface ShareTarget {
  id: string;
  label: string;
  /** Resolves to true when the share was handed off successfully. */
  run: (payload: { text: string; url: string; title: string }) => Promise<boolean> | boolean;
  /** Only offered where it makes sense (e.g. no link to share). */
  available?: (payload: { url: string }) => boolean;
}

/** Opens a URL in a new tab without leaking window.opener. */
function openExternal(url: string): boolean {
  const win = window.open(url, '_blank', 'noopener,noreferrer');
  return Boolean(win);
}

/**
 * The targets, in the order people reach for them. WhatsApp first because
 * this is a student product and WhatsApp is how answers actually get passed
 * to a friend who needs a hostel.
 *
 * LinkedIn's share endpoint only accepts a URL, so it is offered solely when
 * there is a real link to share - otherwise it would open a composer with
 * nothing in it.
 */
export const SHARE_TARGETS: ShareTarget[] = [
  {
    id: 'whatsapp',
    label: 'WhatsApp',
    run: ({ text }) => openExternal(`https://wa.me/?text=${encodeURIComponent(text)}`),
  },
  {
    id: 'x',
    label: 'X (Twitter)',
    run: ({ text, url }) =>
      openExternal(
        `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}${
          url ? `&url=${encodeURIComponent(url)}` : ''
        }`,
      ),
  },
  {
    id: 'email',
    label: 'Email',
    run: ({ text, title }) => {
      window.location.href = `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(text)}`;
      return true;
    },
  },
  {
    id: 'linkedin',
    label: 'LinkedIn',
    available: ({ url }) => Boolean(url),
    run: ({ url }) => openExternal(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`),
  },
];

/**
 * A popout of places to send this answer, rather than a single button that
 * either opens an OS sheet or silently copies. The sheet is still preferred
 * when the platform provides one (it is the destination students actually
 * want on a phone), and this popout is the fallback plus the explicit
 * choices - so the button is never a dead end and never a surprise.
 */
export function ShareMenu({
  text,
  preview,
  title,
  url,
  onShared,
  onShareRequest,
}: {
  text: string;
  /** Short single-line summary, for targets with a length limit. */
  preview: string;
  title: string;
  url: string;
  onShared?: (target: string) => void;
  /** Attempts the OS share sheet. Returning false (dismissed, or refused)
   *  opens this popout instead, so the button is never a dead end. */
  onShareRequest?: () => Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    // Focus goes back to the trigger so keyboard users are not dropped at the
    // top of the document when the popout closes.
    buttonRef.current?.focus();
  }, []);

  const handleTrigger = useCallback(async () => {
    if (!onShareRequest) {
      setOpen((v) => !v);
      return;
    }
    const handedOff = await onShareRequest();
    // Only fall back when the sheet did not open. Opening the popout on top
    // of a sheet the student is still using would be a second, competing UI.
    if (!handedOff) setOpen(true);
  }, [onShareRequest]);

  // Dismiss on Escape or an outside click, the two ways a popout is expected
  // to behave. A modal dialog would be wrong here: it is a short menu, and
  // trapping focus in it would be heavier than the interaction warrants.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      }
    };
    const onPointer = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onPointer);
    };
  }, [open, close]);

  const run = async (target: ShareTarget) => {
    const ok = await target.run({ text: preview ? `${preview}\n\n${text}` : text, url, title });
    if (ok) {
      onShared?.(target.id);
      setOpen(false);
    }
  };

  const copyInstead = async () => {
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      onShared?.('clipboard');
      setTimeout(() => {
        setCopied(false);
        setOpen(false);
      }, 1200);
    }
  };

  return (
    <div className="share-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="message-action"
        onClick={() => void handleTrigger()}
        aria-label="Share this answer"
        aria-expanded={open}
        aria-haspopup="menu"
        title="Share"
      >
        <MessageIcon className="message-action-icon" />
        <span className="message-action-text">Share</span>
      </button>

      {open && (
        <div className="share-popout" role="menu" aria-label="Share this answer">
          <p className="share-popout-title">Share this answer</p>
          {SHARE_TARGETS.filter((t) => !t.available || t.available({ url })).map((target) => (
            <button
              key={target.id}
              type="button"
              role="menuitem"
              className="share-option"
              onClick={() => void run(target)}
            >
              <ShareGlyph id={target.id} />
              <span>{target.label}</span>
            </button>
          ))}
          <button type="button" role="menuitem" className="share-option" onClick={() => void copyInstead()}>
            {copied ? <CheckIcon className="share-glyph is-done" /> : <ShareGlyph id="clipboard" />}
            <span>{copied ? 'Copied' : 'Copy text'}</span>
          </button>
        </div>
      )}
    </div>
  );
}

/** Simple recognisable marks, so the menu is scannable without depending on
 *  a brand-icon package this project does not have. */
function ShareGlyph({ id }: { id: string }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
  if (id === 'whatsapp') {
    return (
      <svg {...common} className="share-glyph">
        <path d="M21 11.5a8.4 8.4 0 0 1-12.6 7.3L3 21l2.2-5.2A8.5 8.5 0 1 1 21 11.5Z" />
        <path d="M8.5 9.5c0 3 2.5 5.5 5.5 5.5.6 0 1-.4 1-1v-.8l-1.8-.6-.7.7a4.6 4.6 0 0 1-2.3-2.3l.7-.7-.6-1.8h-.8c-.6 0-1 .4-1 1Z" />
      </svg>
    );
  }
  if (id === 'x') {
    return (
      <svg {...common} className="share-glyph">
        <path d="M4 4l16 16M20 4L4 20" />
      </svg>
    );
  }
  if (id === 'email') {
    return (
      <svg {...common} className="share-glyph">
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </svg>
    );
  }
  if (id === 'linkedin') {
    return (
      <svg {...common} className="share-glyph">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M8 10v7M8 7v.01M12 17v-4a2 2 0 0 1 4 0v4" />
      </svg>
    );
  }
  return (
    <svg {...common} className="share-glyph">
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}
