import { useRef, useState, type KeyboardEvent } from 'react';
import { ActivityIcon, SendIcon } from '../common/icons';

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
  hasActivity: boolean;
  onToggleActivity: () => void;
}

export function ChatComposer({ onSend, disabled, hasActivity, onToggleActivity }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
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

  return (
    <div className="chat-composer-wrap">
      <div className="chat-composer-inner">
        {hasActivity && (
          <button type="button" className="activity-toggle-btn" onClick={onToggleActivity}>
            <ActivityIcon width={14} height={14} />
            Activity
          </button>
        )}
        <div className="chat-composer">
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
          <button type="button" className="chat-send-btn" onClick={submit} disabled={disabled || !value.trim()} aria-label="Send message">
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}
