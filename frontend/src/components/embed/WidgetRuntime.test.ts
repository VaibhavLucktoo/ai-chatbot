/* DOM-level checks for shipped widget assets; these do not replace browser QA. */
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {fireEvent, waitFor} from '@testing-library/dom';

const assets = resolve(process.cwd(), '../Backend/app/widget');
const config = {widget_id: '11111111-1111-4111-8111-111111111111', revision: 1, title: 'Help', greeting: 'Welcome',
  color: '#2563eb', parent_origin: 'https://shop.example.com'};
let calls: {path: string; payload?: any; token?: string | null}[], results: Response[];
beforeEach(() => {
  calls = []; results = [];
  document.body.innerHTML = readFileSync(resolve(assets, 'index.html'), 'utf8').replace(/<head>[\s\S]*?<\/head>/, '').replace('__CONFIG__', '');
  document.getElementById('configuration')!.dataset.config = JSON.stringify(config);
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    calls.push({path, payload: options.body ? JSON.parse(options.body as string) : undefined, token: new Headers(options.headers).get('X-Widget-Token')});
    if (path.endsWith('/sessions')) return Response.json({session_id: 'session-fixture', token: (calls.filter(item => item.path.endsWith('/sessions')).length === 1 ? 'a' : 'b').repeat(64), expires_at: new Date(Date.now() + 600000).toISOString()});
    if (path.includes('/passages/')) return Response.json({content: '<script>unsafe</script> supporting evidence'});
    return results.shift() || Response.json({answer: '<img src=x onerror="alert(1)"> Answer [1]', sources: [{filename: '<b>Policy</b>', page_number: 2, chunk_id: 'chunk', document_id: 'document'}]});
  }));
});
async function start() {new Function(readFileSync(resolve(assets, 'chat.js'), 'utf8'))(); await waitFor(() => expect((document.getElementById('send') as HTMLButtonElement).disabled).toBe(false));}
async function ask(question: string) {
  (document.getElementById('question') as HTMLTextAreaElement).value = question;
  fireEvent.submit(document.getElementById('form')!);
  await waitFor(() => expect(document.getElementById('status')!.textContent).not.toBe('Thinking…'));
}
describe('Hosted widget runtime', () => {
  it('sends the current schema with a private session and renders answers/sources as text', async () => {
    await start(); await ask('What is the policy?');
    const request = calls.find(item => item.path.endsWith('/chat'))!;
    expect(request.payload).toEqual({question: 'What is the policy?'});
    expect(request.token).toBe('a'.repeat(64));
    expect(document.querySelector('#messages img')).toBeNull();
    expect(document.querySelector('#messages b')).toBeNull();
    const source = Array.from(document.querySelectorAll('#messages button')).find(button => button.textContent?.includes('Policy'))!;
    fireEvent.click(source);
    await waitFor(() => expect(document.querySelector('.passage')?.textContent).toContain('<script>unsafe</script>'));
    expect(document.querySelector('#messages script')).toBeNull();
  });
  it('resends the original question with selected clarification document', async () => {
    results.push(Response.json({status: 'clarification_required', question: 'Choose a document', original_question: 'Explain policy', documents: [{document_id: 'chosen', filename: 'HR.pdf'}]}));
    await start(); await ask('Explain policy');
    fireEvent.click(document.querySelector('.choices button')!);
    await waitFor(() => expect(calls.filter(item => item.path.endsWith('/chat')).length).toBe(2));
    expect(calls.at(-1)?.payload).toEqual({question: 'Explain policy', document_ids: ['chosen']});
    await waitFor(() => expect(document.getElementById('status')!.textContent).toBe('Ready'));
  });
  it('restores a refreshed transcript and rotates the session on new chat', async () => {
    await start(); await ask('Hello');
    const state = JSON.parse(sessionStorage.getItem(`document-widget:${config.widget_id}:${config.parent_origin}`)!);
    expect(state.history[0].result.answer).toContain('Answer');
    document.body.innerHTML = readFileSync(resolve(assets, 'index.html'), 'utf8').replace(/<head>[\s\S]*?<\/head>/, '').replace('__CONFIG__', '');
    document.getElementById('configuration')!.dataset.config = JSON.stringify(config);
    await start();
    expect(document.querySelectorAll('.user').length).toBe(1);
    expect(calls.filter(item => item.path.endsWith('/sessions')).length).toBe(1);
    fireEvent.click(document.getElementById('clear')!);
    await waitFor(() => expect(calls.filter(item => item.path.endsWith('/sessions')).length).toBe(2));
    expect(document.querySelectorAll('.user').length).toBe(0);
    expect(JSON.parse(sessionStorage.getItem(`document-widget:${config.widget_id}:${config.parent_origin}`)!).session.token).not.toBe(state.session.token);
  });
  it('shows quota errors and retry using the original request', async () => {
    results.push(Response.json({detail: 'Widget usage limit reached.'}, {status: 429, headers: {'Retry-After': '30'}}));
    await start(); await ask('Original question');
    expect(document.querySelector('.error')?.textContent).toContain('Retry after 30 seconds');
    fireEvent.click(document.querySelector('.error button')!);
    await waitFor(() => expect(calls.filter(item => item.path.endsWith('/chat')).length).toBe(2));
    expect(calls.at(-1)?.payload).toEqual({question: 'Original question'});
    await waitFor(() => expect(document.getElementById('status')!.textContent).toBe('Ready'));
  });
  it('launches an isolated iframe once and ignores messages from foreign origins', () => {
    const script = document.createElement('script'); script.src = 'https://chat.example.com/widget-assets/loader.js';
    script.dataset.widget = config.widget_id;
    vi.spyOn(document, 'currentScript', 'get').mockReturnValue(script);
    const source = readFileSync(resolve(assets, 'loader.js'), 'utf8'); new Function(source)(); new Function(source)();
    const host = document.getElementById(`document-widget-${config.widget_id}`)!;
    expect(document.querySelectorAll(`#document-widget-${config.widget_id}`).length).toBe(1);
    const button = host.shadowRoot!.querySelector('button')!, frame = host.shadowRoot!.querySelector('iframe')!;
    const chatIcon = button.innerHTML;
    expect(button.querySelector('svg')).not.toBeNull();
    fireEvent.click(button); expect(frame.hidden).toBe(false);
    expect(button.innerHTML).not.toBe(chatIcon);
    expect(new URL(frame.src).searchParams.get('parent_origin')).toBe(window.location.origin);
    expect(frame.getAttribute('sandbox')).toBe('allow-scripts allow-same-origin');
    window.dispatchEvent(new MessageEvent('message', {origin: 'https://evil.example.com', source: frame.contentWindow, data: {type: 'document-widget-close'}}));
    expect(frame.hidden).toBe(false);
    window.dispatchEvent(new MessageEvent('message', {origin: 'https://chat.example.com', source: frame.contentWindow, data: {type: 'document-widget-close'}}));
    expect(frame.hidden).toBe(true);
    expect(button.innerHTML).toBe(chatIcon);
  });
});
