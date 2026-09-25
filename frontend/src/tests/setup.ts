import '@testing-library/jest-dom/vitest';

// jsdom does not implement scrollIntoView; components call it for
// auto-scrolling chat history, so stub it out for tests.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom doesn't implement Blob URLs, and vitest's own polyfill chokes on
// jsdom's File objects - the chat composer only uses this for an instant
// local image preview while an attachment uploads, so a stub is enough.
URL.createObjectURL = () => 'blob:mock-url';
URL.revokeObjectURL = () => {};
