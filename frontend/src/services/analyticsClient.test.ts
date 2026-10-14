import {beforeEach, describe, expect, it, vi} from 'vitest';
beforeEach(() => {vi.resetModules();});

describe('Local admin metrics client', () => {
  it('uses a memory-only admin token in a header and encodes filters', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json({token: 'private-admin-token'})).mockResolvedValueOnce(Response.json({requests: {total: 1}}));
    vi.stubGlobal('fetch', fetch);
    const {backend} = await import('./backend');
    await backend.analytics(168, 'model/name', 25, {assistant: 'assistant-id', provider: 'api.groq.com'});
    expect(fetch.mock.calls[0][0]).toBe('/v1/admin/session');
    const [path, options] = fetch.mock.calls[1];
    expect(path).toContain('model=model%2Fname');
    expect(path).toContain('assistant_id=assistant-id');
    expect(path).toContain('provider=api.groq.com');
    expect(path).not.toContain('private-admin-token');
    expect(new Headers(options.headers).get('X-Admin-Token')).toBe('private-admin-token');
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });
  it('refreshes the local admin token once after a backend restart', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json({token: 'old'}))
      .mockResolvedValueOnce(Response.json({detail: 'Session expired'}, {status: 403}))
      .mockResolvedValueOnce(Response.json({token: 'new'})).mockResolvedValueOnce(Response.json({requests: {total: 2}}));
    vi.stubGlobal('fetch', fetch);
    const {backend} = await import('./backend');
    const result = await backend.analytics();
    expect(result.requests.total).toBe(2);
    expect(new Headers(fetch.mock.calls[3][1].headers).get('X-Admin-Token')).toBe('new');
  });
});
