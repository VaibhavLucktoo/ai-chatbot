import {describe, expect, it, vi} from 'vitest';
import {ApiError, backend, describeError, request} from './backend';

describe('Live API adapter', () => {
  it('sends the strict backend chat payload through a relative URL', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({answer: 'Supported answer.', sources: []}));
    vi.stubGlobal('fetch', fetch);
    await backend.chat({question: 'What applies?', top_k: 5, document_ids: ['fixture-id']});
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe('/v1/chat');
    expect(JSON.parse(options.body)).toEqual({question: 'What applies?', top_k: 5, document_ids: ['fixture-id']});
    expect(options.signal).toBeDefined();
  });
  it('surfaces errors and Retry-After without returning simulated success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({detail: 'Busy processing.'}, {status: 429, headers: {'Retry-After': '7', 'X-Request-ID': 'trace-id'}})));
    const error = await request('/v1/chat').catch(problem => problem);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(429); expect(error.requestId).toBe('trace-id');
    expect(describeError(error)).toContain('Retry after 7 seconds');
  });
  it('handles successful 204 lifecycle responses without trying to parse JSON', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, {status: 204}));
    vi.stubGlobal('fetch', fetch);
    await backend.activation('document', false);
    await backend.delete('document');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({active: false});
    expect(fetch.mock.calls[1][1].method).toBe('DELETE');
  });
  it('rejects oversized PDFs before making an upload request', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    const file = new File(['fixture'], 'oversized.pdf');
    Object.defineProperty(file, 'size', {value: 10 * 1024 * 1024 + 1});
    await expect(backend.submit(file)).rejects.toThrow('10 MiB');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('retains a missing-source error rather than generating a fake download', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({detail: 'Original PDF is unavailable.'}, {status: 409})));
    await expect(request('/v1/documents/document/source')).rejects.toThrow('Original PDF is unavailable');
  });
  it('downloads binary PDF bytes with the original filename and revokes the object URL', async () => {
    vi.useFakeTimers();
    const create = vi.fn().mockReturnValue('blob:fixture'); const revoke = vi.fn();
    vi.stubGlobal('URL', {createObjectURL: create, revokeObjectURL: revoke});
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('%PDF-1.4 fixture', {headers: {'Content-Type': 'application/pdf'}})));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) {
      expect(this.download).toBe('Original.pdf'); expect(this.href).toBe('blob:fixture');
    });
    await backend.download({id: 'fixture', filename: 'Original.pdf', source_available: true} as any);
    expect(click).toHaveBeenCalledOnce(); expect(create.mock.calls[0][0].type).toBe('application/pdf');
    vi.advanceTimersByTime(2000); expect(revoke).toHaveBeenCalledWith('blob:fixture');
  });
  it('loads all ready-document pages so the scope picker is complete', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json({items: [{id: 'a'}, {id: 'b'}], total: 3, limit: 25, offset: 0}))
      .mockResolvedValueOnce(Response.json({items: [{id: 'c'}], total: 3, limit: 25, offset: 2}));
    vi.stubGlobal('fetch', fetch);
    expect((await backend.readyDocuments()).map(doc => doc.id)).toEqual(['a', 'b', 'c']);
    expect(fetch.mock.calls[1][0]).toContain('offset=2'); expect(fetch.mock.calls[1][0]).toContain('active=true');
  });
});
