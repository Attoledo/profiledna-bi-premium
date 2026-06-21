from __future__ import annotations

from dataclasses import dataclass

from backend.services.token import generate_token, token_hash


@dataclass(frozen=True)
class InviteToken:
    token: str
    token_hash: str


def generate_invite_token() -> InviteToken:
    # Reusa o gerador/hasher oficial do projeto
    t = generate_token()
    return InviteToken(token=t, token_hash=token_hash(t))
