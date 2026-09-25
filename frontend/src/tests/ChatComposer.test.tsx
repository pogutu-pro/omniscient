import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatComposer } from '../components/chat/ChatComposer';

describe('ChatComposer', () => {
  it('sends the trimmed message and clears the input on submit', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} disabled={false} hasActivity={false} onToggleActivity={vi.fn()} />);

    const textarea = screen.getByLabelText('Message Omniscient');
    await user.type(textarea, '  Find me a hostel  ');
    await user.click(screen.getByLabelText('Send message'));

    expect(onSend).toHaveBeenCalledWith('Find me a hostel');
    expect(textarea).toHaveValue('');
  });

  it('submits on Enter but not on Shift+Enter', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} disabled={false} hasActivity={false} onToggleActivity={vi.fn()} />);

    const textarea = screen.getByLabelText('Message Omniscient');
    await user.type(textarea, 'Hello');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(onSend).not.toHaveBeenCalled();

    await user.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledWith('Hello');
  });

  it('disables the send button while streaming or when empty', () => {
    render(<ChatComposer onSend={vi.fn()} disabled={true} hasActivity={false} onToggleActivity={vi.fn()} />);
    expect(screen.getByLabelText('Send message')).toBeDisabled();
  });

  it('hides the mobile activity toggle until there is activity to show', () => {
    const { rerender } = render(
      <ChatComposer onSend={vi.fn()} disabled={false} hasActivity={false} onToggleActivity={vi.fn()} />,
    );
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();

    rerender(<ChatComposer onSend={vi.fn()} disabled={false} hasActivity={true} onToggleActivity={vi.fn()} />);
    expect(screen.getByText('Activity')).toBeInTheDocument();
  });
});
