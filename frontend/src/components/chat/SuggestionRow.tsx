import { orderSuggestions, buildSuggestions, type Suggestion } from './suggestions';
import type { DisplayMessage } from '../../types';

/**
 * Follow-up prompts under an answer.
 *
 * A single non-wrapping row that scrolls sideways when it runs out of room.
 * Wrapping was the wrong shape here: with labels this short, a phone stacked
 * them one per line and the block grew to nearly 200px, pushing the composer
 * off screen. One line is the same height everywhere and is a shape people
 * already recognise from elsewhere on a phone.
 *
 * Rendered only for the newest assistant message that produced a result, so
 * the row always belongs to the answer directly above it, and hidden while a
 * new turn streams so it cannot be double-clicked into sending two questions.
 */
export function SuggestionRow({
  message,
  onSelect,
  disabled,
}: {
  message: DisplayMessage;
  onSelect: (question: string) => void;
  disabled: boolean;
}) {
  const suggestions = orderSuggestions(buildSuggestions(message));
  if (suggestions.length === 0) return null;

  return (
    <div className="suggestions">
      <span className="suggestions-label" id="suggestions-label">
        Follow up
      </span>
      <div className="suggestions-row" role="group" aria-labelledby="suggestions-label">
        {suggestions.map((s: Suggestion) => (
          <button
            key={s.id}
            type="button"
            className="suggestion-chip"
            onClick={() => onSelect(s.question)}
            disabled={disabled}
            // Also surfaced in the UI as a tooltip: a chip answerable from the
            // results already on screen costs nothing extra, and a student
            // should not have to guess which is which.
            title={
              s.needsLookup
                ? 'Runs a fresh search — answer with Enter to send'
                : 'Answered from the results above — no new search'
            }
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
