# ADDENDUM — 2026-03-21 — Branch cleanup + snapshots (audit trail)

## Contexto
Durante a estabilização do fluxo público (invites) e do E2E canônico, foram criadas branches temporárias de investigação/hotfix.
Após o sistema estabilizar e o E2E canônico passar (FULL SMOKE OK), optamos por **não mergear** algumas branches remanescentes
e, em vez disso, **preservar o diff** em arquivos `.patch` sob `docs/branch_snapshots/` como trilha de auditoria.

Este addendum registra esse fechamento para evitar retrabalho futuro e manter rastreabilidade.

---

## Estado atual (produção)
- **Branch principal:** `main`
- **Health upstream:** `http://127.0.0.1:18081/health` → `200 OK`
- **Health via domínio:** `https://profiledna.dnaagencia.com/health` → `200 OK`
- **E2E canônico:** `tests/e2e/test_e2e_full_smoke.sh` → ✅ `E2E FULL SMOKE OK`

> Observação: o E2E recebeu melhorias para reduzir falhas transitórias (ex.: waits de health) e evitar `unbound variable` com `set -u`.

---

## Decisão
1. **Manter o sistema como está** (sem introduzir mudanças adicionais em produção).
2. **Encerrar branches não-mergeadas remanescentes**, preservando o conteúdo em snapshots `.patch`.
3. **Guardar os snapshots dentro do repositório** em `docs/branch_snapshots/` para auditoria e eventual reaproveitamento controlado.

---

## Snapshots gerados
Arquivos mantidos em:
- `docs/branch_snapshots/`

Conteúdo:
- `hotfix_t-identificacao-action-url.patch`
  - Ajustes relacionados ao form/action de identificação e suporte canônico de rota /t no HTML.
  - **Decisão:** não mergeado (produção já está funcional e E2E verde).

- `hotfix_invite-id-optional-repo.patch`
  - Tornava `invite_id` opcional em `create_participant_and_attempt_from_invite`.
  - **Decisão:** não mergeado (preferimos manter `invite_id` obrigatório para reforçar integridade do fluxo).

- `feat_invites-model.patch`
  - Migrações e model Invite antigas (histórico pré-stabilização).
  - **Decisão:** não mergeado (main já contém implementação correta do domínio de invites e migrations atualizadas).

---

## Branches removidas (encerradas)
Remotas removidas após snapshot:
- `origin/hotfix/t-identificacao-action-url`
- `origin/hotfix/invite-id-optional-repo`
- `origin/feat/invites-model`

Locais removidas após snapshot:
- `hotfix/t-identificacao-action-url`
- `hotfix/invite-id-optional-repo`
- `feat/invites-model`

---

## Por que isso não gera risco
- As branches acima **não estão em produção**.
- O comportamento final foi validado por:
  - Health checks upstream e via Nginx
  - E2E canônico FULL (incluindo aliases /t, PDF, cache, DB checks e idempotência)

---

## Próximos passos
- Commitar este addendum + a pasta `docs/branch_snapshots/` no `main` (documentação/auditoria).
