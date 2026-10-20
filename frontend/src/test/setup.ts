import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})

// jsdom has no layout engine; Recharts measures its container through ResizeObserver.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
// jsdom reports every element as 0x0, so Recharts would render nothing. Give charts a fixed layout box.
Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
  return { width: 720, height: 340, top: 0, left: 0, right: 720, bottom: 340, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
}
