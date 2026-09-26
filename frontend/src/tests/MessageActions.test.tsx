import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageActions } from '../components/chat/MessageActions';

/**
 * jsdom exposes `navigator.clipboard` and `navigator.share` as getter-only
 * properties, so they have to be redefined rather than assigned.
 */
function mockNavigator(props: Record<string, unknown>) {
  for (const [key, value] of Object.entries(props)) {
    Object.defineProperty(navigator, key, { value, configurable: true, writable: true });
  }
}

function setup(props: Partial<React.ComponentProps<typeof MessageActions>> = {}) {
  const onRate = vi.fn();
  render(
    <MessageActions text="Here are 5 hostels near campus." onRate={onRate} ratingPending={false} {...props} />,
  );
  return { onRate };
}

describe('MessageActions', () => {
  it('offers copy, share and both thumbs', () => {
    setup();
    expect(screen.getByRole('button', { name: /copy this answer/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /share this answer/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /was helpful/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /was not helpful/i })).toBeInTheDocument();
  });

  it('copies the answer and confirms it', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockNavigator({ clipboard: { writeText } });
    setup();

    await user.click(screen.getByRole('button', { name: /copy this answer/i }));

    expect(writeText).toHaveBeenCalledWith('Here are 5 hostels near campus.');
    expect(await screen.findByText('Copied')).toBeInTheDocument();
  });

  it('strips code fences from what it copies', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockNavigator({ clipboard: { writeText } });
    setup({ text: 'Answer:\n```python\nprint(1)\n```' });

    await user.click(screen.getByRole('button', { name: /copy this answer/i }));

    expect(writeText).toHaveBeenCalledWith('Answer:\nprint(1)');
  });

  it('offers the OS share sheet when the platform has one', async () => {
    const user = userEvent.setup();
    const share = vi.fn().mockResolvedValue(undefined);
    mockNavigator({ share });
    setup();

    await user.click(screen.getByRole('button', { name: /share this answer/i }));

    // The full answer travels, not the closing sentence.
    expect(share).toHaveBeenCalledWith(
      expect.objectContaining({ text: expect.stringContaining('Here are 5 hostels near campus.') }),
    );
  });

  it('falls back to the explicit menu when the share sheet is dismissed', async () => {
    // Cancelling the OS sheet rejects. The button must not become a dead
    // end, so the popout of destinations opens instead.
    const user = userEvent.setup();
    const share = vi.fn().mockRejectedValue(new Error('cancelled'));
    mockNavigator({ share });
    setup();

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /share this answer/i }));

    expect(await screen.findByRole('menu')).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /whatsapp/i })).toBeInTheDocument();
  });

  it('opens the menu directly where there is no share sheet', async () => {
    const user = userEvent.setup();
    mockNavigator({ share: undefined });
    setup();

    await user.click(screen.getByRole('button', { name: /share this answer/i }));

    expect(await screen.findByRole('menu')).toBeInTheDocument();
  });

  it('closes the menu on Escape and returns focus to the button', async () => {
    const user = userEvent.setup();
    mockNavigator({ share: undefined });
    setup();

    const trigger = screen.getByRole('button', { name: /share this answer/i });
    await user.click(trigger);
    expect(await screen.findByRole('menu')).toBeInTheDocument();

    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it('copies the results table, not just the prose', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockNavigator({ clipboard: { writeText } });
    setup({
      text: 'I found 2 hostels — see the details below.',
      blocks: [
        {
          type: 'table',
          title: 'Hostels near campus',
          columns: [
            { key: 'name', label: 'Name', align: 'left' },
            { key: 'price', label: 'Price', align: 'right' },
          ],
          rows: [{ name: 'MNM', price: 'KSh 8,000' }],
        },
      ],
    });

    await user.click(screen.getByRole('button', { name: /copy this answer/i }));

    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain('MNM');
    expect(copied).toContain('KSh 8,000');
    expect(copied).toContain('see the details below');
  });

  it('rates helpful', async () => {
    const user = userEvent.setup();
    const { onRate } = setup();

    await user.click(screen.getByRole('button', { name: /was helpful/i }));

    expect(onRate).toHaveBeenCalledWith(1);
  });

  it('rates not helpful', async () => {
    const user = userEvent.setup();
    const { onRate } = setup();

    await user.click(screen.getByRole('button', { name: /was not helpful/i }));

    expect(onRate).toHaveBeenCalledWith(-1);
  });

  it('clears the rating when the lit thumb is pressed again', async () => {
    const user = userEvent.setup();
    const { onRate } = setup({ rating: 1 });

    await user.click(screen.getByRole('button', { name: /was helpful/i }));

    expect(onRate).toHaveBeenCalledWith(null);
  });

  it('switches rather than stacks when the other thumb is pressed', async () => {
    const user = userEvent.setup();
    const { onRate } = setup({ rating: 1 });

    await user.click(screen.getByRole('button', { name: /was not helpful/i }));

    expect(onRate).toHaveBeenCalledWith(-1);
  });

  it('marks the pressed thumb for assistive tech', () => {
    setup({ rating: -1 });
    expect(screen.getByRole('button', { name: /was not helpful/i })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /was helpful/i })).toHaveAttribute('aria-pressed', 'false');
  });

  it('disables the thumbs while a rating is in flight', () => {
    setup({ ratingPending: true });
    expect(screen.getByRole('button', { name: /was helpful/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /was not helpful/i })).toBeDisabled();
  });
});
