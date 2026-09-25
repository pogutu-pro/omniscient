import '@testing-library/jest-dom/vitest';

// jsdom does not implement scrollIntoView; components call it for
// auto-scrolling chat history, so stub it out for tests.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
