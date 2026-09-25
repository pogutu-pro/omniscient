import { useRef, useState, type KeyboardEvent } from 'react';
import { ActivityIcon, SendIcon } from '../common/icons';

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
  onToggleActivity: () => void;
  activityCount: number;
}

export function ChatComposer({ onSend, disabled, onToggleActivity, activityCount }: Props) {
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
      <div style={{ width: '100%', maxWidth: 'var(--content-max-width)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button type="button" className="btn btn-ghost btn-sm activity-toggle activity-toggle-btn" onClick={onToggleActivity} style={{ alignSelf: 'flex-start' }}>
          <ActivityIcon />
          Activity{activityCount > 0 ? ` (${activityCount})` : ''}
        </button>
        <div className="chat-composer">
          <textarea
            ref={textareaRef}
            value={value}
            placeholder="Ask Omniscient anything about campus life..."
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
