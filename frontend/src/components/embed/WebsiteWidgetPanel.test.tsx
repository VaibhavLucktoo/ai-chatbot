import React from 'react';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {WebsiteWidgetPanel, embedCode} from './WebsiteWidgetPanel';
import {backend} from '../../services/backend';
import type {WebsiteWidget} from '../../types/widgets';

const identifier = '11111111-1111-4111-8111-111111111111';
let widget: WebsiteWidget | null;
const fixture = (): WebsiteWidget => ({id: identifier, assistant_id: identifier, enabled: true, title: 'HR Assistant', greeting: 'Welcome!',
  color: '#2563eb', position: 'right', allowed_origins: ['http://127.0.0.1:3000', 'https://shop.example.com'],
  requests_per_minute: 20, requests_per_day: 500, revision: 1, public_origin: 'http://127.0.0.1:8000', public_access_enabled: false, requests_today: 3});
beforeEach(() => {
  widget = fixture();
  vi.spyOn(backend, 'adminAssistants').mockResolvedValue([{id: identifier, name: 'HR', active: true} as any]);
  vi.spyOn(backend, 'widget').mockImplementation(async () => widget);
  vi.spyOn(backend, 'saveWidget').mockImplementation(async (_, payload) => widget = {...fixture(), ...payload, revision: 2});
  vi.spyOn(backend, 'chat').mockResolvedValue({answer: 'Preview answer from assigned documents.', sources: []});
});
describe('Website widget administration', () => {
  it('saves only editable settings and updates copyable code after saving', async () => {
    render(<WebsiteWidgetPanel/>);
    const title = await screen.findByLabelText('Chat title');
    await waitFor(() => expect((title as HTMLInputElement).value).toBe('HR Assistant'));
    fireEvent.change(title, {target: {value: 'Website help'}});
    fireEvent.change(screen.getByLabelText('Allowed websites'), {target: {value: 'https://shop.example.com\nhttps://help.example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save widget'}));
    await screen.findByText('Widget saved. Copy the code below to your approved website.');
    expect(backend.saveWidget).toHaveBeenCalledWith(identifier, expect.objectContaining({title: 'Website help', allowed_origins: ['https://shop.example.com', 'https://help.example.com']}));
    const payload = vi.mocked(backend.saveWidget).mock.calls[0][1];
    expect(payload).not.toHaveProperty('id'); expect(payload).not.toHaveProperty('revision');
    expect(screen.getByLabelText('Widget embed code').textContent).toContain('data-title="Website help"');
    fireEvent.click(screen.getByRole('button', {name: 'Inline iframe'}));
    expect(screen.getByLabelText('Widget embed code').textContent).toContain('parent_origin=https%3A%2F%2Fshop.example.com');
  });
  it('opens a disabled widget preview with unsaved changes and retains chat while collapsed', async () => {
    widget = {...fixture(), enabled: false, allowed_origins: ['https://shop.example.com']}; render(<WebsiteWidgetPanel/>);
    await screen.findByText(/3 \/ 500 questions today/);
    expect((screen.getByRole('button', {name: 'Open widget preview'}) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', {name: 'Copy embed code'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Chat title'), {target: {value: 'Unsaved preview title'}});
    fireEvent.click(screen.getByRole('button', {name: 'Open widget preview'}));
    const chat = screen.getByRole('region', {name: 'Assistant preview chat'});
    expect(within(chat).getByRole('heading').textContent).toBe('Unsaved preview title');
    expect(chat.hasAttribute('hidden')).toBe(false);
    fireEvent.change(screen.getByLabelText('Preview question'), {target: {value: 'What is the policy?'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send preview question'}));
    await screen.findByText('Preview answer from assigned documents.');
    const [payload, key] = vi.mocked(backend.chat).mock.calls[0];
    expect(payload.assistant_id).toBe(identifier); expect(payload.question).toBe('What is the policy?');
    expect(payload.conversation_id).toMatch(/^[a-f0-9-]{36}$/); expect(key).toMatch(/^[a-f0-9]{64}$/);
    expect(screen.getByRole('button', {name: 'Close widget preview'}).getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(screen.getByRole('button', {name: 'Close widget preview'}));
    expect(chat.hasAttribute('hidden')).toBe(true);
    fireEvent.click(screen.getByRole('button', {name: 'Open widget preview'}));
    expect(screen.getByRole('region', {name: 'Assistant preview chat'})).toBe(chat);
    expect(screen.getByText('Preview answer from assigned documents.')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Close preview chat'}));
    await waitFor(() => expect(chat.hasAttribute('hidden')).toBe(true));
    expect(document.activeElement).toBe(screen.getByRole('button', {name: 'Open widget preview'}));
    expect(backend.saveWidget).not.toHaveBeenCalled();
    expect(widget?.enabled).toBe(false);
  });
  it('previews an unsaved widget without enabling website access', async () => {
    widget = null; render(<WebsiteWidgetPanel/>);
    await screen.findByText('Save your widget to generate its embed code.');
    fireEvent.click(screen.getByRole('button', {name: 'Open widget preview'}));
    expect(screen.getByRole('region', {name: 'Assistant preview chat'})).not.toBeNull();
    expect(within(screen.getByRole('region', {name: 'Assistant preview chat'})).getByText('Hello! What would you like to know?')).not.toBeNull();
    expect(backend.saveWidget).not.toHaveBeenCalled(); expect(backend.chat).not.toHaveBeenCalled();
  });
  it('clarifies documents and rotates preview conversation credentials on new chat', async () => {
    vi.mocked(backend.chat).mockResolvedValueOnce({status: 'clarification_required', question: 'Choose a PDF', original_question: 'Explain policy', top_k: 5,
      documents: [{document_id: 'document-fixture', filename: 'HR.pdf'}]});
    render(<WebsiteWidgetPanel/>); await screen.findByText(/3 \/ 500 questions today/);
    fireEvent.click(screen.getByRole('button', {name: 'Open widget preview'}));
    fireEvent.change(screen.getByLabelText('Preview question'), {target: {value: 'Explain policy'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send preview question'}));
    fireEvent.click(await screen.findByRole('button', {name: 'HR.pdf'}));
    await screen.findByText('Preview answer from assigned documents.');
    const first = vi.mocked(backend.chat).mock.calls[0], clarified = vi.mocked(backend.chat).mock.calls[1];
    expect(clarified[0].document_ids).toEqual(['document-fixture']); expect(clarified[0].question).toBe('Explain policy');
    expect(clarified[1]).toBe(first[1]);
    fireEvent.click(screen.getByRole('button', {name: 'New preview chat'}));
    fireEvent.change(screen.getByLabelText('Preview question'), {target: {value: 'A new question'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send preview question'}));
    await screen.findByText('Preview answer from assigned documents.');
    const fresh = vi.mocked(backend.chat).mock.calls[2];
    expect(fresh[0].conversation_id).not.toBe(first[0].conversation_id); expect(fresh[1]).not.toBe(first[1]);
  });
  it('keeps save errors visible without generating an unsaved embed', async () => {
    widget = null; vi.mocked(backend.saveWidget).mockRejectedValue(new Error('Add at least one allowed website.'));
    render(<WebsiteWidgetPanel/>); await screen.findByText('Save your widget to generate its embed code.');
    fireEvent.click(screen.getByRole('button', {name: 'Save widget'}));
    expect((await screen.findByRole('alert')).textContent).toContain('Add at least one allowed website.');
    expect(screen.queryByLabelText('Widget embed code')).toBeNull();
  });
  it('escapes titles and never emits credentials or a workspace endpoint', () => {
    const malicious = {...fixture(), title: '" onload="alert(1)'};
    expect(embedCode(malicious, 'script', 'https://shop.example.com')).toContain('&quot; onload=&quot;alert(1)');
    expect(embedCode(malicious, 'iframe', 'https://shop.example.com')).not.toContain('title="" onload=');
    expect(embedCode(malicious, 'script', '')).not.toContain('/v1/chat');
  });
});
