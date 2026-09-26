import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageList } from '../components/chat/MessageList';
import type { DisplayMessage } from '../types';

describe('MessageList', () => {
  it('shows suggestion prompts when there are no messages yet', async () => {
    const user = userEvent.setup();
    const onSuggestion = vi.fn();
    render(<MessageList messages={[]} isSlow={false} isStreaming={false} onSuggestion={onSuggestion} onRate={vi.fn()} />);

    expect(screen.getByText('What can I help with?')).toBeInTheDocument();
    // The tile shows a short label; the full question is what's actually sent.
    const suggestion = screen.getByText('Find a hostel');
    await user.click(suggestion);
    expect(onSuggestion).toHaveBeenCalledWith('Find me a hostel under KSh 8,000 near Boma');
  });

  it('renders user and assistant messages with the right roles', () => {
    const messages: DisplayMessage[] = [
      { id: '1', role: 'user', content: 'Find me a hostel' },
      { id: '2', role: 'assistant', content: 'Here are some options', pending: false },
    ];
    render(<MessageList messages={messages} isSlow={false} isStreaming={false} onSuggestion={vi.fn()} onRate={vi.fn()} />);

    expect(screen.getByText('Find me a hostel')).toBeInTheDocument();
    expect(screen.getByText('Here are some options')).toBeInTheDocument();
  });

  it('shows a typing indicator for a pending, contentless assistant message', () => {
    const messages: DisplayMessage[] = [
      { id: '1', role: 'user', content: 'Find me a hostel' },
      { id: '2', role: 'assistant', content: '', pending: true },
    ];
    render(<MessageList messages={messages} isSlow={false} isStreaming={false} onSuggestion={vi.fn()} onRate={vi.fn()} />);
    expect(screen.getByText('Omniscient is thinking')).toBeInTheDocument();
    expect(screen.queryByText('Still working on it...')).not.toBeInTheDocument();
  });

  it('shows a slow hint once the watchdog flags the request as slow', () => {
    const messages: DisplayMessage[] = [
      { id: '1', role: 'user', content: 'Find me a hostel' },
      { id: '2', role: 'assistant', content: '', pending: true },
    ];
    render(<MessageList messages={messages} isSlow={true} isStreaming={false} onSuggestion={vi.fn()} onRate={vi.fn()} />);
    expect(screen.getByText('Still working on it...')).toBeInTheDocument();
  });

  it('renders content blocks attached to an assistant message', () => {
    const messages: DisplayMessage[] = [
      { id: '1', role: 'user', content: 'Find me a hostel' },
      {
        id: '2',
        role: 'assistant',
        content: 'Here are some options.',
        blocks: [
          {
            type: 'table',
            columns: [{ key: 'name', label: 'Name', align: 'left' }],
            rows: [{ name: 'Boma View Hostel' }],
          },
        ],
      },
    ];
    render(<MessageList messages={messages} isSlow={false} isStreaming={false} onSuggestion={vi.fn()} onRate={vi.fn()} />);
    expect(screen.getByText('Boma View Hostel')).toBeInTheDocument();
    expect(screen.getByText('Here are some options.')).toBeInTheDocument();
  });

  it('renders an image attachment on a user message', () => {
    const messages: DisplayMessage[] = [
      {
        id: '1',
        role: 'user',
        content: "What's in this photo?",
        attachments: [{ key: 'uploads/x.png', content_type: 'image/png', file_name: 'photo.png', url: 'http://x/photo.png' }],
      },
      { id: '2', role: 'assistant', content: 'I cannot see images in offline mode.' },
    ];
    render(<MessageList messages={messages} isSlow={false} isStreaming={false} onSuggestion={vi.fn()} onRate={vi.fn()} />);
    const image = screen.getByAltText('photo.png');
    expect(image).toHaveAttribute('src', 'http://x/photo.png');
  });
});

describe('MessageList message actions', () => {
  it('offers copy, share and rate on an assistant answer', () => {
    render(
      <MessageList
        messages={[{ id: 'a1', role: 'assistant', content: 'Here are 5 hostels.' }]}
        isSlow={false}
        isStreaming={false}
        onSuggestion={vi.fn()}
        onRate={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /copy this answer/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /share this answer/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /was helpful/i })).toBeInTheDocument();
  });

  it('does not offer them on the student’s own message', () => {
    // A thumb on your own question is meaningless, and copy there would
    // copy the question rather than the answer.
    render(
      <MessageList
        messages={[{ id: 'u1', role: 'user', content: 'hostels near campus' }]}
        isSlow={false}
        isStreaming={false}
        onSuggestion={vi.fn()}
        onRate={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /copy this answer/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /was helpful/i })).not.toBeInTheDocument();
  });

  it('does not offer them on a streaming answer that has no text yet', () => {
    render(
      <MessageList
        messages={[{ id: 'a1', role: 'assistant', content: '', pending: true }]}
        isSlow={false}
        isStreaming
        onSuggestion={vi.fn()}
        onRate={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /copy this answer/i })).not.toBeInTheDocument();
  });
});
