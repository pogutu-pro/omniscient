import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatComposer } from '../components/chat/ChatComposer';

describe('ChatComposer', () => {
  it('sends the trimmed message and clears the input on submit', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} disabled={false} onToggleActivity={vi.fn()} activityCount={0} />);

    const textarea = screen.getByLabelText('Message Omniscient');
    await user.type(textarea, '  Find me a hostel  ');
    await user.click(screen.getByLabelText('Send message'));

    expect(onSend).toHaveBeenCalledWith('Find me a hostel');
    expect(textarea).toHaveValue('');
  });

  it('submits on Enter but not on Shift+Enter', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} disabled={false} onToggleActivity={vi.fn()} activityCount={0} />);

    const textarea = screen.getByLabelText('Message Omniscient');
    await user.type(textarea, 'Hello');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(onSend).not.toHaveBeenCalled();

    await user.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledWith('Hello');
  });

  it('disables the send button while streaming or when empty', () => {
    render(<ChatComposer onSend={vi.fn()} disabled={true} onToggleActivity={vi.fn()} activityCount={0} />);
    expect(screen.getByLabelText('Send message')).toBeDisabled();
  });

  it('shows the activity count on the mobile toggle button', () => {
    render(<ChatComposer onSend={vi.fn()} disabled={false} onToggleActivity={vi.fn()} activityCount={3} />);
    expect(screen.getByText('Activity (3)')).toBeInTheDocument();
  });
});
