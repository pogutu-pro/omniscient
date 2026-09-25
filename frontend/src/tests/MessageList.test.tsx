import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageList } from '../components/chat/MessageList';
import type { DisplayMessage } from '../types';

describe('MessageList', () => {
  it('shows suggestion prompts when there are no messages yet', async () => {
    const user = userEvent.setup();
    const onSuggestion = vi.fn();
    render(<MessageList messages={[]} onSuggestion={onSuggestion} />);

    expect(screen.getByText('What can I help with?')).toBeInTheDocument();
    const suggestion = screen.getByText('Find me a hostel under KSh 8,000 near Boma');
    await user.click(suggestion);
    expect(onSuggestion).toHaveBeenCalledWith('Find me a hostel under KSh 8,000 near Boma');
  });

  it('renders user and assistant messages with the right roles', () => {
    const messages: DisplayMessage[] = [
      { id: '1', role: 'user', content: 'Find me a hostel' },
      { id: '2', role: 'assistant', content: 'Here are some options', pending: false },
    ];
    render(<MessageList messages={messages} onSuggestion={vi.fn()} />);

    expect(screen.getByText('Find me a hostel')).toBeInTheDocument();
    expect(screen.getByText('Here are some options')).toBeInTheDocument();
  });
});
