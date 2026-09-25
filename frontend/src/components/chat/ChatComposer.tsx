import { useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react';
import { uploadFile } from '../../api/client';
import type { Attachment } from '../../types';
import { AttachIcon, ChevronUpIcon, CloseIcon, GenericFileIcon, ImageFileIcon, SendIcon, SpinnerIcon } from '../common/icons';

const MAX_ATTACHMENTS = 4;
const ACCEPTED_TYPES = 'image/png,image/jpeg,image/webp,application/pdf,text/plain';

interface PendingAttachment {
  id: string;
  file_name: string;
  content_type: string;
  previewUrl: string | null;
  uploading: boolean;
  error: string | null;
  attachment: Attachment | null;
}

interface Props {
  onSend: (text: string, attachments?: Attachment[]) => void;
  disabled: boolean;
  hasActivity: boolean;
  isStreaming: boolean;
  statusLabel: string | null;
  onToggleActivity: () => void;
}

let pendingIdCounter = 0;

export function ChatComposer({ onSend, disabled, hasActivity, isStreaming, statusLabel, onToggleActivity }: Props) {
  const [value, setValue] = useState('');
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const stillUploading = pending.some((p) => p.uploading);
  const readyAttachments = pending.filter((p) => p.attachment).map((p) => p.attachment as Attachment);

  const submit = () => {
    const trimmed = value.trim();
    if ((!trimmed && readyAttachments.length === 0) || disabled || stillUploading) return;
    if (readyAttachments.length > 0) {
      onSend(trimmed, readyAttachments);
    } else {
      onSend(trimmed);
    }
    setValue('');
    setPending([]);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const autoGrow = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const handleFilesSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []).slice(0, MAX_ATTACHMENTS - pending.length);
    event.target.value = '';
    for (const file of files) {
      const id = `pending-${(pendingIdCounter += 1)}`;
      const isImage = file.type.startsWith('image/');
      setPending((prev) => [
        ...prev,
        {
          id,
          file_name: file.name,
          content_type: file.type,
          previewUrl: isImage ? URL.createObjectURL(file) : null,
          uploading: true,
          error: null,
          attachment: null,
        },
      ]);
      uploadFile(file)
        .then((result) => {
          setPending((prev) =>
            prev.map((p) =>
              p.id === id
                ? {
                    ...p,
                    uploading: false,
                    attachment: { key: result.key, content_type: file.type, file_name: file.name, url: result.url },
                  }
                : p,
            ),
          );
        })
        .catch((err) => {
          setPending((prev) =>
            prev.map((p) =>
              p.id === id
                ? { ...p, uploading: false, error: err instanceof Error ? err.message : 'Upload failed' }
                : p,
            ),
          );
        });
    }
  };

  const removePending = (id: string) => {
    setPending((prev) => prev.filter((p) => p.id !== id));
  };

  return (
    <div className="chat-composer-wrap">
      <div className="chat-composer-inner">
        {hasActivity && (
          <button type="button" className="status-strip" onClick={onToggleActivity} aria-label="View activity details">
            <span className={`status-strip-indicator${isStreaming ? ' is-live' : ''}`} aria-hidden="true" />
            <span className="status-strip-text">{statusLabel ?? 'Activity'}</span>
            <ChevronUpIcon width={14} height={14} className="status-strip-chevron" />
          </button>
        )}
        {pending.length > 0 && (
          <div className="composer-attachments">
            {pending.map((p) => (
              <div key={p.id} className={`composer-attachment-chip${p.error ? ' has-error' : ''}`}>
                {p.previewUrl ? (
                  <img src={p.previewUrl} alt="" className="composer-attachment-thumb" />
                ) : (
                  <span className="composer-attachment-icon">
                    {p.content_type.startsWith('image/') ? <ImageFileIcon size={14} /> : <GenericFileIcon size={14} />}
                  </span>
                )}
                <span className="composer-attachment-name">{p.error ?? p.file_name}</span>
                {p.uploading ? (
                  <SpinnerIcon className="spin" size={13} />
                ) : (
                  <button
                    type="button"
                    className="composer-attachment-remove"
                    aria-label={`Remove ${p.file_name}`}
                    onClick={() => removePending(p.id)}
                  >
                    <CloseIcon size={13} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="chat-composer">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            className="visually-hidden"
            onChange={handleFilesSelected}
            aria-label="Attach a file"
          />
          <button
            type="button"
            className="chat-attach-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || pending.length >= MAX_ATTACHMENTS}
            aria-label="Attach an image or file"
          >
            <AttachIcon size={18} />
          </button>
          <textarea
            ref={textareaRef}
            value={value}
            placeholder="Message Omniscient..."
            onChange={(e) => {
              setValue(e.target.value);
              autoGrow();
            }}
            onKeyDown={handleKeyDown}
            rows={1}
            aria-label="Message Omniscient"
          />
          <button
            type="button"
            className="chat-send-btn"
            onClick={submit}
            disabled={disabled || stillUploading || (!value.trim() && readyAttachments.length === 0)}
            aria-label="Send message"
          >
            {isStreaming ? <SpinnerIcon className="spin" /> : <SendIcon />}
          </button>
        </div>
      </div>
    </div>
  );
}
