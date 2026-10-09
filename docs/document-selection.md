# Document selection in the chat client

POST `/v1/chat` accepts the existing question, top_k, and optional document_ids.
When document_ids is omitted and an English question refers to an unspecified
document (for example, "Summarize this document" or "Explain it"), the backend
checks ready documents before embedding or calling the LLM.

- No ready documents: return clarification_required with an upload prompt and no choices.
- One ready document: automatically restrict retrieval to that document.
- Multiple ready documents: return clarification_required with filename choices.
- Specific questions without document references: continue searching all ready documents.
- Explicit document_ids: continue the existing scoped retrieval flow.

This phrase check is a heuristic, not conversation memory or a general ambiguity detector.
Summary questions still use passage retrieval; this feature does not implement full-document summarization.

Example clarification response:

```json
{
  "status": "clarification_required",
  "question": "Which document do you mean? Select a filename.",
  "original_question": "Summarize this document",
  "top_k": 5,
  "documents": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "policy.pdf"
    }
  ]
}
```

Client integration:

1. If response.status is clarification_required, display response.question.
2. Render a button for each document, using filename as visible text and document_id as its value.
   Treat filenames as text, never HTML. Duplicate names remain separate choices; the client
   can label them with an occurrence number to distinguish their buttons.
3. On click, resend original_question and top_k with document_ids set to [selected document_id].
4. Otherwise display the existing answer and sources. With no choices, offer PDF upload.

Keep the pending question in the client. The backend does not save a clarification session.
No dedicated chat frontend exists in this repository; clients must implement these buttons.
