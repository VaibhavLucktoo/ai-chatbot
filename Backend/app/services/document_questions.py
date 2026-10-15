"""Conservative hints for questions about a document's identity."""

import re


def is_document_identity_question(question: str) -> bool:
    """Recognize identity requests without treating ownership clauses as identity.

    These hints choose evidence, never determine an owner or manufacture an
    answer. In particular, ownership of work product remains a clause search.
    """
    identity = r"(?:owner|owns|author|publisher|issuer|issued|published|authored|prepared|belongs)"
    document = r"(?:policy|document|pdf|file|agreement|manual|handbook|report)"
    return bool(metadata_fields_for_question(question)) or bool(re.search(
        rf"\b{identity}\b.{{0,60}}\b{document}\b"
        rf"|\b{document}\b.{{0,40}}\b(?:owner|author|publisher|issuer)\b"
        r"|\b(?:name|identity)\b.{0,35}\bdisclosing party\b"
        r"|\bdisclosing party\b.{0,35}\b(?:name|identity)\b"
        r"|\b(?:company|organization|organisation)\b.{0,35}\b(?:name|website|email|e-mail)\b"
        r"|\b(?:header|footer|branding|letterhead)\b",
        question, re.IGNORECASE,
    ))


def metadata_fields_for_question(question: str) -> tuple[str, ...]:
    """Choose metadata fields, leaving ordinary rule/ownership-clause questions alone."""
    text = question.casefold()
    if re.search(r"\bdisclosing party\b", text) and re.search(r"\b(?:name|identity|who)\b", text):
        return ("disclosing_party",)
    if re.search(r"\breceiving party\b", text) and re.search(r"\b(?:name|identity|who)\b", text):
        return ("receiving_party",)
    fields = []
    if re.search(r"\b(?:author|authored|wrote|written by|prepared by)\b", text):
        fields.append("author")
    if re.search(r"\b(?:version|revision)\b", text):
        fields.append("version")
    if re.search(r"\b(?:effective date|when.{0,30}(?:issued|effective|published))\b", text):
        fields.append("effective_date")
    if re.search(r"\b(?:title|document name|policy name)\b", text):
        fields.extend(("title", "section_title"))
    if re.search(r"\b(?:website|web site|url)\b", text):
        fields.append("website")
    if re.search(r"\b(?:email|e-mail)\b", text):
        fields.append("email")
    if fields:
        return tuple(dict.fromkeys(fields))
    if re.search(r"\b(?:header|footer|branding|letterhead)\b", text):
        return ("organization", "publisher", "website", "email", "title", "section_title")
    if re.search(r"\b(?:owner|owns|belongs|issuer|issued|publisher|published)\b", text) and re.search(
        r"\b(?:policy|document|pdf|file|agreement|manual|handbook|report)\b", text,
    ):
        return ("document_owner", "organization", "publisher", "website", "email")
    if re.search(r"\b(?:company|organization|organisation)\b.{0,35}\b(?:name|identity)\b", text):
        return ("organization", "publisher", "website", "email")
    return ()
