import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageText } from '../components/chat/MessageText';

describe('MessageText', () => {
  it('renders plain prose as-is', () => {
    render(<MessageText text="Here are some hostel options near campus." />);
    expect(screen.getByText('Here are some hostel options near campus.')).toBeInTheDocument();
  });

  it('renders a fenced code block as a distinct code block', () => {
    const { container } = render(
      <MessageText text={'Here you go:\n```python\nprint("hi")\n```\nLet me know if that helps.'} />,
    );
    expect(container.textContent).toContain('Here you go:');
    expect(container.textContent).toContain('Let me know if that helps.');
    expect(screen.getByText('python')).toBeInTheDocument();
    expect(screen.getByText('print("hi")')).toBeInTheDocument();
  });

  it('renders nothing for empty text', () => {
    const { container } = render(<MessageText text="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
