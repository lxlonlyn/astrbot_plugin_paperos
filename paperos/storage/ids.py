from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"  # Crockford-like, no confusing i/l/o/u.


def _base32(num: int) -> str:
    if num == 0:
        return "0"
    chars: list[str] = []
    while num:
        num, rem = divmod(num, 32)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    """Create an independent sortable-ish id without external dependencies.

    Do not use DOI/arXiv/core id/sha256 as primary keys: those are external
    identifiers or file fingerprints, not PaperOS object identities.
    """

    millis = int(time.time() * 1000)
    rand = secrets.token_bytes(10)
    rand_num = int.from_bytes(rand, "big")
    return f"{prefix}_{_base32(millis)}{_base32(rand_num).rjust(16, '0')}"
