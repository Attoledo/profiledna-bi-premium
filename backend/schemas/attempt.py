from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AttemptStatus(str, Enum):
    """
    SSOT: estados canônicos do ciclo de vida de uma tentativa/convite.
    """

    PENDING = "PENDING"
    OPENED = "OPENED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AnswerChoice(str, Enum):
    A = "A"
    B = "B"


# ---------------------------------------------------------------------------
# Tradução de vocabulário legado -> enum canônico AttemptStatus
# ---------------------------------------------------------------------------

# Mapeamento tolerante de valores legados (em uso em public.py/admin.py via
# strings livres / `_normalize_text_key()`) para os estados canônicos do
# enum AttemptStatus. Chaves devem estar em UPPERCASE.
_LEGACY_STATUS_ALIASES: dict[str, AttemptStatus] = {
    "SUBMITTED": AttemptStatus.COMPLETED,
    "IN_PROGRESS": AttemptStatus.OPENED,
}


def _normalize_attempt_status(value: Any) -> Any:
    """
    Normaliza valores de status recebidos de formulários/ORM legados:
    - já é AttemptStatus -> retorna como está
    - string -> trim + uppercase; aplica alias legado se aplicável;
      caso contrário, repassa a string em uppercase para o Enum validar
      (fail-fast em valores realmente desconhecidos).
    - demais tipos / None -> repassa sem alteração.
    """
    if value is None or isinstance(value, AttemptStatus):
        return value

    if isinstance(value, str):
        key = value.strip().upper()
        if key in _LEGACY_STATUS_ALIASES:
            return _LEGACY_STATUS_ALIASES[key]
        return key

    return value


# ---------------------------------------------------------------------------
# Participant
# ---------------------------------------------------------------------------

class ParticipantBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    sobrenome: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    empresa_nome: Optional[str] = Field(default=None, max_length=255)
    tipo_aplicacao: str = Field(..., min_length=1, max_length=32)


class ParticipantCreate(ParticipantBase):
    pass


class ParticipantResponse(ParticipantBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------

class AnswerCreate(BaseModel):
    question_number: int = Field(..., ge=1, le=100)
    choice: AnswerChoice


class AnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    question_number: int = Field(..., ge=1, le=100)
    choice: AnswerChoice
    letter_scored: str = Field(..., min_length=1, max_length=2)
    answered_at: datetime


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------

class AttemptCreate(BaseModel):
    participant_id: UUID
    cliente_id: UUID
    rodada_id: UUID
    setor_id: Optional[UUID] = None
    cargo: Optional[str] = Field(default=None, max_length=255)
    testdef_version: str = Field(default="v1", max_length=32)
    invite_id: Optional[UUID] = None


class AttemptUpdate(BaseModel):
    status: Optional[AttemptStatus] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    data_conclusao: Optional[datetime] = None
    cargo: Optional[str] = Field(default=None, max_length=255)

    @field_validator("status", mode="before")
    @classmethod
    def _translate_status(cls, v: Any) -> Any:
        return _normalize_attempt_status(v)


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    participant_id: UUID
    cliente_id: UUID
    rodada_id: UUID
    setor_id: Optional[UUID] = None
    cargo: Optional[str] = None
    status: AttemptStatus
    progress: int = Field(..., ge=0, le=100)
    data_inicio: datetime
    data_conclusao: Optional[datetime] = None
    testdef_version: str
    invite_id: Optional[UUID] = None

    @field_validator("status", mode="before")
    @classmethod
    def _translate_status(cls, v: Any) -> Any:
        return _normalize_attempt_status(v)


class AttemptDetailResponse(AttemptResponse):
    participant: Optional[ParticipantResponse] = None
    answers: List[AnswerResponse] = Field(default_factory=list)
