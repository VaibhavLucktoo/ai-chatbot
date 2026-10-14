import {afterEach, beforeEach, vi} from 'vitest';
import {cleanup} from '@testing-library/react';

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  HTMLElement.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
});
