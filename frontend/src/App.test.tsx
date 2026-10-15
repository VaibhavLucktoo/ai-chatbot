import React from 'react';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from './App';
import type {DocumentInfo} from './types/backend';

const firstId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const newId = '33333333-3333-4333-8333-333333333333';
let documents: DocumentInfo[];
let chatResponses: Response[];
let requests: {path: string; method: string; body?: any; key?: string | null}[];
let jobStatus: 'ready' | 'failed';
let offline: boolean;
let notReady: boolean;

beforeEach(() => {
  offline = false; notReady = false; jobStatus = 'ready'; requests = []; chatResponses = [];
  documents = [firstId, secondId].map((id, index) => ({id, filename: index ? 'Second.pdf' : 'First.pdf', page_count: 2,
    chunk_count: 3, status: 'ready', active: true, created_at: '2026-10-12T00:00:00Z', source_available: !index}));
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    if (offline) throw new TypeError('Connection unavailable');
    const url = new URL(input, 'http://127.0.0.1:3000');
    const path = url.pathname; const method = options.method ?? 'GET';
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
    requests.push({path, method, body, key: new Headers(options.headers).get('X-Conversation-Key')});
    if (path === '/v1/assistants') return Response.json([]);
    if (path === '/v1/health') return Response.json({status: 'ok', message: 'Service is healthy'});
    if (path === '/v1/ready') return Response.json({status: notReady ? 'not_ready' : 'ready'}, {status: notReady ? 503 : 200});
    if (path === '/v1/documents' && method === 'GET') {
      const items = url.searchParams.get('active') === 'true' ? documents.filter(doc => doc.active && doc.status === 'ready') : documents;
      return Response.json({items, total: items.length, limit: 25, offset: 0});
    }
    if (path === '/v1/chat') return chatResponses.shift() ?? Response.json({answer: 'Grounded answer. [1]', sources: [
      {document_id: firstId, chunk_id: 'chunk-1', filename: 'First.pdf', page_number: 1},
    ]});
    if (path.endsWith('/chunks/chunk-1')) return Response.json({id: 'chunk-1', document_id: firstId, filename: 'First.pdf', page_number: 1, chunk_index: 0, content: 'The original supporting passage.'});
    if (path === '/v1/documents/jobs' && method === 'POST') {
      documents.push({id: newId, filename: 'New.pdf', page_count: 1, chunk_count: 0, status: 'pending', active: true, source_available: true, created_at: '2026-10-12T00:00:00Z'});
      return Response.json({document_id: newId, filename: 'New.pdf', status: 'pending'}, {status: 202});
    }
    if (path === `/v1/documents/jobs/${newId}`) {
      documents = documents.map(doc => doc.id === newId ? {...doc, status: jobStatus, page_count: 2, chunk_count: jobStatus === 'ready' ? 3 : 0} : doc);
      return Response.json({document_id: newId, filename: 'New.pdf', status: jobStatus});
    }
    if (path.endsWith('/activation')) {
      const id = path.split('/')[3]; documents = documents.map(doc => doc.id === id ? {...doc, active: body.active} : doc);
      return new Response(null, {status: 204});
    }
    if (method === 'DELETE') {documents = documents.filter(doc => doc.id !== path.split('/')[3]); return new Response(null, {status: 204});}
    throw new Error(`Unexpected fixture request: ${method} ${path}`);
  }));
});

async function start() {
  const user = userEvent.setup(); render(<App/>);
  await screen.findByText('Backend ready');
  await screen.findByRole('button', {name: 'All active documents (2)'});
  return user;
}
async function selectDocument(user: ReturnType<typeof userEvent.setup>, filename: string) {
  await user.click(screen.getByRole('button', {name: /All active documents|selected document/}));
  await user.click(screen.getByRole('button', {name: 'Search all'}));
  await user.click(screen.getByRole('checkbox', {name: filename}));
  await user.click(screen.getByRole('button', {name: /selected document/}));
}

describe('Initial connected workspace', () => {
  it('uses one private conversation across turns and starts a fresh one when cleared', async () => {
    chatResponses.push(Response.json({answer: 'Hello! How can I help you today?', sources: []}));
    chatResponses.push(Response.json({answer: "You're welcome!", sources: []}));
    const user = await start();
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'Hello');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText('Hello! How can I help you today?');
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'Thank you');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText("You're welcome!");
    const rows = requests.filter(row => row.path === '/v1/chat');
    expect(rows[0].body.conversation_id).toBe(rows[1].body.conversation_id);
    expect(rows[0].key).toMatch(/^[0-9a-f]{64}$/);
    expect(rows[0].key).toBe(rows[1].key);
    expect(document.body.textContent).not.toContain(rows[0].key);
    await user.click(screen.getByRole('button', {name: 'Clear chat'}));
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'Hello');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText('Grounded answer. [1]');
    const last = requests.filter(row => row.path === '/v1/chat')[2];
    expect(last.body.conversation_id).not.toBe(rows[0].body.conversation_id);
    expect(last.key).not.toBe(rows[0].key);
  });
  it('answers a selected-document question and loads an original cited passage', async () => {
    const user = await start(); await selectDocument(user, 'First.pdf');
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'What does the policy say?');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText('Grounded answer. [1]');
    expect(requests.find(row => row.path === '/v1/chat')?.body).toEqual({question: 'What does the policy say?', top_k: 5, document_ids: [firstId], conversation_id: expect.any(String)});
    await user.click(screen.getByRole('button', {name: 'Inspect source 1: First.pdf, page 1'}));
    await screen.findByText('The original supporting passage.');
  });
  it('resends the original question and top_k after choosing a clarification document', async () => {
    chatResponses.push(Response.json({status: 'clarification_required', question: 'Which document?', original_question: 'Explain this document', top_k: 3,
      documents: [{document_id: secondId, filename: 'Second.pdf'}]}));
    const user = await start();
    await user.selectOptions(screen.getByRole('combobox', {name: 'Number of passages'}), '3');
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'Explain this document');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText('Which document?');
    await user.click(screen.getByRole('button', {name: 'Second.pdf'}));
    await screen.findByText('Grounded answer. [1]');
    expect(requests.filter(row => row.path === '/v1/chat')[1].body).toEqual({question: 'Explain this document', top_k: 3, document_ids: [secondId], conversation_id: expect.any(String)});
  });
  it('retries an older failed request with its original scope after another question', async () => {
    chatResponses.push(Response.json({detail: 'Provider unavailable'}, {status: 503}));
    const user = await start(); await selectDocument(user, 'First.pdf');
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'First question');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText('Provider unavailable');
    await selectDocument(user, 'Second.pdf');
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'Second question');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await screen.findByText('Grounded answer. [1]');
    await user.click(screen.getByRole('button', {name: 'Retry original question'}));
    await waitFor(() => expect(requests.filter(row => row.path === '/v1/chat')).toHaveLength(3));
    expect(requests.filter(row => row.path === '/v1/chat')[2].body).toEqual({question: 'First question', top_k: 5, document_ids: [firstId], conversation_id: expect.any(String)});
  });
  it('submits a durable PDF job and polls it to a ready library record', async () => {
    const user = await start(); await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    await user.upload(screen.getByLabelText('Choose PDF'), new File(['%PDF fixture'], 'New.pdf', {type: 'application/pdf'}));
    await user.click(screen.getByRole('button', {name: 'Upload PDF'}));
    await screen.findByText(/PDF received/);
    await waitFor(() => expect(documents.find(doc => doc.id === newId)?.status).toBe('ready'), {timeout: 5000});
    await screen.findByRole('heading', {name: 'New.pdf'});
    expect(requests.some(row => row.path === `/v1/documents/jobs/${newId}`)).toBe(true);
    expect(requests.some(row => row.path === '/v1/documents/upload')).toBe(false);
  });
  it('shows a failed job without claiming ingestion succeeded', async () => {
    jobStatus = 'failed'; const user = await start();
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    await user.upload(screen.getByLabelText('Choose PDF'), new File(['%PDF fixture'], 'New.pdf', {type: 'application/pdf'}));
    await user.click(screen.getByRole('button', {name: 'Upload PDF'}));
    await screen.findByText(/An upload failed/, {}, {timeout: 5000});
    expect(documents.find(doc => doc.id === newId)?.status).toBe('failed');
  });
  it('enforces the same 10 MiB limit for drag/drop', async () => {
    const user = await start(); await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    const oversized = new File(['fixture'], 'huge.pdf', {type: 'application/pdf'});
    Object.defineProperty(oversized, 'size', {value: 10 * 1024 * 1024 + 1});
    fireEvent.drop(screen.getByText('Add a PDF').closest('div')!.parentElement!.parentElement!, {dataTransfer: {files: [oversized]}});
    await screen.findByText('Maximum PDF size is 10 MiB.');
    expect(requests.some(row => row.method === 'POST')).toBe(false);
  });
  it('retires and reactivates a document using the real lifecycle contract', async () => {
    const user = await start(); await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    await user.click(screen.getAllByRole('button', {name: 'Retire'})[0]);
    await screen.findByText('Retired');
    expect(documents[0].active).toBe(false);
    await user.click(screen.getByRole('button', {name: 'Reactivate'}));
    await waitFor(() => expect(documents[0].active).toBe(true));
  });
  it('never deletes before explicit confirmation and supports cancellation', async () => {
    const user = await start(); await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    await user.click(screen.getByRole('button', {name: 'Delete First.pdf'}));
    const dialog = screen.getByRole('dialog');
    expect(requests.filter(row => row.method === 'DELETE')).toHaveLength(0);
    await user.click(within(dialog).getByRole('button', {name: 'Cancel'}));
    expect(requests.filter(row => row.method === 'DELETE')).toHaveLength(0);
    await user.click(screen.getByRole('button', {name: 'Delete First.pdf'}));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Delete permanently'}));
    await waitFor(() => expect(documents.some(doc => doc.id === firstId)).toBe(false));
    expect(requests.filter(row => row.method === 'DELETE')).toHaveLength(1);
  });
  it('removes a pending upload immediately and ignores its stale in-flight poll', async () => {
    const fetch = vi.mocked(globalThis.fetch);
    const original = fetch.getMockImplementation()!;
    let releasePoll: ((response: Response) => void) | undefined;
    fetch.mockImplementation((input, options) => {
      if (input === `/v1/documents/jobs/${newId}`) return new Promise<Response>(resolve => {releasePoll = resolve;});
      return original(input, options);
    });
    const user = await start();
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    await user.upload(screen.getByLabelText('Choose PDF'), new File(['%PDF fixture'], 'New.pdf', {type: 'application/pdf'}));
    await user.click(screen.getByRole('button', {name: 'Upload PDF'}));
    await screen.findByText(/PDF received/);
    await waitFor(() => expect(releasePoll).toBeDefined(), {timeout: 4000});
    await user.click(screen.getByRole('button', {name: 'Delete New.pdf'}));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Delete permanently'}));
    await waitFor(() => expect(screen.queryByText('New.pdf')).toBeNull());
    releasePoll!(Response.json({document_id: newId, filename: 'New.pdf', status: 'pending'}));
    await waitFor(() => expect(screen.queryByText('Upload activity')).toBeNull());
    expect(screen.queryByText('New.pdf')).toBeNull();
  });
  it('dismisses a stale row when retrying an already completed delete returns 404', async () => {
    const fetch = vi.mocked(globalThis.fetch);
    const original = fetch.getMockImplementation()!;
    fetch.mockImplementation((input, options) => {
      if (input === `/v1/documents/${firstId}` && options?.method === 'DELETE') {
        documents = documents.filter(doc => doc.id !== firstId);
        return Promise.resolve(Response.json({detail: 'Document not found.'}, {status: 404}));
      }
      return original(input, options);
    });
    const user = await start();
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    await user.click(screen.getByRole('button', {name: 'Delete First.pdf'}));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Delete permanently'}));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText('First.pdf')).toBeNull();
  });
  it('disables a legacy missing-source download', async () => {
    const user = await start(); await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: /^Documents/}));
    expect((screen.getByRole('button', {name: 'Download Second.pdf'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('shows actual offline errors without fabricated ready status', async () => {
    offline = true; render(<App/>);
    await screen.findByText('Backend offline');
    expect((screen.getByRole('button', {name: 'Send question'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Status'}));
    await screen.findByText('Offline');
    expect(screen.queryByText('LLM Configuration')).toBeNull();
  });
  it('distinguishes API liveness from dependency readiness', async () => {
    notReady = true; render(<App/>);
    await screen.findByText('Check readiness');
    fireEvent.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Status'}));
    await screen.findByText('Online'); await screen.findByText('Not ready');
  });
});
