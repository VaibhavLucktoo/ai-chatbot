"""Keep inference batches bounded independently of ingestion's storage batches."""

from unittest.mock import Mock

from app.providers.fastembed_provider import FastEmbedProvider


def test_configured_inference_batch_preserves_all_normalized_vectors(tmp_path):
    provider = FastEmbedProvider(cache_dir=tmp_path, batch_size=4, threads=1)
    model = Mock()
    model.passage_embed.return_value = iter([[2.0] + [0.0] * 383 for _ in range(32)])
    provider._model = model
    try:
        result = provider._embed(tuple(f'Passage {index}' for index in range(32)), False)
        assert model.passage_embed.call_args.kwargs['batch_size'] == 4
        assert len(result) == 32
        assert all(vector == [1.0] + [0.0] * 383 for vector in result)
    finally:
        provider.close()
