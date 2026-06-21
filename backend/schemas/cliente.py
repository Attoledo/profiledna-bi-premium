from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Coerção booleana de campos "ativo" vindos de HTML forms
# ---------------------------------------------------------------------------

_TRUTHY_STRINGS = {"true", "1", "on", "yes", "sim", "y", "t"}
_FALSY_STRINGS = {"false", "0", "off", "no", "nao", "não", "n", "f", ""}


def _coerce_ativo(value: Any) -> Any:
    """
    Converte valores de campos `ativo` recebidos via Form(...) (strings de
    checkbox HTML, ex.: "on", "true", "1") em booleanos legítimos.

    Substitui o padrão `bool(ativo)` (bug: qualquer string não-vazia,
    incluindo "false"/"0", avalia como True).
    """
    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUTHY_STRINGS:
            return True
        if normalized in _FALSY_STRINGS:
            return False
        raise ValueError(f"valor booleano inválido para 'ativo': {value!r}")

    raise ValueError(f"tipo inválido para 'ativo': {type(value)!r}")


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class ClienteBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    razao_social: Optional[str] = Field(default=None, max_length=255)
    cnpj: Optional[str] = Field(default=None, max_length=32)
    endereco: Optional[str] = Field(default=None, max_length=500)
    setor_mercado: Optional[str] = Field(default=None, max_length=255)
    responsavel: Optional[str] = Field(default=None, max_length=255)
    setor_responsavel: Optional[str] = Field(default=None, max_length=255)
    email_responsavel: Optional[str] = Field(default=None, max_length=255)


class ClienteCreate(ClienteBase):
    ativo: bool = True

    @field_validator("ativo", mode="before")
    @classmethod
    def _validate_ativo(cls, v: Any) -> Any:
        return _coerce_ativo(v)


class ClienteUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    razao_social: Optional[str] = Field(default=None, max_length=255)
    cnpj: Optional[str] = Field(default=None, max_length=32)
    endereco: Optional[str] = Field(default=None, max_length=500)
    setor_mercado: Optional[str] = Field(default=None, max_length=255)
    responsavel: Optional[str] = Field(default=None, max_length=255)
    setor_responsavel: Optional[str] = Field(default=None, max_length=255)
    email_responsavel: Optional[str] = Field(default=None, max_length=255)
    ativo: Optional[bool] = None

    @field_validator("ativo", mode="before")
    @classmethod
    def _validate_ativo(cls, v: Any) -> Any:
        return _coerce_ativo(v)


class ClienteResponse(ClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ativo: bool
    criado_em: datetime


# ---------------------------------------------------------------------------
# SetorEmpresa
# ---------------------------------------------------------------------------

class SetorCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)


class SetorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    nome: str


# ---------------------------------------------------------------------------
# RodadaAplicacao
# ---------------------------------------------------------------------------

class RodadaCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    data_inicio: date
    data_encerramento: Optional[date] = None


class RodadaUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    data_inicio: Optional[date] = None
    data_encerramento: Optional[date] = None


class RodadaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    nome: str
    data_inicio: date
    data_encerramento: Optional[date] = None
    criado_por: UUID
