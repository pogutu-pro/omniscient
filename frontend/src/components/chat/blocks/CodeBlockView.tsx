import { useState } from 'react';
import { CheckIcon } from '../../common/icons';

export function CodeBlockView({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard access can be denied (permissions, insecure context) - not worth surfacing an error for
    }
  };

  return (
    <div className="block-code">
      <div className="block-code-header">
        <span>{language || 'code'}</span>
        <button type="button" className="block-code-copy" onClick={handleCopy}>
          {copied ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <CheckIcon size={12} /> Copied
            </span>
          ) : (
            'Copy'
          )}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}
