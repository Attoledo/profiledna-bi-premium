# Addendum — 2026-03-12 — Public Flow Service (internal refactor)

Este addendum registra uma refatoração **interna** alinhada ao SSOT v2.0: separar HTTP (routers) de regras de negócio (services) e de persistência (repositories).

## O que mudou

Foi criado o arquivo:

- `backend/services/public_flow.py`

## Por que existe

Objetivo: centralizar regras do **fluxo público** (ex.: `POST /start`) em um **service** para que:

- `backend/routers/public.py` fique **fino**, responsável apenas por HTTP (Form/Request/Redirect).
- A orquestração do fluxo (geração de token + criação do attempt) fique em `backend/services/`.
- As queries/persistência permaneçam em `backend/repositories/` (ex.: `repo_attempt.create_participant_and_attempt_default_seed`).

## Escopo

No MVP atual, o fluxo público usa bootstrap `DEFAULT_*` (Cliente/Rodada/Setor) enquanto o painel admin ainda não existe.

Isso **não altera** SSOT de conteúdo, scoring, nem relatório — apenas organiza responsabilidades internas.

## Contrato

Função:
- `start_public_attempt(session, nome, sobrenome, email, tipo_aplicacao, testdef_version="v1") -> StartResult`

Retorna:
- `token`: token cru (apenas para URL/cookie do browser)
- `attempt`: Attempt ORM criado (apenas `token_hash` é persistido)
