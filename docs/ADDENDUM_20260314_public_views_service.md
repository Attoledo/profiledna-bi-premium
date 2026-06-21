# Addendum — 2026-03-14 — Public Views Service (review/report/confirm/pdf)

Este addendum registra uma refatoração **interna** alinhada ao SSOT v2.0: separar HTTP (routers) de regras de negócio (services) e de persistência (repositories).

## O que mudou

Foi criado o arquivo:

- `backend/services/public_views.py`

## Por que existe

Objetivo: centralizar regras das telas/artefatos do **fluxo público** em um service, para que:

- `backend/routers/public.py` fique **fino** e sem SQL (apenas HTTP e templates/redirects).
- A construção de contexto das telas fique em `backend/services/`.
- As queries/persistência permaneçam em `backend/repositories/`.

## Escopo

Rotas afetadas (v2 runtime):
- `GET /p/{token}/review`
- `GET /p/{token}/report`
- `GET /p/{token}/confirm`
- `GET /p/{token}/report/pdf`

## Contrato

Funções principais:
- `build_review_context(session, token) -> ReviewContext`
- `build_report_context(session, token) -> ReportContext`
- `ensure_report_pdf(session, token) -> (attempt_id_str, pdf_path)`

Exceção:
- `PublicFlowNotFound` para casos de token inválido, ausência de computed_result ou snapshot.
