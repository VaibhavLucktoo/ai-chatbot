import React from 'react';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../../App';
import type {Assistant, ProviderConnection} from '../../types/assistants';
import type {DocumentInfo} from '../../types/backend';

const hrId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const itId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const firstId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const connectionId = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
let assistants: Assistant[];
let connections: ProviderConnection[];
let requests: {path: string; body: any; headers: Headers}[];
let documents: DocumentInfo[];
let modelFailure: boolean;

beforeEach(() => {
  requests = []; modelFailure = false;
  documents = [firstId, secondId].map((id, index) => ({id, filename: index ? 'IT.pdf' : 'HR.pdf', page_count: 1,
    chunk_count: 1, status: 'ready', active: true, source_available: true, created_at: '2026-10-13T00:00:00Z'}));
  connections = [{id: connectionId, name: 'Existing Groq', provider: 'groq', active: true, revision: 1,
    created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z'}];
  assistants = [hrId, itId].map((id, index) => ({id, name: index ? 'IT assistant' : 'HR assistant', description: '',
    connection_id: connectionId, provider: 'groq', model: 'openai/gpt-oss-120b', document_ids: [index ? secondId : firstId],
    active: true, revision: 1, max_output_tokens: 2048, context_window_tokens: 32768, temperature: 0, timeout_seconds: 120,
    created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z'}));
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const url = new URL(input, 'http://127.0.0.1:3000'); const path = url.pathname;
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : undefined;
    const headers = new Headers(options.headers); requests.push({path, body, headers});
    if (options.method === 'DELETE') {
      const id = path.split('/').at(-1);
      if (path.includes('/connections/')) {
        if (assistants.some(item => item.connection_id === id)) return Response.json({detail: 'Connection is used by an assistant.'}, {status: 409});
        connections = connections.filter(item => item.id !== id);
      } else assistants = assistants.filter(item => item.id !== id);
      return new Response(null, {status: 204});
    }
    if (path === '/v1/health') return Response.json({status: 'ok'});
    if (path === '/v1/ready') return Response.json({status: 'ready'});
    if (path === '/v1/documents') return Response.json({items: documents, total: documents.length, limit: 25, offset: 0});
    if (path === '/v1/assistants') return Response.json(assistants.filter(item => item.active));
    if (path === '/v1/admin/assistants' && !body) return Response.json(assistants);
    if (options.method === 'PUT' && path.startsWith('/v1/admin/assistants/')) {
      const id = path.split('/').at(-1);
      assistants = assistants.map(item => item.id === id ? {...item, ...body} : item);
      return Response.json(assistants.find(item => item.id === id));
    }
    if (path === '/v1/admin/session') return Response.json({token: 'local-test-admin'});
    if (path === '/v1/admin/providers') return Response.json({items: [{id: 'groq', name: 'Groq'}, {id: 'gemini', name: 'Google Gemini'}]});
    if (path === '/v1/admin/connections' && !body) return Response.json(connections);
    if (path === '/v1/admin/connections' && body) {
      const connection = {id: connectionId, name: body.name, provider: body.provider, active: true, revision: 1,
        created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z'};
      connections.push(connection); return Response.json(connection, {status: 201});
    }
    if (path.endsWith('/models')) return Response.json({items: ['openai/gpt-oss-120b']});
    if (path === '/v1/admin/connections/test') return modelFailure
      ? Response.json({detail: 'The provider rejected the API key or model access.'}, {status: 422})
      : Response.json({status: 'ok', model: body.model, provider: 'groq'});
    if (path === '/v1/admin/assistants' && body) {
      const assistant = {...body, id: hrId, provider: 'groq', revision: 1,
        created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z'};
      assistants.push(assistant); return Response.json(assistant, {status: 201});
    }
    if (path === '/v1/chat') return Response.json({answer: body.assistant_id === itId ? 'IT answer.' : 'HR answer.', sources: []});
    throw new Error(`Unexpected fixture request: ${path}`);
  }));
});

describe('Assistant configuration and chat isolation', () => {
  it('keeps separate histories, conversation credentials and assigned-document pickers', async () => {
    const user = userEvent.setup(); render(<App/>); await screen.findByText('Backend ready');
    await screen.findByRole('option', {name: 'HR assistant'});
    await user.selectOptions(screen.getByRole('combobox', {name: 'Chat assistant'}), hrId);
    await user.click(screen.getByRole('button', {name: 'All assigned documents (1)'}));
    expect(screen.getByRole('checkbox', {name: 'HR.pdf'})).toBeTruthy();
    expect(screen.queryByRole('checkbox', {name: 'IT.pdf'})).toBeNull();
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'HR question');
    await user.click(screen.getByRole('button', {name: 'Send question'})); await screen.findByText('HR answer.');
    await user.selectOptions(screen.getByRole('combobox', {name: 'Chat assistant'}), itId);
    expect(screen.queryByText('HR answer.')).toBeNull();
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'IT question');
    await user.click(screen.getByRole('button', {name: 'Send question'})); await screen.findByText('IT answer.');
    await user.selectOptions(screen.getByRole('combobox', {name: 'Chat assistant'}), hrId);
    await screen.findByText('HR answer.'); expect(screen.queryByText('IT answer.')).toBeNull();
    await user.type(screen.getByRole('textbox', {name: 'Your question'}), 'HR follow-up');
    await user.click(screen.getByRole('button', {name: 'Send question'}));
    await waitFor(() => expect(requests.filter(item => item.path === '/v1/chat')).toHaveLength(3));
    const calls = requests.filter(item => item.path === '/v1/chat');
    expect(calls.map(item => item.body.assistant_id)).toEqual([hrId, itId, hrId]);
    expect(calls[0].body.conversation_id).not.toBe(calls[1].body.conversation_id);
    expect(calls[0].headers.get('X-Conversation-Key')).not.toBe(calls[1].headers.get('X-Conversation-Key'));
    expect(calls[0].body.conversation_id).toBe(calls[2].body.conversation_id);
  });

  it('saves a key without browser persistence, tests a model and assigns documents', async () => {
    connections = []; assistants = [];
    const user = userEvent.setup(); render(<App/>); await screen.findByText('Backend ready');
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Models'}));
    await screen.findByText('Add a connection to get started.');
    fireEvent.change(screen.getByRole('textbox', {name: 'Connection name'}), {target: {value: 'My Groq'}});
    const key = screen.getByLabelText('Provider API key') as HTMLInputElement;
    expect(key.type).toBe('password'); fireEvent.change(key, {target: {value: 'private-test-key'}});
    await user.click(screen.getByRole('button', {name: 'Save connection'}));
    await screen.findByText('Provider connection saved. The key is stored encrypted.');
    expect(key.value).toBe(''); expect(JSON.stringify({...localStorage, ...sessionStorage})).not.toContain('private-test-key');
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Assistants'}));
    await screen.findByRole('option', {name: 'My Groq (groq)'});
    await user.selectOptions(screen.getByRole('combobox', {name: 'Assistant connection'}), connectionId);
    fireEvent.change(screen.getByRole('textbox', {name: 'Assistant name'}), {target: {value: 'New HR'}});
    fireEvent.change(screen.getByRole('combobox', {name: 'Assistant model'}), {target: {value: 'openai/gpt-oss-120b'}});
    await user.click(screen.getByRole('checkbox', {name: 'Assign HR.pdf'}));
    expect((screen.getByRole('button', {name: 'Save assistant'}) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole('button', {name: 'Test selected model'})); await screen.findByText('Connection test passed.');
    await user.click(screen.getByRole('button', {name: 'Save assistant'}));
    await screen.findByText('Assistant saved. New chat requests use these settings.');
    const saved = requests.find(item => item.path === '/v1/admin/assistants' && item.body);
    expect(saved?.body.document_ids).toEqual([firstId]); expect(saved?.body.connection_id).toBe(connectionId);
    expect(saved?.body).not.toHaveProperty('api_key'); expect(saved?.headers.get('X-Admin-Token')).toBeTruthy();
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Chat'}));
    await screen.findByRole('option', {name: 'New HR'});
  });

  it('shows provider failure and prevents saving an untested model', async () => {
    modelFailure = true;
    const user = userEvent.setup(); render(<App/>); await screen.findByText('Backend ready');
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Assistants'}));
    await screen.findByRole('option', {name: 'Existing Groq (groq)'});
    await user.type(screen.getByRole('textbox', {name: 'Assistant name'}), 'New HR');
    await user.selectOptions(screen.getByRole('combobox', {name: 'Assistant connection'}), connectionId);
    await user.type(screen.getByRole('combobox', {name: 'Assistant model'}), 'openai/gpt-oss-120b');
    await user.click(screen.getByRole('button', {name: 'Test selected model'}));
    await screen.findByText('The provider rejected the API key or model access.');
    expect((screen.getByRole('button', {name: 'Save assistant'}) as HTMLButtonElement).disabled).toBe(true);
    expect(requests.some(item => item.path === '/v1/admin/assistants' && item.body)).toBe(false);
  });

  it('keeps Models separate and prevents deleting referenced connections', async () => {
    const user = userEvent.setup(); render(<App/>); await screen.findByText('Backend ready');
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Models'}));
    await screen.findByRole('button', {name: 'Delete connection Existing Groq'});
    expect((screen.getByRole('button', {name: 'Delete connection Existing Groq'}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('textbox', {name: 'Assistant name'})).toBeNull();
    expect(screen.getByText(/Key saved/)).toBeTruthy();
  });

  it('requires confirmation for assistant deletion and clears its local history', async () => {
    const user = userEvent.setup(); render(<App/>); await screen.findByRole('option', {name: 'HR assistant'});
    await user.selectOptions(screen.getByRole('combobox', {name: 'Chat assistant'}), hrId);
    await waitFor(() => expect(sessionStorage.getItem(`pdf-assistant-chat-v1:${hrId}`)).not.toBeNull());
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Assistants'}));
    await screen.findByRole('button', {name: 'Delete assistant HR assistant'});
    await user.click(screen.getByRole('button', {name: 'Delete assistant HR assistant'}));
    expect(requests.some(item => item.path === `/v1/admin/assistants/${hrId}`)).toBe(false);
    expect(document.activeElement).toBe(within(screen.getByRole('dialog')).getByRole('button', {name: 'Cancel'}));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.click(screen.getByRole('button', {name: 'Delete assistant HR assistant'}));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Cancel'}));
    expect(requests.some(item => item.path === `/v1/admin/assistants/${hrId}`)).toBe(false);
    await user.click(screen.getByRole('button', {name: 'Delete assistant HR assistant'}));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Delete permanently'}));
    await screen.findByText('Configuration deleted.');
    expect(assistants.some(item => item.id === hrId)).toBe(false);
    expect(sessionStorage.getItem(`pdf-assistant-chat-v1:${hrId}`)).toBeNull();
    expect(sessionStorage.getItem('pdf-assistant-selected')).toBeNull();
  });

  it('deletes an unused connection with confirmation and handles its empty response', async () => {
    assistants = [];
    const user = userEvent.setup(); render(<App/>); await screen.findByText('Backend ready');
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Models'}));
    await screen.findByRole('button', {name: 'Delete connection Existing Groq'});
    await user.click(screen.getByRole('button', {name: 'Delete connection Existing Groq'}));
    expect(connections).toHaveLength(1);
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Delete permanently'}));
    await screen.findByText('Configuration deleted.'); expect(connections).toHaveLength(0);
  });

  it('saves an active-status change without requiring another provider call', async () => {
    const user = userEvent.setup(); render(<App/>); await screen.findByText('Backend ready');
    await user.click(within(screen.getByRole('navigation', {name: 'Main navigation'})).getByRole('button', {name: 'Assistants'}));
    await screen.findByRole('button', {name: 'Edit assistant HR assistant'});
    await user.click(screen.getByRole('button', {name: 'Edit assistant HR assistant'}));
    await user.click(screen.getByRole('checkbox', {name: 'Assistant active'}));
    await user.click(screen.getByRole('button', {name: 'Save assistant'}));
    await screen.findByText('Assistant saved. New chat requests use these settings.');
    expect(assistants.find(item => item.id === hrId)?.active).toBe(false);
    expect(requests.some(item => item.path === '/v1/admin/connections/test')).toBe(false);
  });
});
