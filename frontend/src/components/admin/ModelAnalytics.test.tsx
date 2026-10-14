import React from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {ModelAnalyticsPanel} from './ModelAnalytics';
import {backend} from '../../services/backend';
import type {ModelAnalytics} from '../../types/analytics';

vi.mock('../../services/backend', () => ({backend: {analytics: vi.fn()}, describeError: (error: Error) => error.message}));
const fetchAnalytics = vi.mocked(backend.analytics);
function fixture(): ModelAnalytics {
  const calls = {attempts: 2, provider_requests: 2, succeeded: 1, failed: 1, cancelled: 0, rate_limited: 1,
    usage_available_calls: 1, total_reported_calls: 1, priced_calls: 0, input_tokens: 100, output_tokens: 10,
    total_tokens: 110, estimated_cost_usd: null, usage_complete: false, cost_complete: false,
    average_ms: 100, p95_ms: 150, average_queue_ms: 5, average_provider_ms: 95};
  return {
    window: {since: '2026-10-12T00:00:00Z', until: '2026-10-12T01:00:00Z', hours: 24, model: null},
    requests: {total: 2, successful: 1, unsuccessful: 1, cancelled: 0, retrieval_requests: 1, average_results: 5,
      average_sources: 1, success_rate: 50, average_ms: 120, median_ms: 120, p95_ms: 180, average_graph_ms: 110},
    outcomes: {answered: 1, provider_rate_limit: 1}, intents: {document_question: 2}, calls,
    models: [{...calls, model: 'test-model', provider: 'provider.example'}], call_stages: [{...calls, stage: 'answer'}],
    workflow_stages_ms: {retrieve: 20}, timeline: [{at: '2026-10-12T00:00:00Z', requests: 2, unsuccessful: 1, average_ms: 120}],
    requests_last_minute: 2, available_models: ['test-model'],
    recent: {items: [{id: 'request-1', instance_id: 'instance', started_at: '2026-10-12T00:00:00Z', endpoint: '/v1/chat',
      workflow_version: 'conversational-rag-v1', prompt_version: 'abc', http_status: 200, outcome: 'answered', intent: 'document_question',
      error_type: null, duration_ms: 100, graph_ms: 90, retrieval_performed: true, result_count: 5, source_count: 1,
      stage_timings_ms: {retrieve: 20}, calls: [{id: 'call', stage: 'answer', model: 'test-model', provider: 'provider.example',
        status: 'success', error_type: null, provider_requested: true, http_status: 200, duration_ms: 100, queue_ms: 5,
        provider_ms: 95, input_tokens: 100, output_tokens: 10, total_tokens: 110, estimated_cost_usd: null}]}], total: 2, offset: 0, limit: 25},
    runtime: {scope: 'this_process', instance_id: 'instance', started_at: '2026-10-12T00:00:00Z', active_chats: 1,
      active_model_calls: 1, waiting_model_calls: 0, pending_metric_writes: 0, dropped_events: 0, write_failures: 0,
      persisted_events: 2, last_write_at: null, last_error: null, writer_running: true},
    pricing: {currency: 'USD', configured_models: [], basis: 'Configured rates'},
    quality: {status: 'not_evaluated', accuracy: null, citation_support: null, completeness: null, reason: 'Accuracy requires labeled evaluations.'},
  };
}
beforeEach(() => {fetchAnalytics.mockReset(); fetchAnalytics.mockResolvedValue(fixture());});

describe('Model analytics', () => {
  it('shows real values with partial usage and unavailable cost, without inventing accuracy', async () => {
    render(<ModelAnalyticsPanel/>);
    await screen.findByText('50%');
    expect(screen.getByText('Not evaluated')).toBeDefined();
    expect(screen.getByText('Estimated model cost').parentElement?.textContent).toContain('Unavailable');
    expect(screen.getByText('Partial usage')).toBeDefined();
    fireEvent.click(screen.getByRole('button', {name: 'Inspect request request-1'}));
    await screen.findByText(/Retrieved: 5 candidates/);
    expect(screen.getByText(/Input: 100/).textContent).toContain('Estimated cost: Unavailable');
  });
  it('filters by period and model through backend parameters', async () => {
    render(<ModelAnalyticsPanel/>);
    await screen.findByText('50%');
    fireEvent.change(screen.getByLabelText('Analytics model'), {target: {value: 'test-model'}});
    await waitFor(() => expect(fetchAnalytics).toHaveBeenLastCalledWith(24, 'test-model', 0));
    fireEvent.change(screen.getByLabelText('Analytics period'), {target: {value: '168'}});
    await waitFor(() => expect(fetchAnalytics).toHaveBeenLastCalledWith(168, 'test-model', 0));
  });
  it('reports empty historical data without claiming perfect success', async () => {
    const data = fixture(); data.requests.total = 0; data.requests.success_rate = null; data.recent.items = [];
    fetchAnalytics.mockResolvedValue(data);
    render(<ModelAnalyticsPanel/>);
    await screen.findByText(/No recorded chat requests/);
    expect(screen.queryByText('100%')).toBeNull();
  });
  it('filters assistant and provider and displays separate configuration comparisons', async () => {
    const data = fixture();
    data.available_assistants = [{id: 'assistant-id', name: 'HR assistant'}];
    data.available_providers = ['api.groq.com'];
    data.assistants = [{assistant_id: 'assistant-id', assistant_name: 'HR assistant', assistant_revision: 2,
      connection_id: 'connection-id', connection_revision: 3, configured_provider: 'groq', configured_model: 'test-model',
      requests: 2, successful: 1, success_rate: 50, average_ms: 120, median_ms: 100, p95_ms: 180,
      provider_requests: 2, failed_calls: 1, input_tokens: 100, output_tokens: 10,
      estimated_cost_usd: null, cost_complete: false, usage_complete: false}];
    fetchAnalytics.mockResolvedValue(data);
    render(<ModelAnalyticsPanel/>);
    await screen.findByText('Configuration 2 · Connection revision 3');
    fireEvent.change(screen.getByLabelText('Analytics assistant'), {target: {value: 'assistant-id'}});
    await waitFor(() => expect(fetchAnalytics).toHaveBeenLastCalledWith(24, undefined, 0, {assistant: 'assistant-id', provider: undefined}));
    await screen.findByText('Configuration 2 · Connection revision 3');
    fireEvent.change(screen.getByLabelText('Analytics provider'), {target: {value: 'api.groq.com'}});
    await waitFor(() => expect(fetchAnalytics).toHaveBeenLastCalledWith(24, undefined, 0, {assistant: 'assistant-id', provider: 'api.groq.com'}));
    fireEvent.change(screen.getByLabelText('Analytics assistant'), {target: {value: 'workspace'}});
    await waitFor(() => expect(fetchAnalytics).toHaveBeenLastCalledWith(24, undefined, 0, {assistant: 'workspace', provider: 'api.groq.com'}));
  });
  it('reports metrics collection loss and backend outages', async () => {
    const data = fixture(); data.runtime!.dropped_events = 3;
    fetchAnalytics.mockResolvedValueOnce(data).mockRejectedValueOnce(new Error('Storage unavailable'));
    render(<ModelAnalyticsPanel/>);
    await screen.findByText(/3 event\(s\) dropped/);
    fireEvent.click(screen.getByRole('button', {name: 'Refresh metrics'}));
    await screen.findByText(/Analytics unavailable: Storage unavailable/);
    expect(screen.queryByText('50%')).toBeNull();
  });
});
