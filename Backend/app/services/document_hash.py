from hashlib import sha256


def pdf_sha256(data: bytes) -> str:
    """Return a stable fingerprint of the exact PDF bytes."""
    if not data:
        raise ValueError("Cannot hash an empty PDF.")

    return sha256(data).hexdigest()