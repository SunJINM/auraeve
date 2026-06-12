import '@testing-library/jest-dom/vitest'

Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: () => {},
})

Object.defineProperty(window.HTMLElement.prototype, 'scrollTo', {
  configurable: true,
  value: () => {},
})

if (!('ResizeObserver' in globalThis)) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}
