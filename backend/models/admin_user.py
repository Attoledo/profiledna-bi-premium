from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

# Perfis de acesso: "admin" é superusuário (sempre full-access, nunca limitado
# pela matriz de permissões); "analista" é restrito por módulo via o campo
# 'permissions' e bloqueado por completo da rota /admin/usuarios.
ROLE_ADMIN = "admin"
ROLE_ANALISTA = "analista"

# Níveis de permissão por módulo, do mais fraco ao mais forte.
PERMISSION_LEVEL_NONE = "none"
PERMISSION_LEVEL_READ = "read"
PERMISSION_LEVEL_TOTAL = "total"

PERMISSION_LEVEL_RANK = {
    PERMISSION_LEVEL_NONE: 0,
    PERMISSION_LEVEL_READ: 1,
    PERMISSION_LEVEL_TOTAL: 2,
}

# Módulos cobertos pela matriz dinâmica de permissões de analista. A checagem
# em 'has_module_permission' é por chave de dicionário (string genérica), de
# modo que adicionar um módulo aqui não exige nenhuma mudança de lógica —
# basta que o backend/UI passem a referenciar a nova chave.
PERMISSION_MODULES = ("dashboard", "clientes", "bi", "bi_comparativo", "dana")


class AdminUser(Base):
    """
    SSOT 7.1 (estendido):
    admin_users
        id, username, password_hash, nome, ativo,
        role, requires_reset, permissions
    """
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Perfil de acesso ("admin" | "analista"). Default "admin" preserva o
    # comportamento de full-access para todas as contas já existentes.
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=ROLE_ADMIN)

    # Quando True, a próxima requisição autenticada é redirecionada para
    # /admin/trocar-senha antes de liberar qualquer outra rota do painel.
    requires_reset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Mapa de permissões por módulo, ex.: {"dashboard": "read", "clientes":
    # "total", "bi": "read", "bi_comparativo": "none", "dana": "total"}. Só
    # é consultado quando role == "analista" — contas "admin" nunca são
    # limitadas por este campo.
    permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


def has_module_permission(admin: Optional["AdminUser"], module: str, min_level: str = PERMISSION_LEVEL_READ) -> bool:
    """
    True se 'admin' pode acessar 'module' com pelo menos 'min_level'.
    Contas "admin" (ou qualquer role que não seja "analista") sempre
    retornam True — a matriz de permissões só restringe analistas.
    """
    if not admin:
        return False
    if getattr(admin, "role", ROLE_ADMIN) != ROLE_ANALISTA:
        return True

    perms = getattr(admin, "permissions", None) or {}
    level = perms.get(module, PERMISSION_LEVEL_NONE)
    return PERMISSION_LEVEL_RANK.get(level, 0) >= PERMISSION_LEVEL_RANK.get(min_level, 1)
