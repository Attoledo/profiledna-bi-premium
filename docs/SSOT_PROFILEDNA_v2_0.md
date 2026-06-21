# SSOT — ProfileDNA v2.0

## Governança do SSOT (Fonte Única da Verdade)

- Este arquivo (**SSOT_PROFILEDNA_v2_0.md**) é a **única fonte de verdade** do produto ProfileDNA (requisitos, fluxos, dados SSOT v1, regras de cálculo, relatório e critérios de aceite).
- Qualquer mudança **de regra, dado, estrutura de relatório, contratos JSON, segurança ou fluxos** deve gerar **nova versão** (ex.: `SSOT_PROFILEDNA_v2_1.md`) ou um **Addendum versionado**, nunca alteração “silenciosa”.
- O pacote **SSOT v1 (JSONs oficiais)** é **imutável por versão**: mudanças em perguntas/gabarito/dimensões/bibliotecas/blocos exigem **novo versionamento** do dataset (ex.: `data/ssot/profiledna/v2/`).
- Critério de fechamento: um **Audit PASS/FAIL** (SSOT ↔ Documento Programa ↔ JSONs ↔ Excel-lógica) deve permanecer **100% PASS** para qualquer release.

> **Este documento substitui integralmente:**
>
> - `CONTEXTO_PROJETO.md`
> - `SSOT_PROFILEDNA_v1_2.md`
>
> **Leia este documento na íntegra antes de gerar qualquer código.**
> Nenhum dado, regra ou estrutura pode ser alterada sem aprovação explícita do cliente.
> Versão gerada após análise completa do PDF original, Excel de gabarito e todas as sessões de alinhamento arquitetural.

---

**Produto:** ProfileDNA
**Cliente:** DNA Agência
**Modelo de negócio:** Single-operator, multi-client
**Versão do documento:** 2.0 FINAL
**Data:** Fevereiro 2026

---

## ÍNDICE

1. [Visão Geral do Produto](#1-visão-geral-do-produto)
2. [Contexto de Negócio — Como a DNA Agência Opera](#2-contexto-de-negócio)
3. [Stack Tecnológica — Imutável](#3-stack-tecnológica)
4. [Princípios Arquiteturais](#4-princípios-arquiteturais)
5. [Estrutura Completa de Pastas](#5-estrutura-completa-de-pastas)
6. [Explicação Detalhada — Pasta por Pasta, Arquivo por Arquivo](#6-explicação-detalhada)
7. [Banco de Dados — Modelo Completo](#7-banco-de-dados)
8. [SSOT de Conteúdo — Dados Congelados do Teste](#8-ssot-de-conteúdo)
9. [Motor de Cálculo — Regras Determinísticas](#9-motor-de-cálculo)
10. [Estrutura do Relatório — Especificação Completa](#10-estrutura-do-relatório)
11. [Fluxo do Participante — UX Obrigatória](#11-fluxo-do-participante)
12. [Painel Administrativo — DNA Agência](#12-painel-administrativo)
13. [Dashboard BI — Análise por Cliente](#13-dashboard-bi)
14. [Segurança — Requisitos Mínimos](#14-segurança)
15. [Variáveis de Ambiente](#15-variáveis-de-ambiente)
16. [Infraestrutura e Deploy](#16-infraestrutura-e-deploy)
17. [Testes — Estratégia e Cobertura](#17-testes)
18. [Ordem de Desenvolvimento — Etapas Sequenciais](#18-ordem-de-desenvolvimento)
19. [Regras Absolutas para Geração de Código](#19-regras-absolutas)
20. [O que o Sistema Faz — Visão Prática Completa](#20-o-que-o-sistema-faz)

---

## 1. VISÃO GERAL DO PRODUTO

**ProfileDNA** é um webapp de teste de perfil comportamental desenvolvido exclusivamente para a **DNA Agência** aplicar em seus clientes (empresas e pessoas físicas).

### O que é o teste

O teste é composto por **100 perguntas de múltipla escolha** (A ou B), que medem **20 dimensões comportamentais** agrupadas em 3 áreas: Gerencial, Interpessoal e Pessoal. Ao final, o sistema calcula automaticamente o perfil do participante e gera um **relatório profissional completo** com pontos fortes, oportunidades de desenvolvimento, PDI e recomendações para gestor/RH.

### Para que serve

A DNA Agência usa o ProfileDNA como ferramenta de consultoria organizacional. Ela aplica o teste em colaboradores de empresas clientes para:

- Mapear o perfil comportamental de equipes inteiras
- Identificar forças coletivas e gaps por setor
- Apoiar processos de seleção, desenvolvimento e gestão de pessoas
- Comparar perfis ao longo do tempo (reavaliações periódicas)
- Gerar relatórios individuais e análises de grupo para o RH da empresa cliente

### O que o sistema entrega, do início ao fim

```
DNA Agência cria um Cliente (empresa) no sistema
    ↓
DNA cria uma Rodada de Aplicação para aquele cliente
    ↓
DNA gera convites (links únicos) para cada colaborador
    ↓
DNA envia os links por WhatsApp ou e-mail
    ↓
Colaborador abre o link, lê a apresentação, clica em "Começar"
    ↓
Colaborador preenche seus dados de identificação
    ↓
Colaborador responde 100 perguntas (A ou B), uma por vez
    ↓
Sistema salva automaticamente cada resposta (autosave)
    ↓
Colaborador revisa as respostas antes de enviar
    ↓
Colaborador confirma o envio — teste travado, sem edição
    ↓
Sistema calcula automaticamente as 20 dimensões
    ↓
Sistema gera o relatório completo e o snapshot imutável
    ↓
Colaborador vê o resultado na tela e pode baixar o PDF
    ↓
DNA Agência acessa o painel e vê todos os resultados
    ↓
DNA analisa por cliente, por setor, por rodada (BI)
    ↓
DNA exporta relatórios individuais e dados em CSV/XLSX
```

---

## 2. CONTEXTO DE NEGÓCIO

### 2.1 Modelo Operacional

O ProfileDNA opera no modelo **single-operator, multi-client**:

- **Operador único:** A DNA Agência. Ela é a única que acessa o painel administrativo, cria clientes, gera convites e analisa resultados.
- **Múltiplos clientes:** Cada empresa contratante da DNA é um "Cliente" no sistema — um agrupador de participantes, não um usuário do sistema.
- **Participantes:** Os colaboradores das empresas clientes. Eles acessam apenas o próprio teste via link único. Não têm login, não têm conta, não acessam painel.

### 2.2 O que isso significa tecnicamente

```
NÃO é SaaS multi-tenant:
  Empresa A faz login → vê seus dados
  Empresa B faz login → vê seus dados

É single-operator multi-client:
  DNA faz login → vê todos os dados
  DNA filtra por cliente → vê dados do cliente X
  Cliente NUNCA acessa o sistema
```

Consequência direta: **não existe middleware de tenant, não existe permissão por empresa, não existe login de cliente.** O `cliente_id` nas tabelas é uma tag de agrupamento para o BI — não um controle de autenticação entre usuários distintos.

### 2.2.1 Scope de contexto — cliente_id como boundary interno

Embora o sistema não seja SaaS multi-tenant, o `cliente_id` **funciona como boundary de autorização dentro do painel da DNA** para duas finalidades específicas:

1. **BI:** Todas as queries de análise usam o `cliente_id` da tela atual como filtro obrigatório. O operador vê os dados de um cliente por vez — nunca dados misturados de dois clientes na mesma visualização.
2. **Agente IA:** Todas as ferramentas (`tools.py`) usam o `cliente_id` extraído da **sessão HTTP**, não o `cliente_id` que o modelo de linguagem possa sugerir como argumento. Isso garante que o agente nunca acessa dados de um cliente diferente do contexto atual da tela.

**Em linguagem de código:** `cliente_id` não é campo de controle de acesso entre usuários (não há usuários distintos por empresa), mas é um **scope de contexto obrigatório** em todas as queries de BI e em todas as tool calls do agente.

### 2.3 Hierarquia de entidades

```
DNA Agência (operador único)
└── Cliente (empresa contratante)
    └── RodadaAplicacao (diagnóstico Jan/2026, Jun/2026...)
        └── SetorEmpresa (Comercial, Operações, TI...)
            └── Attempt (sessão de teste de um colaborador)
                ├── Participant (dados pessoais)
                ├── Answer × 100 (respostas A/B)
                ├── ComputedResult (snapshot do cálculo)
                └── ReportSnapshot (HTML renderizado + PDF)
```

### 2.4 Por que RodadaAplicacao existe

A DNA aplica o teste em diferentes momentos para o mesmo cliente. Um diagnóstico em Janeiro/2026 e uma reavaliação em Junho/2026 são rodadas distintas. O BI precisa comparar "como evoluiu o setor Comercial entre a Rodada 1 e a Rodada 2". Sem a entidade `RodadaAplicacao`, essa comparação temporal é impossível.

### 2.5 Por que SetorEmpresa existe

A DNA aplica o teste em múltiplas camadas da organização. O BI precisa responder "qual o perfil médio do setor de TI vs o setor Comercial desta empresa". O `setor_id` no Attempt é o que permite esse recorte.

---

## 3. STACK TECNOLÓGICA

> ⚠️ **REGRA ABSOLUTA:** Esta stack é imutável. Nunca sugerir tecnologias fora desta lista.

| Camada | Tecnologia | Versão Mínima | Motivo da escolha |
|--------|-----------|---------------|-------------------|
| Backend | **FastAPI** (Python) | 0.110+ | Async nativo, Pydantic integrado, baixa latência |
| Banco de dados | **PostgreSQL** | 15+ | Robusto, queries complexas de BI, JSONB para snapshots |
| ORM | **SQLAlchemy** | 2.0+ async | Suporte async, queries tipadas, migrations via Alembic |
| Migrations | **Alembic** | latest | Versionamento de schema, reversível |
| Validação | **Pydantic** | 2.0+ | Validação unificada de entrada, saída e dados SSOT |
| Templates HTML | **Jinja2** | 3.1+ | Renderização server-side, templates modulares |
| Geração de PDF | **WeasyPrint** | 60+ | HTML → PDF A4 fiel, CSS suportado |
| Autenticação | **JWT (python-jose)** + **bcrypt** | — | JWT para admin, token hasheado para participante |
| Containerização | **Docker + Docker Compose** | — | Ambientes reprodutíveis |
| Proxy reverso | **Nginx** + Let's Encrypt | — | HTTPS, rate limiting, headers de segurança |
| Hospedagem | **Hetzner VPS** (Ubuntu 22.04) | — | Custo-benefício, controle total |

**Não usar:** Flask, Django, Streamlit, React, Vue, Redis (v1), Celery (v1), ou qualquer framework não listado acima.

### 3.1 Estratégia de geração de PDF (decisão consciente)

A ausência de Celery/Redis na v1 implica PDF **gerado de forma síncrona e lazy** — sob demanda no download, não no submit. Decisão deliberada:

- **No submit:** Gera `ComputedResult` e `ReportSnapshot` (HTML). O campo `pdf_path` fica `null`.
- **No primeiro download:** Verifica se `pdf_path` existe. Se não, gera o PDF via WeasyPrint, salva em disco, atualiza `pdf_path`, retorna o arquivo. Downloads subsequentes servem o cache.
- **Timeout Nginx:** Configurar `proxy_read_timeout 120s` no `site.conf` para acomodar WeasyPrint (tipicamente 3–8s por relatório).
- **Proteção contra concorrência:** Lock por `attempt_id` (`asyncio.Lock` em dicionário global) para evitar geração dupla simultânea.
- **Quando escalar:** Se PDF virar gargalo (>50 downloads simultâneos), introduzir Celery + Redis na v2 sem alterar a interface do endpoint.

---

## 4. PRINCÍPIOS ARQUITETURAIS

Estes princípios guiam cada decisão de código. Leia antes de qualquer implementação.

### 4.1 Separação de responsabilidades

Cada arquivo tem uma única responsabilidade. O scoring engine não conhece o banco. O banco não conhece o HTTP. Os templates não conhecem o cálculo.

### 4.2 Dados separados do código

Perguntas, gabarito e bibliotecas de texto ficam em arquivos JSON versionados (`data/ssot/`), não em dicionários Python. O código lê os dados — não contém os dados.

### 4.3 Imutabilidade após envio

Após SUBMIT, nenhuma linha de resposta pode ser alterada. Isso é protegido no app (serviço de negócio) e opcional no banco (trigger). Qualquer tentativa retorna HTTP 409.

### 4.4 Snapshots para auditabilidade

Ao submeter, o sistema grava um JSON completo do resultado calculado (`ComputedResult`) e um HTML renderizado do relatório (`ReportSnapshot`). Se os textos da biblioteca mudarem no futuro, os relatórios históricos permanecem inalterados.

### 4.5 Golden Master para o scoring

O motor de cálculo tem fixtures de entrada e saída esperadas. Qualquer refatoração que altere o resultado matemático quebra os testes automaticamente.

### 4.6 Token hasheado, nunca em texto puro

O token do participante é armazenado no banco como `SHA-256(token)`. O token original existe apenas no link enviado e no cookie do browser.

### 4.7 Async do banco ao endpoint

FastAPI com SQLAlchemy async. Cada `await db.execute()` libera o event loop. 200 usuários simultâneos são gerenciados sem bloqueio.

---

## 5. ESTRUTURA COMPLETA DE PASTAS

```
profiledna/                                  ← raiz do projeto
│
├── README.md                                ← instruções de setup e execução
├── requirements.txt                         ← dependências Python com versões fixadas
├── pyproject.toml                           ← configuração opcional (Poetry/uv)
├── .env.example                             ← template de variáveis (sem segredos)
├── .gitignore                               ← exclui .env, postgres_data, __pycache__
│
├── compose/                                 ← orquestração Docker
│   ├── docker-compose.dev.yml               ← stack de desenvolvimento local
│   └── docker-compose.prod.yml              ← stack de produção Hetzner
│
├── docker/                                  ← configuração dos containers
│   ├── Dockerfile                           ← build da imagem do app FastAPI
│   ├── entrypoint.sh                        ← migrações + healthcheck + start uvicorn
│   └── nginx/
│       ├── nginx.conf                       ← configuração global do Nginx
│       └── site.conf                        ← virtual host, TLS, rate limiting, headers
│
├── docs/                                    ← documentação do projeto
│   ├── SSOT_PROFILEDNA_v2_0.md             ← ESTE DOCUMENTO (fonte de verdade)
│   ├── SECURITY.md                          ← checklist de hardening de segurança
│   ├── RUNBOOK_PROD.md                      ← operação: deploy, rollback, backup, logs
│   ├── DATA_DICTIONARY.md                   ← dicionário de dados (tabelas e campos)
│   └── API_CONTRACTS.md                     ← endpoints com payloads de entrada e saída
│
├── data/                                    ← dados congelados do teste (SSOT de conteúdo)
│   └── ssot/
│       └── profiledna/
│           └── v1/                          ← versão 1 do teste — NUNCA ALTERAR
│               ├── questions_100.json       ← as 100 perguntas com opções A e B
│               ├── gabarito_100.json        ← letra resultante por pergunta (se A / se B)
│               ├── dimensions_20.json       ← 20 dimensões com área e competência RH
│               ├── library1_basic.json      ← Biblioteca 1: textos por faixa (padrão)
│               ├── library2_premium.json    ← Biblioteca 2: textos premium (corporativo)
│               ├── dimension_competency_map.json  ← mapa dimensão → competência RH PDI
│               ├── premium_manager_blocks.json    ← 3 blocos Gestor/RH (bullets completos)
│               └── README.txt               ← instruções de uso e regras de versionamento
│
├── scripts/                                 ← utilitários de linha de comando
│   ├── seed_ssot.py                         ← carrega v1 dos JSONs no banco (TestDefinition)
│   └── generate_report_pdf.py               ← gera PDF de um relatório (utilitário admin)
│
├── infra/                                   ← configuração de infraestrutura
│   ├── hetzner/
│   │   ├── cloud_init.md                    ← anotações de bootstrap do servidor
│   │   └── firewall_rules.md                ← regras de firewall Hetzner
│   └── backup/
│       ├── backup_pg.sh                     ← script de backup do PostgreSQL
│       └── restore_pg.sh                    ← script de restauração do PostgreSQL
│
├── backend/                                 ← código-fonte da aplicação
│   ├── main.py                              ← entrypoint FastAPI: app + routers + lifespan
│   ├── config.py                            ← Pydantic BaseSettings (lê do .env)
│   ├── database.py                          ← SQLAlchemy async engine + SessionLocal
│   │
│   ├── ssot/                                ← carregamento dos dados do teste em memória
│   │   ├── loader.py                        ← lê os JSONs de data/ssot/v1/ no startup
│   │   └── validator.py                     ← valida integridade dos dados carregados
│   │
│   ├── models/                              ← SQLAlchemy ORM — definição das tabelas
│   │   ├── cliente.py                       ← Cliente + SetorEmpresa + RodadaAplicacao
│   │   ├── attempt.py                       ← Attempt + Participant + Answer
│   │   ├── result.py                        ← ComputedResult + ReportSnapshot
│   │   └── admin_user.py                    ← AdminUser (usuários internos da DNA)
│   │
│   ├── schemas/                             ← Pydantic — validação de entrada e saída HTTP
│   │   ├── cliente.py                       ← schemas de Cliente, Setor, Rodada
│   │   ├── attempt.py                       ← schemas de Attempt, Participant, Answer
│   │   └── report.py                        ← schemas de ComputedResult, ReportSnapshot
│   │
│   ├── repositories/                        ← queries ao banco — separadas das rotas
│   │   ├── cliente.py                       ← CRUD de clientes, setores, rodadas
│   │   ├── attempt.py                       ← queries de attempt, answers, autosave
│   │   └── result.py                        ← queries de resultados e snapshots
│   │
│   ├── services/                            ← regras de negócio — sem I/O direto
│   │   ├── autosave.py                      ← upsert idempotente de resposta individual
│   │   ├── submit.py                        ← transação atômica: valida + calcula + trava
│   │   ├── token.py                         ← geração e hash SHA-256 de token
│   │   └── invite.py                        ← criação de convite vinculado a rodada/setor
│   │
│   ├── scoring/                             ← motor de cálculo puro — sem I/O, sem HTTP
│   │   ├── engine.py                        ← compute_result(): lógica central do cálculo
│   │   ├── rules.py                         ← faixas, top/bottom com desempate determinístico
│   │   ├── types.py                         ← tipos Python: AnswerMap, ScoreMap, ResultSnapshot
│   │   └── fixtures/                        ← dados para testes Golden Master
│   │       ├── golden_inputs.json           ← vetores de 100 respostas A/B conhecidos
│   │       └── golden_outputs.json          ← resultado esperado para cada vetor de entrada
│   │
│   ├── reports/                             ← geração de relatório HTML e PDF
│   │   ├── renderer.py                      ← monta o relatório a partir do snapshot
│   │   └── pdf.py                           ← converte HTML → PDF via WeasyPrint
│   │
│   ├── bi/                                  ← dashboard de análise para a DNA
│   │   ├── selectors.py                     ← queries agregadas (médias, percentis, top/bottom)
│   │   ├── services.py                      ← transforma dados brutos em payloads de gráfico
│   │   └── charts.py                        ← helpers de configuração Chart.js
│   │
│   ├── ai_analyst/                          ← agente IA (implementar após 1ª rodada de dados)
│   │   ├── agent.py                         ← wrapper OpenAI Responses API + tool calling
│   │   ├── tools.py                         ← funções autorizadas (checagem de cliente_id)
│   │   ├── prompts.py                       ← system prompts versionados + regras anti-alucinação
│   │   ├── models.py                        ← AIInteractionLog (auditoria obrigatória)
│   │   ├── services.py                      ← sanitização de entrada + montagem do context pack
│   │   ├── router.py                        ← POST /admin/ai/chat + GET /admin/ai/history
│   │   └── templates/
│   │       ├── chat_panel.html              ← UI do chat embedded no painel admin
│   │       └── chat_messages.html           ← fragmentos HTMX das mensagens
│   │
│   ├── routers/                             ← endpoints HTTP — entrada e saída da aplicação
│   │   ├── public.py                        ← fluxo do participante (sem autenticação)
│   │   └── admin.py                         ← painel da DNA (JWT obrigatório)
│   │
│   ├── templates/                           ← Jinja2 — HTML server-side
│   │   ├── base.html                        ← layout base: head, meta viewport, footer
│   │   ├── public/                          ← telas do participante
│   │   │   ├── landing.html                 ← página de apresentação do teste
│   │   │   ├── identification.html          ← formulário de identificação
│   │   │   ├── question.html                ← tela da pergunta A/B
│   │   │   ├── review.html                  ← revisão antes do envio
│   │   │   └── finished.html                ← confirmação de envio + link resultado
│   │   ├── partials/                        ← fragmentos reutilizáveis (HTMX-ready)
│   │   │   ├── question_card.html           ← card da pergunta (texto + botões A/B)
│   │   │   ├── progress_bar.html            ← barra "Pergunta X de 100"
│   │   │   └── save_status.html             ← indicador "Salvando..." / "Salvo ✓"
│   │   ├── admin/                           ← telas do painel da DNA
│   │   │   ├── login.html                   ← autenticação JWT
│   │   │   ├── dashboard.html               ← lista de clientes e participantes
│   │   │   ├── cliente_detail.html          ← visão de um cliente: rodadas + participantes
│   │   │   ├── rodada_detail.html           ← participantes de uma rodada + status
│   │   │   ├── participant_detail.html      ← resultado completo de um participante
│   │   │   └── bi/
│   │   │       ├── overview.html            ← visão geral de todos os clientes
│   │   │       ├── cliente_bi.html          ← BI de um cliente: médias, gráficos, top/bottom
│   │   │       └── comparativo.html         ← dois clientes ou duas rodadas lado a lado
│   │   └── reports/                         ← templates do relatório (modulares)
│   │       ├── report_full.html             ← relatório completo (inclui todas as seções)
│   │       └── sections/                    ← seções individuais do relatório
│   │           ├── header.html              ← identificação: nome, email, empresa, data, ID
│   │           ├── executive_summary.html   ← síntese executiva (parágrafo Top 3)
│   │           ├── area_panel.html          ← painel por área: Gerencial/Interpessoal/Pessoal
│   │           ├── strengths.html           ← pontos fortes: Top 5 com blocos completos
│   │           ├── development.html         ← oportunidades: Bottom 3 com plano de ação
│   │           ├── pdi.html                 ← PDI: 3 competências potencializar + 3 desenvolver
│   │           ├── premium_manager.html     ← blocos Gestor/RH (só se tipo=empresa)
│   │           ├── detailed_dimensions.html ← tabela das 20 dimensões com score e texto
│   │           └── technical_note.html      ← nota técnica de rodapé
│   │
│   └── static/                              ← assets estáticos
│       ├── css/
│       │   └── app.css                      ← CSS responsivo mobile-first (sem framework)
│       ├── js/
│       │   └── app.js                       ← AJAX autosave + navegação + progresso
│       └── img/
│           └── logo.png                     ← logo da DNA Agência (cabeçalho e PDF)
│
└── tests/                                   ← testes automatizados
    ├── conftest.py                          ← fixtures compartilhadas (db, client, dados)
    ├── unit/
    │   └── scoring/
    │       └── test_engine_golden_master.py  ← testa scoring com vetores fixos
    └── integration/
        ├── test_public_flow.py              ← fluxo completo do participante
        ├── test_autosave.py                 ← idempotência do autosave
        ├── test_submit_lock.py              ← bloqueio após submit
        └── test_admin_flow.py              ← autenticação e operações do admin
```

---

---

## 6. EXPLICAÇÃO DETALHADA — PASTA POR PASTA, ARQUIVO POR ARQUIVO

Esta seção explica o **propósito exato** de cada pasta e cada arquivo. Leia antes de criar qualquer código.

---

### 6.1 Raiz do Projeto

#### `README.md`

Manual de bordo do projeto. Contém: como clonar o repositório, como configurar o `.env`, como rodar em desenvolvimento, como executar os testes, como fazer deploy em produção. É o primeiro arquivo que qualquer desenvolvedor novo lê.

#### `requirements.txt`

Lista todas as dependências Python com versões exatas fixadas (ex: `fastapi==0.110.0`). Versões fixadas garantem que o ambiente de desenvolvimento e o container de produção sejam idênticos. Nunca usar `fastapi>=0.110.0` — isso permite atualizações acidentais que podem quebrar o sistema.

#### `.env.example`

Template público das variáveis de ambiente. Contém todos os nomes das variáveis necessárias, mas com valores fictícios. É commitado no git. O arquivo `.env` real (com senhas e chaves) **nunca** vai para o git.

#### `.gitignore`

Garante que arquivos sensíveis ou desnecessários não sejam enviados ao repositório. Deve incluir obrigatoriamente: `.env`, `postgres_data/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`.

---

### 6.2 `compose/` — Orquestração Docker

#### `docker-compose.dev.yml`

Ambiente de desenvolvimento local. Sobe PostgreSQL (porta 5432 exposta para o host) e a aplicação FastAPI com **hot reload** ativado. Nginx não é necessário em desenvolvimento — o FastAPI serve direto na porta 8000.

#### `docker-compose.prod.yml`

Ambiente de produção no Hetzner. Sobe PostgreSQL (porta **não** exposta), a aplicação FastAPI com Gunicorn/Uvicorn (sem hot reload), e Nginx como proxy reverso com TLS. Os containers se comunicam por rede interna Docker.

---

### 6.3 `docker/` — Configuração dos Containers

#### `Dockerfile`

Define como construir a imagem Docker da aplicação: parte de imagem Python base, instala dependências, copia código, define usuário não-root, define `entrypoint.sh` como comando de entrada.

#### `entrypoint.sh`

Script executado quando o container inicia:

1. Aguarda PostgreSQL estar pronto (retry com backoff)
2. Executa migrations do Alembic (`alembic upgrade head`)
3. Inicia o servidor Uvicorn (dev) ou Gunicorn+Uvicorn (prod)

#### `nginx/nginx.conf`

Configuração global do Nginx: workers, buffer, logs. Raramente modificado.

#### `nginx/site.conf`

Virtual host do ProfileDNA: redirect HTTP→HTTPS, certificado SSL, proxy_pass para o container FastAPI, rate limiting por IP, headers de segurança (X-Frame-Options, HSTS, CSP), timeout para geração de PDF.

---

### 6.4 `docs/` — Documentação

#### `SSOT_PROFILEDNA_v2_0.md`

Este documento. A fonte única de verdade. Leia integralmente antes de qualquer código.

#### `SECURITY.md`

Checklist de hardening: headers, cookies, PostgreSQL, rotação de chaves JWT, procedimentos em caso de incidente.

#### `RUNBOOK_PROD.md`

Manual de operação: como fazer deploy, rollback, restaurar backup, verificar logs, renovar certificado SSL.

#### `DATA_DICTIONARY.md`

Cada tabela do banco com campos, tipos, restrições e descrição de negócio.

#### `API_CONTRACTS.md`

Cada endpoint HTTP com método, URL, autenticação, payload de entrada, payload de saída, exemplos de erro.

#### `QUESTIONS_PDF_CORRIGIDO_CANONICAL.json`

Arquivo canônico (extraído uma única vez do **PDF corrigido**) contendo as 100 perguntas e opções A/B. Usado apenas para validação (`scripts/validate_questions_against_pdf.py`) e para garantir aderência total ao PDF.

---

### 6.5 `data/ssot/profiledna/v1/` — Dados Congelados do Teste

> **REGRA ABSOLUTA:** Nenhum arquivo dentro de `v1/` pode ser modificado após entrar em produção. Qualquer alteração exige criar `v2/`.

#### `questions_100.json`

As 100 perguntas com opções A e B. Conteúdo definitivo do PDF corrigido pelo cliente.

```json
[{"number": 1, "option_a": "Gosto de fazer meu trabalho bem-feito.", "option_b": "Gosto de estar em movimento."}, ...]
```

#### `gabarito_100.json`

Para cada pergunta: qual letra é pontuada se A, qual letra se B. Extraído do Excel original.

```json
[{"number": 1, "letter_if_A": "L", "letter_if_B": "T"}, ...]
```

#### `dimensions_20.json`

As 20 dimensões com área e competência RH equivalente.

```json
[{"letter": "A", "name": "Atitude Analítica", "area": "GERENCIAL", "competency_rh": "Pensamento analítico..."}, ...]
```

**Contrato de enum (`area`):** o campo `area` deve ser **exatamente** um destes valores:

- `GERENCIAL`
- `INTER PESSOAL`
- `PESSOAL`

Qualquer variação (ex.: `INTERPESSOAL`, `INTERPESSOAL`) deve ser rejeitada pelo `validator.py` (fail-fast).

#### `interpretations_per_score.json` (LEGADO — somente referência)

Textos por **score exato (0–10)** por dimensão, provenientes da aba “RESULTADOS” do Excel.

- **Uso permitido:** apenas para **regressão** (comparar com versões antigas) e para auditoria.
- **Uso no relatório v2:** **NÃO** (a Biblioteca 1 do v2 deve vir do PDF).

#### `library1_basic.json`

Biblioteca 1 — textos por faixa para aplicações do tipo "pessoal". Para cada dimensão: texto Baixo/Médio/Alto, Risco do Excesso, Ações e Métrica.

**Fonte obrigatória:** `DOCUMENTO PROGRAMA TESTE PERFIL DNA` (seção “IMPORTANTE — Biblioteca 1”). **Não** usar os textos legados do Excel.

#### `library2_premium.json`

Biblioteca 2 — textos por faixa para aplicações do tipo "empresa". Linguagem mais refinada, orientada a gestão corporativa.
**Schema (por dimensão/letra):**

- `title`: título da dimensão
- `fields.low` / `fields.mid` / `fields.high`: texto por faixa (0–3 / 4–6 / 7–10)
- `fields.excess`: risco do excesso
- `fields.suggestions`: ações recomendadas
- `fields.indicator`: métrica/indicador (pode incluir a área ao final, mas a área oficial vem de `dimensions_20.json`)

**Nota de compatibilidade (dataset):** caso o arquivo tenha sido entregue como `premium_library_0_3_4_6_7_10.json`, ele deve ser **renomeado** para `library2_premium.json` (conteúdo idêntico) antes do `seed_ssot.py`.

#### `dimension_competency_map.json` (OPCIONAL)

Mapa dimensão → competência RH. **Opcional**, pois `dimensions_20.json` já contém `competency_rh`.

- Se presente, deve ser **derivado 1:1** de `dimensions_20.json` e validado (mesmas letras, mesmos textos).
- Se ausente, o relatório PDI usa diretamente `dimensions_20.json.competency_rh`.

#### `premium_manager_blocks.json`

Os 3 blocos completos de recomendações para Gestor/RH com todos os bullets. O sistema seleciona 3 de cada bloco com base no perfil Top/Bottom.

---

### 6.6 `scripts/` — Utilitários de Linha de Comando

#### `seed_ssot.py`

**O que faz:** Lê os JSONs de `data/ssot/profiledna/v1/` e popula as tabelas de definição do teste no banco. Executado uma única vez após o deploy inicial.

```bash
python scripts/seed_ssot.py --version v1
```

#### `validate_ssot_schemas.py`

Valida **schema e enums** de todos os JSONs em `data/ssot/profiledna/v1/` (ex.: `area` ∈ {GERENCIAL, INTER PESSOAL, PESSOAL}; chaves obrigatórias; ranges; ausência de letras fora de A..T). Deve rodar em CI.

#### `validate_questions_against_pdf.py`

Valida que `questions_100.json` reflete **exatamente** a versão corrigida das perguntas do PDF.

> Observação: parsing direto do PDF pode ser instável (quebras de linha/encoding). Portanto, este script compara `questions_100.json` contra um arquivo canônico extraído **uma única vez** do PDF corrigido e versionado no repositório:
>
> - `docs/QUESTIONS_PDF_CORRIGIDO_CANONICAL.json`

Se houver qualquer divergência (texto, ordem, pontuação), o script falha.

> Exportação de tentativas (CSV/XLSX): não há script standalone — a exportação é servida diretamente
> pelo painel admin via `GET /admin/exportar/csv` e `GET /admin/exportar/xlsx`
> (helpers `_build_export_rows` / `_build_csv_bytes` / `_build_xlsx_bytes` em `backend/routers/admin.py`),
> com filtros por `cliente_id`, `rodada_id` e `setor_id`.

#### `generate_report_pdf.py`

Gera PDF de um relatório específico por attempt ID. Útil para regenerar PDFs perdidos.

---

### 6.7 `backend/main.py` — Entrypoint FastAPI

Define: instância do app, lifespan (startup: carrega SSOT, valida dados; shutdown: fecha conexões), registro de todos os routers, middlewares globais, endpoint `/health`. Não contém lógica de negócio.

---

### 6.8 `backend/config.py` — Configurações

Classe `Settings` com Pydantic `BaseSettings`. Lê variáveis do `.env` automaticamente com validação de tipos. Se `DATABASE_URL` não estiver definida, o app não inicia.

---

### 6.9 `backend/database.py` — Conexão PostgreSQL

Configura o SQLAlchemy async engine com pool de conexões (`pool_size=10, max_overflow=20`), `SessionLocal` e a dependência `get_db` para injeção nos endpoints.

---

### 6.10 `backend/ssot/loader.py` + `validator.py`

**`loader.py`:** No startup, lê todos os JSONs e os carrega em um objeto `ssot_data` global em memória. Elimina queries ao banco para dados estáticos que nunca mudam em runtime.

**`validator.py`:** Verifica integridade após carga: exatamente 100 questões, 20 dimensões sem repetição, letras válidas no gabarito, soma = 200 entradas. Se falhar, o app não inicia.

**Política de qualidade (typos / grafia):** o validador deve **REJEITAR (fail-fast)** qualquer divergência de grafia/enum/contrato. **Não** normalizar silenciosamente.

- Se houver typos em datasets legados, corrigir o JSON **antes** do deploy (e, após produção, somente via nova versão `vN+1`).

---

### 6.11 `backend/models/` — Tabelas do Banco

#### `cliente.py` — 3 tabelas

- **`clientes`**: empresa contratante (id, nome, setor_mercado, responsavel, email_responsavel, ativo)
- **`setores_empresa`**: divisões internas (id, cliente_id, nome)
- **`rodadas_aplicacao`**: cada aplicação do teste (id, cliente_id, nome, data_inicio, data_encerramento, criado_por)

#### `attempt.py` — 3 tabelas

- **`participants`**: dados pessoais do colaborador (id, nome, sobrenome, email, tipo_aplicacao)
- **`attempts`**: sessão do teste (id, token_hash UNIQUE, participant_id, cliente_id, rodada_id, setor_id, cargo, status, progress, data_inicio, data_conclusao, testdef_version)
- **`answers`**: respostas individuais (id, attempt_id, question_number, choice, letter_scored, answered_at) com UNIQUE(attempt_id, question_number)

#### `result.py` — 2 tabelas imutáveis

- **`computed_results`**: snapshot JSON do cálculo (id, attempt_id UNIQUE, scores JSONB, bands JSONB, top3 JSONB, top5 JSONB, bottom3 JSONB, interpretations JSONB, premium_data JSONB)
- **`report_snapshots`**: HTML renderizado (id, attempt_id UNIQUE, html_content TEXT, pdf_path, generated_at)

#### `admin_user.py`

- **`admin_users`**: usuários internos da DNA (id, username UNIQUE, password_hash, nome, ativo)

---

### 6.12 `backend/schemas/` — Validação Pydantic

Contratos de dados: o que cada endpoint aceita e retorna.

- **`cliente.py`**: ClienteCreate, ClienteResponse, SetorCreate, RodadaCreate, RodadaResponse
- **`attempt.py`**: ParticipantCreate, AnswerCreate `{question_number: int, choice: Literal["A","B"]}`, AttemptResponse, AttemptStatus enum
- **`report.py`**: ComputedResultResponse, ReportSnapshotResponse

---

### 6.13 `backend/repositories/` — Queries ao Banco

Isolam as queries SQLAlchemy do restante da aplicação. Nenhum router ou service escreve queries diretamente.

- **`cliente.py`**: get_all_clientes, get_cliente_by_id, create_cliente, get_setores_by_cliente, get_rodadas_by_cliente
- **`attempt.py`**: get_attempt_by_token_hash, get_answers_by_attempt, upsert_answer (idempotente), update_attempt_status, lock_attempt
- **`result.py`**: create_computed_result, get_computed_result, create_report_snapshot

---

### 6.14 `backend/services/` — Regras de Negócio

#### `token.py`

- `generate_token()` → UUID4 (122 bits de entropia)
- `hash_token(token)` → SHA-256 (o que vai para o banco)
- `verify_token(token, stored_hash)` → comparação segura com `hmac.compare_digest`

#### `invite.py`

Cria convite vinculado a rodada/setor: gera token, armazena hash, cria Attempt com status CREATED, retorna URL completa.

#### `autosave.py`

Upsert idempotente: verifica que attempt não está SUBMITTED (→ 409 se estiver), obtém letra do gabarito, faz upsert da Answer, atualiza progress.

#### `submit.py`

Transação atômica: valida 100/100 respostas → calcula via engine → salva ComputedResult → renderiza e salva ReportSnapshot → trava attempt (SUBMITTED). Se qualquer passo falhar, a transação inteira é revertida.

---

### 6.15 `backend/scoring/` — Motor de Cálculo Puro

**Sem dependências de banco, HTTP ou templates. Python puro.**

#### `types.py`

Estruturas de dados: `AnswerMap`, `LetterMap`, `CountMap`, `ScoreMap`, `BandMap`, `ResultSnapshot` (dataclass com todos os campos do resultado).

#### `rules.py`

- `get_band(score)` → "baixo" | "medio" | "alto"
- `get_top_n(scores, n)` → lista de N letras com maiores scores, desempate por letra ASC
- `get_bottom_n(scores, n)` → lista de N letras com menores scores, desempate por letra ASC

> **Desempate determinístico é obrigatório.** Dois participantes com mesmo score devem sempre ter mesmo resultado.

#### `engine.py`

`compute_result(answers, ssot, tipo)`:

1. A/B → letras via gabarito
2. Conta frequência por letra
3. `assert sum(counts.values()) == 100`
4. Score = Count
5. Classifica por faixa
6. Seleciona Top3/Top5/Bottom3 (com desempate)
7. Busca textos (library1 se pessoal, library2 se empresa)
8. Monta premium se corporativo
9. Retorna `ResultSnapshot`

#### `fixtures/golden_inputs.json` + `golden_outputs.json`

Vetores de teste calculados manualmente no Excel original. São a prova matemática de equivalência com o instrumento original.

---

### 6.16 `backend/reports/` — Geração de Relatório

#### `renderer.py`

Recebe `ResultSnapshot` + dados SSOT, renderiza HTML via Jinja2. Determinístico: mesmos inputs → mesmo HTML. Implementa o template exato da Síntese Executiva conforme PDF original. Implementa a regra de seleção dos bullets dos blocos Gestor/RH.

#### `pdf.py`

`generate_pdf(html_content, output_path)` → WeasyPrint. PDF A4 com logo, quebras de página entre seções, nota técnica no rodapé.

---

### 6.17 `backend/bi/` — Dashboard de Análise

#### `selectors.py`

Queries otimizadas sobre `computed_results` e `attempt_dimension_scores` (dados pré-calculados). Nunca recalcula scoring. Funções: get_average_by_dimension, get_band_distribution, get_top_dimensions_frequency, compare_rodadas.

#### `services.py`

Transforma dados brutos em payloads de gráfico: build_radar_data, build_heatmap_data, build_distribution_data.

#### `charts.py`

Configurações JSON para Chart.js: cores DNA Agência, labels das dimensões, escalas 0–10.

---

### 6.18 `backend/routers/` — Endpoints HTTP

#### `public.py` — Rotas do participante (sem autenticação)

```
GET  /t/{token}                → landing
GET  /t/{token}/identificacao  → formulário
POST /t/{token}/identificacao  → salva identificação
GET  /t/{token}/q/{n}          → pergunta n
POST /t/{token}/q/{n}/answer   → autosave
GET  /t/{token}/revisao        → revisão
POST /t/{token}/submit         → submete (transação atômica)
GET  /t/{token}/resultado      → relatório na tela
GET  /t/{token}/resultado/pdf  → download PDF
```

#### `admin.py` — Rotas do painel DNA (JWT obrigatório)

```
POST /admin/login
GET  /admin/dashboard
POST /admin/clientes
GET  /admin/clientes/{id}
POST /admin/clientes/{id}/setores
POST /admin/clientes/{id}/rodadas
POST /admin/rodadas/{id}/convites
GET  /admin/participants/{id}
GET  /admin/participants/{id}/pdf
GET  /admin/bi/overview
GET  /admin/bi/cliente/{id}
GET  /admin/bi/comparativo
GET  /admin/exportar/csv
GET  /admin/exportar/xlsx
```

---

### 6.19 `backend/templates/` — Jinja2 HTML

**`base.html`**: layout base com meta viewport mobile-first, link CSS, blocos Jinja2 (title, content, scripts).

**`public/landing.html`**: apresentação com logo, subtítulo, 4 orientações, tempo estimado, confidencialidade, botão "Começar".

**`public/identification.html`**: formulário Nome/Sobrenome/Email/Tipo/Empresa com validação client-side.

**`public/question.html`**: barra de progresso + texto da pergunta + botões A/B (mín 48px) + Voltar/Próxima + indicador autosave.

**`public/review.html`**: lista 100 perguntas com respostas + botão "Confirmar envio".

**`public/finished.html`**: confirmação + link para o resultado.

**`partials/question_card.html`**: fragmento HTMX do card da pergunta (atualizado sem reload).

**`partials/progress_bar.html`**: fragmento HTMX da barra de progresso.

**`partials/save_status.html`**: fragmento "Salvando..." / "Salvo ✓".

**`admin/login.html`**: usuário + senha, sem revelar se usuário existe em erros.

**`admin/dashboard.html`**: tabela de clientes com métricas, filtros, busca.

**`admin/cliente_detail.html`**: dados da empresa + rodadas + participantes + geração de convites.

**`admin/participant_detail.html`**: relatório completo + baixar PDF + exportar dados.

**`admin/bi/cliente_bi.html`**: radar chart + tabela de scores + distribuição + top/bottom + filtros.

**`reports/report_full.html`**: inclui via `{% include %}` cada seção modular.

**`reports/sections/`**: 9 seções independentes. Editar uma não afeta as outras.

---

### 6.20 `backend/static/`

**`css/app.css`**: CSS mobile-first sem framework. Variáveis de cor DNA, layout responsivo 320px→1440px, botões A/B com 48px mínimo, barra de progresso animada.

**`js/app.js`**: autosave via fetch POST, habilita "Próxima" após resposta, indicador visual, mostra campo "Empresa" condicionalmente, confirmação de submit.

**`img/logo.png`**: logo DNA Agência para cabeçalho e PDF.

---

### 6.21 `tests/`

**`conftest.py`**: fixtures compartilhadas (db em memória, test client, sample_answers, ssot_mock).

**`unit/scoring/test_engine_golden_master.py`**: O teste mais crítico. Compara resultado do engine com Golden Master calculado no Excel. Se falhar, scoring está errado.

**`integration/test_autosave.py`**: idempotência, resposta inválida → 422, pós-submit → 409.

**`integration/test_submit_lock.py`**: submit <100 → 400, submit 100 → 200, segundo submit → 409.

**`integration/test_public_flow.py`**: fluxo completo ponta a ponta.

**`integration/test_admin_flow.py`**: login inválido → 401, JWT expirado → 401, sem JWT → 401.

---

## 7. BANCO DE DADOS — MODELO COMPLETO

### 7.1 Diagrama de entidades

```
admin_users
    id, username, password_hash, nome, ativo

clientes
    id, nome, setor_mercado, responsavel, email_responsavel, ativo, criado_em

setores_empresa
    id, cliente_id (FK→clientes), nome

rodadas_aplicacao
    id, cliente_id (FK→clientes), nome, data_inicio, data_encerramento, criado_por (FK→admin_users)

invites
    id, token_hash (UNIQUE), cliente_id (FK→clientes), rodada_id (FK→rodadas)
    setor_id (FK→setores, nullable), cargo (nullable)
    status (PENDING | OPENED | COMPLETED | EXPIRED | CANCELLED)
    expires_at (TIMESTAMP, nullable)
    attempt_id (FK→attempts, nullable — preenchido apos abertura)
    criado_por (FK→admin_users), criado_em, atualizado_em

participants
    id, nome, sobrenome, email, tipo_aplicacao

attempts
    id, invite_id (FK→invites, UNIQUE), participant_id (FK→participants)
    cliente_id (FK→clientes), rodada_id (FK→rodadas), setor_id (FK→setores)
    cargo, status, progress, data_inicio, data_conclusao, testdef_version
    token_hash (UNIQUE) ← mantido para lookup direto por URL

answers
    id, attempt_id (FK→attempts), question_number, choice, letter_scored, answered_at
    UNIQUE (attempt_id, question_number)

computed_results
    id, attempt_id (FK→attempts, UNIQUE), testdef_version
    scores (JSONB), bands (JSONB), top3 (JSONB), top5 (JSONB), bottom3 (JSONB)
    interpretations (JSONB), premium_data (JSONB), generated_at

report_snapshots
    id, attempt_id (FK→attempts, UNIQUE), html_content, pdf_path, generated_at

attempt_dimension_scores  ← desnormalizado para BI rápido
    attempt_id, cliente_id, rodada_id, setor_id, letter, score, band
```

### 7.2 Índices obrigatórios

```sql
CREATE UNIQUE INDEX idx_attempts_token_hash ON attempts(token_hash);
CREATE INDEX idx_attempts_cliente_id ON attempts(cliente_id);
CREATE INDEX idx_attempts_rodada_id ON attempts(rodada_id);
CREATE INDEX idx_attempts_setor_id ON attempts(setor_id);
CREATE INDEX idx_answers_attempt_id ON answers(attempt_id);
CREATE INDEX idx_attempts_status ON attempts(status);
CREATE INDEX idx_dim_scores_cliente ON attempt_dimension_scores(cliente_id, letter);
```

### 7.3 Estados do Invite

```
PENDING     → convite criado, link ainda nao foi aberto
OPENED      → participante abriu o link (Attempt criado)
COMPLETED   → participante concluiu e submeteu o teste
EXPIRED     → link ultrapassou expires_at sem ser concluido
CANCELLED   → admin encerrou/revogou o convite manualmente
```

Transicoes validas:

```
PENDING  → OPENED     (participante abre o link)
PENDING  → EXPIRED    (cron job diario verifica expires_at)
PENDING  → CANCELLED  (admin cancela)
OPENED   → COMPLETED  (participante submete)
OPENED   → EXPIRED    (expires_at ultrapassado sem submit)
OPENED   → CANCELLED  (admin cancela)
```

### 7.4 Estados do Attempt

```
CREATED     → Attempt criado ao abrir o link, antes da identificacao
IN_PROGRESS → participante identificou-se, esta respondendo
SUBMITTED   → finalizado e travado (imutavel)
CANCELLED   → admin cancelou (espelha o Invite CANCELLED)
```

> **Relacao Invite x Attempt:** Um Invite gera exatamente um Attempt ao ser aberto. O `token_hash` existe em ambos para lookup direto pela URL. O Invite e a entidade de controle (criada pela DNA); o Attempt e a entidade de execucao (criada quando o participante abre o link). A rastreabilidade "enviei X convites, Y foram abertos, Z concluiram" e feita via contagem de status no Invite.

---

## 8. SSOT DE CONTEÚDO — DADOS CONGELADOS

### 8.1 As 20 Dimensões

| Letra | Nome | Área |
|-------|------|------|
| A | Atitude Analítica | GERENCIAL |
| B | Organização | GERENCIAL |
| C | Controle | GERENCIAL |
| D | Liderança | GERENCIAL |
| F | Decisão de Risco | GERENCIAL |
| J | Apego às Técnicas | GERENCIAL |
| L | Detalhismo | GERENCIAL |
| N | Autogestão Emocional | INTER PESSOAL |
| M | Assertividade | INTER PESSOAL |
| P | Empatia e Vínculo | INTER PESSOAL |
| S | Sociabilidade | INTER PESSOAL |
| E | Comunicação | INTER PESSOAL |
| R | Presença e Posicionamento | PESSOAL |
| I | Maturidade Organizacional | PESSOAL |
| H | Comprometimento e Disciplina | PESSOAL |
| G | Ritmo de Execução | PESSOAL |
| T | Energia e Movimento | PESSOAL |
| K | Persistência | PESSOAL |
| O | Adaptabilidade e Inovação | PESSOAL |
| Q | Orientação a Resultados | PESSOAL |

### 8.2 Regra de uso das bibliotecas

| Tipo de Aplicação | Biblioteca usada |
|-------------------|-----------------|
| `pessoal` | `library1_basic.json` |
| `empresa` | `library2_premium.json` |

**Faixas (bandas) e chaves internas:**

- Score `0..3` → **Baixo** → chave `low`
- Score `4..6` → **Médio** → chave `mid`
- Score `7..10` → **Alto** → chave `high`

> O relatório (UI/PDF/BI) exibe sempre **Baixo/Médio/Alto**. As chaves `low/mid/high` são apenas o contrato interno dos JSONs de biblioteca.

### 8.3 Regra de versionamento

- `v1` é imutável após produção. Qualquer alteração → criar `v2/`.
- O campo `testdef_version` em `attempts` e `computed_results` registra qual versão foi usada.
- Relatórios históricos de v1 nunca são afetados por v2.

---

## 9. MOTOR DE CÁLCULO — REGRAS DETERMINÍSTICAS

### 9.1 Passo a passo

**Regra de desempate (obrigatória, determinística):**

- Ordenação primária: `score` **descendente**
- Desempate: `letter` **crescente** (`A < B < ... < T`)

> A regra acima vale para Top 5, Top 3, Bottom 3, e para qualquer seleção “mais altas/mais baixas” por área.

1. **A/B → Letras**: gabarito converte cada resposta em uma letra A..T
2. **Contar**: frequência de cada letra nas 100 respostas
3. **Score = Count**: escala 0–10 por design do gabarito
4. **Faixas**: 0–3 Baixo, 4–6 Médio, 7–10 Alto

**Contrato de faixa → chave interna (obrigatório):**

- `score` 0–3 ⇒ Faixa **Baixo** ⇒ `band_key='low'`
- `score` 4–6 ⇒ Faixa **Médio** ⇒ `band_key='mid'`
- `score` 7–10 ⇒ Faixa **Alto**  ⇒ `band_key='high'`

> As bibliotecas (`library1_basic.json`, `library2_premium.json`) usam **somente** as chaves `low/mid/high`.

1. **Top/Bottom**: ordenação com desempate determinístico (letra ASC)
2. **Textos**: busca na biblioteca correta pela faixa
3. **Premium**: seleciona bullets Gestor/RH se corporativo

### 9.2 Validações obrigatórias no engine

```python
assert sum(counts.values()) == 100
assert all(0 <= s <= 10 for s in scores.values())
assert len(top3) == 3
assert len(bottom3) == 3
```

### 9.3 Validação prévia obrigatória no `ssot/validator.py`

Antes de aceitar o gabarito como válido no startup, o `validator.py` verifica a distribuição máxima real por letra. Isso garante que nenhuma dimensão possa ultrapassar score 10 em nenhuma combinação possível de respostas:

```python
def validate_gabarito_distribution(gabarito: list[dict]) -> None:
    max_occurrences: dict[str, int] = {}
    for entry in gabarito:
        for letter in [entry["letter_if_A"], entry["letter_if_B"]]:
            max_occurrences[letter] = max_occurrences.get(letter, 0) + 1

    for letter, count in max_occurrences.items():
        if count > 10:
            raise ValueError(
                f"Gabarito invalido: letra '{letter}' aparece {count} vezes "
                f"(maximo permitido: 10). Escala 0-10 seria violada."
            )

    expected = set("ABCDEFGHIJKLMNOPQRST")
    found = set(max_occurrences.keys())
    if found != expected:
        raise ValueError(f"Letras faltando no gabarito: {expected - found}")
```

> **Nota:** Se o gabarito original do Excel tiver alguma letra com mais de 10 ocorrencias, isso precisa ser resolvido com o cliente antes do deploy. O `validator.py` bloqueia o startup do app se esta condicao nao for satisfeita.

---

## 10. ESTRUTURA DO RELATÓRIO

### Seção 1 — Cabeçalho

Nome, Email, Empresa (ou "Aplicação Pessoal"), Data/hora, ID do teste.

### Seção 2 — Síntese Executiva

Parágrafo padrão (template do PDF) com Top 3 dimensões substituídas como variáveis.

**Preenchimento das variáveis (contrato, determinístico):**

- `[Dimensão_Alta_1]`, `[Dimensão_Alta_2]`, `[Dimensão_Alta_3]`: títulos das 3 dimensões com maior `score` (Top 3), aplicando a regra de desempate da Seção **9.1**. Fonte do título: `dimensions_20.json[letter].name`.
- `[impacto_positivo]`: texto literal de `library1_basic.json[Dimensão_Alta_1].fields.high`.
- `[ponto_de_atenção]`: texto literal de `library1_basic.json[Dimensão_Alta_1].fields.excess`.
- `[gatilho]`: selecionado a partir da **área** (`dimensions_20.json[Dimensão_Alta_1].area`) pelo mapa fixo abaixo:
  - `GERENCIAL` ⇒ "prazos curtos, metas agressivas e decisões rápidas"
  - `INTER PESSOAL` ⇒ "conflitos, divergências e pressão social"
  - `PESSOAL` ⇒ "cansaço, rotina e alta carga emocional"

> Observação: o parágrafo da Síntese Executiva **sempre** referencia a Dimensão_Alta_1 como base de `[impacto_positivo]`, `[ponto_de_atenção]` e `[gatilho]` para manter o texto estável e determinístico.

### Seção 3 — Painel por Áreas

Gerencial / Interpessoal / Pessoal: média da área, 2 dimensões mais altas, 1 mais baixa.

### Seção 4 — Pontos Fortes (Top 5)

Para cada dimensão: Score/10, Contribuição, Contexto ideal, Risco em excesso, Como potencializar.

### Seção 5 — Oportunidades (Bottom 3)

Para cada dimensão: Score/10, Impacto no trabalho, 2 comportamentos para evoluir, Ação 30 dias, Métrica.

### Seção 6 — PDI

3 competências para potencializar (Top 3) + 3 para desenvolver (Bottom 3). Cada uma com: Por que é relevante, Comportamentos-alvo, Rotina de prática, Indicador.

### Seção 7 — Gestor/RH (só se empresa)

3 blocos de 3 bullets: Engajar, Feedback, Ambiente Ideal. Seleção baseada no perfil.

### Seção 8 — 20 Dimensões

Tabela completa: dimensão, score, faixa, texto interpretativo.

### Seção 9 — Nota Técnica

Rodapé obrigatório sobre uso adequado do instrumento.

---

## 11. FLUXO DO PARTICIPANTE

```
/t/{token}               → Landing
/t/{token}/identificacao → Formulário
/t/{token}/q/1..100      → 100 Perguntas
/t/{token}/revisao       → Revisão
/t/{token}/submit        → Confirmação + Submit
/t/{token}/finalizado    → Confirmação de envio
/t/{token}/resultado     → Relatório completo
```

**Comportamentos obrigatórios:** autosave após cada resposta, retomada se fechar o browser, botão Voltar (desabilitado na Q1), botão Próxima (desabilitado até responder), submit irreversível com modal de confirmação.

---

## 12. PAINEL ADMINISTRATIVO

**Login:** `/admin/login` → JWT 8h
**Dashboard:** lista clientes com métricas
**Cliente:** rodadas + participantes + gerar convites
**Participante:** resultado completo + baixar PDF
**Exportação:** CSV e XLSX com filtros por cliente/rodada/setor

---

## 13. DASHBOARD BI

**Base de dados:** tabela `attempt_dimension_scores` pre-calculada — todas as queries de BI operam sobre ela, nunca recalculam o scoring.

### 13.1 Contrato minimo — Overview (todos os clientes)

| Elemento | Descricao | Filtros |
|----------|-----------|---------|
| Tabela de clientes | Nome, total participantes, concluidos, em andamento, % conclusao, data ultima rodada | Status, periodo |
| Media global por area | Media Gerencial / Interpessoal / Pessoal de todos os clientes | Periodo |

### 13.2 Contrato minimo — BI por Cliente

| Elemento | Tipo | Descricao |
|----------|------|-----------|
| Grafico Radar | Chart.js radar | Medias das 3 areas — escala 0-10 |
| Tabela de scores | Tabela HTML | 20 dimensoes x (media, mediana, % Alto, % Medio, % Baixo) |
| Top 5 coletivo | Lista | Dimensoes mais frequentes no Top5 individual — contagem e % |
| Bottom 3 coletivo | Lista | Dimensoes mais frequentes no Bottom3 individual — contagem e % |
| Distribuicao por faixa | Barra empilhada | Para cada dimensao: % Alto / Medio / Baixo |

**Filtros obrigatorios no BI por cliente:**

- Por rodada (todas ou uma especifica)
- Por setor (todos ou um especifico)
- Por cargo (todos ou um especifico)
- Por tipo de aplicacao (pessoal / empresa / todos)

### 13.3 Contrato minimo — Comparativo

| Elemento | Descricao |
|----------|-----------|
| Selecao | Dois clientes distintos OU duas rodadas do mesmo cliente |
| Tabela delta | 20 dimensoes x (media A, media B, diferenca, sinal alto/baixo/igual) |
| Radar duplo | Duas series sobrepostas no mesmo radar — escala 0-10 |

### 13.4 Estatisticas disponiveis por dimensao

Para cada dimensao em qualquer recorte (cliente/setor/rodada/cargo):

- **Media** (principal indicador)
- **Mediana** (resistente a outliers)
- **Distribuicao** (contagem e % por faixa: Alto / Medio / Baixo)
- **Frequencia no Top5** (quantos participantes tem esta dimensao no Top5)
- **Frequencia no Bottom3** (quantos participantes tem esta dimensao no Bottom3)

> Percentil e desvio padrao ficam para v2 quando houver volume suficiente para ser estatisticamente relevante.

---

## 14. SEGURANÇA

- Token participante: UUID4 armazenado como SHA-256 no banco
- Admin: bcrypt (custo 12) + JWT 8h com SECRET_KEY de 64 chars
- HTTPS obrigatório em produção
- Rate limiting: 10 req/s por IP no Nginx
- PostgreSQL: porta não exposta, apenas rede interna Docker
- Logs: sem PII, sem respostas A/B

### 14.1 Modelo de sessão admin — JWT em cookie HttpOnly (modelo único e fixo)

> **DECISÃO FIXADA:** O JWT do admin fica em **cookie HttpOnly** — nunca em `localStorage` nem via `Authorization: Bearer`. O painel usa Jinja2 (SSR) + HTMX, que não envia headers `Authorization` arbitrários nativamente. Cookie HttpOnly é o modelo correto para SSR + HTMX.

**Fluxo de autenticação:**

```
POST /admin/login
  -> valida usuario/senha com bcrypt
  -> gera JWT (python-jose, HS256, expira 8h)
  -> Set-Cookie: access_token={jwt}; HttpOnly; Secure; SameSite=Lax; Path=/admin
  -> redireciona para /admin/dashboard
```

**Validação em cada request admin:**

```python
async def get_current_admin(request: Request, db=Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401)
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(status_code=401)
    return await repo_admin.get_admin_by_id(db, payload["sub"])
```

### 14.2 Proteção CSRF — Double Submit Cookie

Como o JWT está em cookie (não Bearer), **CSRF é obrigatório** em todos os POSTs do painel admin.

```
1. No login, além do cookie JWT, define:
   Set-Cookie: csrf_token={uuid4}; Secure; SameSite=Lax; Path=/admin
   (NÃO HttpOnly — o JavaScript precisa lê-lo para inserir nos forms)

2. Todo form HTML do admin inclui:
   <input type="hidden" name="csrf_token" value="{{ csrf_token }}">

3. Todo request HTMX inclui:
   hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'

4. Middleware FastAPI valida em todo POST/PUT/DELETE:
   cookie csrf_token == header X-CSRF-Token (ou campo csrf_token do form)
```

GETs do admin e rotas públicas `/t/{token}/...` não precisam de CSRF.

### 14.3 Cookies do participante

```
Set-Cookie: attempt_token={token_original}; HttpOnly; Secure; SameSite=Lax; Path=/t/
```

Usado apenas para retomada se o browser fechar. O banco armazena apenas `SHA-256(token)`.

---

## 15. VARIÁVEIS DE AMBIENTE

```env
DATABASE_URL=postgresql+asyncpg://profiledna_user:SENHA@postgres:5432/profiledna_db
SECRET_KEY=gere_64_chars_aleatorios_aqui
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
ADMIN_USERNAME=admin_dna
ADMIN_PASSWORD=troque_no_primeiro_acesso
ENVIRONMENT=production
DEBUG=False
APP_HOST=0.0.0.0
APP_PORT=8000
```

Gerar SECRET_KEY: `python -c "import secrets; print(secrets.token_hex(32))"`

---

## 16. INFRAESTRUTURA E DEPLOY

**Servidor:** Hetzner VPS Ubuntu 22.04, mínimo 4 vCPU / 8GB RAM / 80GB SSD

**Containers produção:** nginx (80/443), web (8000 interno), db (5432 interno)

**Diretórios no servidor:**

```
/srv/profiledna/prod/       → compose + configs
/srv/profiledna/runtime/    → .env (permissões 600)
/srv/profiledna/backups/    → dumps PostgreSQL
```

**Deploy:**

```bash
git pull && docker compose build web && docker compose up -d web && docker compose exec web alembic upgrade head
```

**Backup:** cron diário às 2h, retenção 30 dias.

**Health check:** `GET /health` → `{"status":"ok","database":"connected","ssot_version":"v1"}`

---

## 17. TESTES

---

### 17.1 CI (GitHub Actions) — Subida do sistema do zero (Migrations + Seeds mínimos)

### Por que existe
O CI (GitHub Actions) é o “teste automático” que garante que, ao pegar o repositório **do jeito que está no GitHub** e subir tudo **do zero** (banco vazio), o sistema:
- **sobe sem erro**
- **cria as tabelas necessárias**
- **tem os dados mínimos obrigatórios**
- **passa o fluxo público E2E** (simulando um participante real)

Sem isso, o projeto pode “parecer funcionar” em um ambiente já existente, mas falhar em deploys limpos, novos ambientes ou alterações futuras.

### O que o CI executa (ordem)
Arquivo: `.github/workflows/ci.yml`

1) **Subir serviços** (API + Postgres) via `compose/docker-compose.ci.yml`
2) **Rodar migrations** (criar/atualizar schema do banco):
   - `alembic upgrade head`
3) **Seed de defaults do domínio (mínimos obrigatórios)**:
   - Script: `scripts/seed_domain_defaults.py`
   - Objetivo: garantir existência de registros mínimos para o domínio funcionar em banco zerado, especialmente:
     - `admin_users` (para campos NOT NULL como `rodadas_aplicacao.criado_por`)
     - `clientes` (ex.: `DEFAULT_CLIENTE`)
     - `setores_empresa` (ex.: `GERAL`)
     - `rodadas_aplicacao` (ex.: `DEFAULT_RODADA_V1`)
4) **Gate SSOT no-legacy**:
   - Script: `scripts/gate_ssot_no_legacy.sh`
5) **E2E full smoke**:
   - Script: `tests/e2e/test_e2e_full_smoke.sh`

### Importante: CI não é Produção
- O seed acima existe para **ambiente efêmero de CI** (banco nasce vazio em toda execução).
- Produção mantém seus próprios dados reais; o CI não deve sobrescrever dados de produção.
- Os defaults criados pelo seed devem ser **idempotentes** (rodar 1x ou 10x não pode quebrar nem duplicar indevidamente).

### Arquivos envolvidos
- Workflow: `.github/workflows/ci.yml`
- Compose CI: `compose/docker-compose.ci.yml` (e override se houver)
- Migrations: `backend/alembic/versions/*.py`
- Seed defaults CI: `scripts/seed_domain_defaults.py`
- Gate SSOT: `scripts/gate_ssot_no_legacy.sh`
- E2E: `tests/e2e/test_e2e_full_smoke.sh`


| Prioridade | Teste | Consequência se falhar |
|-----------|-------|----------------------|
| 🔴 CRÍTICO | Golden Master scoring | Todos os relatórios errados |
| 🔴 CRÍTICO | Submit lock | Participante altera respostas |
| 🟡 ALTO | Autosave idempotência | Respostas duplicadas |
| 🟡 ALTO | Fluxo público completo | Produto não funciona |
| 🟢 MÉDIO | Autenticação admin | Acesso não autorizado |

```bash
pytest tests/ -v                                              # todos
pytest tests/unit/scoring/test_engine_golden_master.py -v    # crítico
pytest tests/ --cov=backend --cov-report=html                 # com cobertura
```

---

## 18. ORDEM DE DESENVOLVIMENTO

| # | Arquivo(s) | O que faz | Depende de |
|---|-----------|-----------|------------|
| 1 | `.env` + `requirements.txt` | Configuração e dependências | — |
| 2 | `backend/config.py` | Leitura segura de variáveis | .env |
| 3 | `backend/database.py` | Conexão PostgreSQL async | config.py |
| 4 | `data/ssot/profiledna/v1/*.json` | Dados congelados do teste | — |
| 5 | `backend/ssot/loader.py` + `validator.py` | Carrega e valida JSONs em memória | data/ssot/ |
| 6 | `backend/scoring/types.py` + `rules.py` + `engine.py` | Motor de cálculo puro | ssot/loader.py |
| 7 | `scoring/fixtures/` + `test_engine_golden_master.py` | Golden Master — valida cálculo | engine.py |
| 8 | `backend/models/*.py` | Todas as tabelas | database.py |
| 9 | Alembic init + primeira migration | Cria tabelas no PostgreSQL | models/ |
| 10 | `backend/repositories/*.py` | Queries ao banco | models/ |
| 11 | `backend/services/token.py` + `invite.py` | Token SHA-256 + convites | repositories/ |
| 12 | `backend/services/autosave.py` | Upsert idempotente | repositories/ + ssot/ |
| 13 | `backend/services/submit.py` | Transação atômica | scoring/ + repositories/ |
| 14 | `backend/reports/renderer.py` | Monta HTML do relatório | ssot/ + scoring/types |
| 15 | `backend/reports/pdf.py` | HTML → PDF WeasyPrint | renderer.py |
| 16 | `backend/schemas/*.py` | Schemas Pydantic | models/ |
| 17 | `backend/routers/public.py` | Rotas do participante | services/ + schemas/ |
| 18 | `backend/bi/selectors.py` + `services.py` + `charts.py` | BI analítico | repositories/ |
| 19 | `backend/routers/admin.py` | Rotas do painel DNA | services/ + bi/ |
| 20 | `backend/main.py` | Montagem final do app | todos os routers |
| 21 | Templates HTML públicos | landing → pergunta → resultado | — |
| 22 | Templates HTML admin | login → dashboard → BI | — |
| 23 | `static/css/app.css` + `static/js/app.js` | CSS responsivo + AJAX | — |
| 24 | `templates/reports/` | Seções modulares do relatório | renderer.py |
| 25 | `tests/integration/*.py` | Testes de integração | todos |
| 26 | `docker/` + `compose/` + `nginx/` | Containerização + Nginx | main.py |
| 27 | `scripts/seed_ssot.py` | Popula dados SSOT no banco | models/ + data/ssot/ |
| 28 | Deploy no Hetzner | Produção | tudo |

---

## 19. REGRAS ABSOLUTAS PARA GERAÇÃO DE CÓDIGO

1. **Código sempre 100% completo** — nunca `...` ou `# resto do código`
2. **Um arquivo por resposta** — com caminho exato no topo como comentário
3. **O GABARITO É SAGRADO** — nunca alterar, reordenar ou "corrigir"
4. **AS PERGUNTAS SÃO FIXAS** — usar exclusivamente as 100 do `questions_100.json`
5. **Stack imutável** — nunca sugerir tecnologias fora da Seção 3
6. **Imports sempre presentes** — todo arquivo começa com todos os imports
7. **Senhas nunca em texto puro** — sempre bcrypt com custo mínimo 12
8. **Variáveis sensíveis sempre no .env** — nunca hardcoded
9. **Token nunca em texto puro no banco** — sempre SHA-256
10. **`assert sum(counts.values()) == 100`** — obrigatório no engine, nunca remover
11. **Após cada arquivo:** informar qual gerar em seguida e por quê
12. **Comentários explicativos** — explicar o que cada bloco faz
13. **Instrução de execução** — como rodar/testar o arquivo isoladamente
14. **Async obrigatório** — todas as funções que acessam banco: `async def` + `await`
15. **Desempate determinístico** — Top/Bottom sempre com critério explícito (letra ASC)
16. **ReportSnapshot imutável** — após criar, nunca sobrescrever
17. **Não usar localStorage** — progresso sempre no banco via cookie
18. **Biblioteca correta por tipo** — library1 se pessoal, library2 se empresa

---

## 20. O QUE O SISTEMA FAZ — VISÃO PRÁTICA COMPLETA

### Do ponto de vista da DNA Agência

**Cadastrar cliente:** DNA acessa o painel, faz login, cria a empresa com nome, setor e dados do responsável.

**Criar rodada:** Para um cliente existente, cria uma rodada ("Diagnóstico Inicial Janeiro 2026"). Cada rodada agrupa todos os participantes daquela aplicação.

**Definir setores:** Cadastra os setores da empresa (Comercial, Operações, TI, Gestores) para permitir análise por área no BI.

**Gerar convites:** Seleciona rodada + setor + cargo + quantidade. O sistema gera N links únicos prontos para copiar e enviar.

**Enviar links:** DNA envia por WhatsApp ou e-mail. O sistema não envia automaticamente na v1.

**Acompanhar:** Painel mostra em tempo real: abertos, em andamento, concluídos — por rodada e setor.

**Ver resultado individual:** Após submit do participante, acessa relatório completo no painel + download PDF.

**Analisar o grupo (BI):** Médias por dimensão, radar por área, distribuição de perfis por setor, comparativo entre rodadas. Esse é o produto final da consultoria DNA.

**Exportar:** CSV ou XLSX com todos os participantes, scores e classificações — para entregar ao RH do cliente.

---

### Do ponto de vista do participante (colaborador)

**Recebe o link:** `https://profiledna.dna.com.br/t/abc-123-def`

**Abre no celular ou computador:** Vê apresentação do teste, clica "Começar".

**Preenche dados:** Nome, sobrenome, e-mail, tipo, empresa.

**Responde 100 perguntas:** Uma por vez, A ou B. Barra de progresso visível. Pode voltar e corrigir. Se fechar o navegador, retoma de onde parou.

**Revisa:** Vê todas as respostas antes de enviar. Pode alterar qualquer uma.

**Confirma envio:** Modal de aviso: "após confirmar, não será possível editar". Confirma.

**Vê o resultado:** Relatório completo imediatamente. Pode baixar PDF.

---

### O que o sistema garante

- **Fidelidade matemática:** Cálculo idêntico ao Excel original. Mesmo conjunto de respostas → mesmo resultado, sempre.
- **Imutabilidade:** Teste enviado não pode ser alterado por ninguém nem por nada.
- **Auditabilidade:** Snapshot imutável salvo no banco. Textos históricos nunca mudam mesmo com v2.
- **Privacidade:** Participante acessa apenas o próprio teste. Sem login, sem conta, sem acesso cruzado.
- **Escalabilidade:** 200 simultâneos sem degradação. Async FastAPI + autosave leve (<10ms por operação).
- **Continuidade:** Nenhuma resposta perdida se o browser fechar. Retomada automática.
- **Rastreabilidade:** Cada resultado vinculado a cliente + setor + rodada + versão do teste.

---

*Documento: SSOT_PROFILEDNA_v2_0.md*
*Versão: 2.0 FINAL — Fevereiro 2026*
*Substitui: CONTEXTO_PROJETO.md e SSOT_PROFILEDNA_v1_2.md*
*Próxima ação: Iniciar Etapa 1 da Seção 18*

---

## 21. AGENTE IA — ANÁLISE INTELIGENTE NO PAINEL DNA

> **Status de implementação:** Módulo **presente no codigo desde o deploy inicial**. Ativado/desativado via flag `AI_ENABLED` no `.env` — sem alterar codigo, sem divida tecnica.
> **Comportamento com `AI_ENABLED=false`:** Todos os endpoints `/admin/ai/*` retornam HTTP 404 com `{"detail": "Modulo de IA desabilitado"}`. A UI esconde o painel de chat via `{% if settings.ai_enabled %}`. Nenhuma chamada a OpenAI e feita.
> **Quando ativar:** Apos primeira rodada de dados reais (recomendado: minimo 30 participantes de pelo menos 2 clientes). Com dados reais as respostas passam de genericas para especificas e acionaveis.

### 21.0 cliente_id como scope de acesso no modulo IA

> **Resolucao da aparente contradicao com a Secao 2:** O sistema nao e SaaS multi-tenant. Mas dentro do painel da DNA, o `cliente_id` funciona como **scope de contexto obrigatorio** conforme Secao 2.2.1. No modulo IA isso e uma regra rigida de implementacao:

```python
@router.post("/admin/ai/chat")
async def ai_chat(
    body: AIChatRequest,
    request: Request,
    cliente_id: str = Query(...),   # vem do query param da tela — NUNCA do body
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # Valida que o cliente existe
    cliente = await repo_cliente.get_by_id(db, cliente_id)
    if not cliente:
        raise HTTPException(404)

    # Passa cliente_id fixo — o LLM nao pode altera-lo
    return await agent.run_agent(body.question, body.attempt_id, cliente_id, db)
```

O `cliente_id` nunca vem do corpo da requisicao nem dos argumentos do LLM. Ele e sempre extraido do query param da tela atual e injetado pelo router — **nao existe caminho para o agente cruzar dados entre clientes**.

---

### 21.1 O que o agente faz

O agente IA é um **assistente de análise para a DNA Agência**, disponível dentro do painel administrativo. Ele não substitui o relatório — ele aprofunda a interpretação dos dados já calculados.

A DNA usa o agente para:

- Entender melhor o resultado de um participante específico
- Formular perguntas de entrevista ou feedback baseadas no perfil
- Comparar um participante com a média do grupo ou setor
- Explorar o que um padrão de scores significa para a gestão
- Gerar hipóteses sobre dinâmicas de equipe

**Exemplos de perguntas que a DNA pode fazer:**

> "Quais perguntas de entrevista eu usaria para validar o score 8 em Liderança e 2 em Assertividade juntos?"

> "O que o perfil do setor Comercial desta empresa sugere sobre como estruturar o feedback coletivo?"

> "Como evoluiu a dimensão de Organização entre a Rodada 1 e a Rodada 2 deste cliente?"

> "Quais riscos aparecem quando Controle está alto (9) e Empatia está baixo (2)?"

> "Me dê 3 ações de PDI específicas para alguém com score 3 em Decisão de Risco no contexto de liderança sênior."

---

### 21.2 O que o agente NÃO faz (regras inegociáveis)

- **Não inventa dimensões, nomes ou regras** — responde apenas com base nos dados reais do sistema e nas bibliotecas fechadas
- **Não envia PII para a OpenAI** — nome, sobrenome e e-mail do participante nunca saem do servidor
- **Não acessa dados de clientes diferentes** — cada resposta é sempre escoped ao cliente atual
- **Não altera o relatório** — o relatório é gerado deterministicamente pelo engine; o agente apenas interpreta
- **Não faz diagnósticos** — sempre usa linguagem de hipótese ("tende a", "pode indicar", "sugere")
- **Não gera novas perguntas para o teste** — o banco de questões é fechado e imutável

---

### 21.3 Arquitetura do módulo

```
backend/ai_analyst/
├── agent.py          ← wrapper da OpenAI Responses API + orquestração de tools
├── tools.py          ← funções autorizadas que o modelo pode chamar
├── prompts.py        ← system prompts versionados + regras de comportamento
├── models.py         ← AIInteractionLog (auditoria obrigatória)
├── services.py       ← sanitização de entrada + montagem do context pack
├── router.py         ← endpoints do chat no painel admin
└── templates/
    ├── chat_panel.html    ← UI do chat embedded no painel
    └── chat_messages.html ← fragmentos HTMX das mensagens
```

---

### 21.4 `agent.py` — Wrapper OpenAI

**O que faz:** Recebe a pergunta da DNA, monta o contexto autorizado, chama a OpenAI Responses API com tool calling, processa as chamadas de ferramenta, e retorna a resposta final.

```python
# backend/ai_analyst/agent.py

async def run_agent(
    question: str,
    attempt_id: str | None,
    cliente_id: str,
    db: AsyncSession
) -> AgentResponse:

    # 1. Sanitiza a entrada (remove PII acidental)
    clean_question = services.sanitize_input(question)

    # 2. Monta o context pack inicial (sem PII)
    context = await services.build_context_pack(attempt_id, cliente_id, db)

    # 3. Chama a OpenAI com tools disponíveis
    response = await openai_client.responses.create(
        model="gpt-4o",
        instructions=prompts.SYSTEM_PROMPT,
        input=clean_question,
        tools=tools.TOOL_DEFINITIONS,
        context=context
    )

    # 4. Processa tool calls (se o modelo pediu dados adicionais)
    while response.requires_tool_call:
        tool_results = await tools.execute(response.tool_calls, cliente_id, db)
        response = await openai_client.responses.submit_tool_outputs(
            response.id, tool_results
        )

    # 5. Registra auditoria
    await _log_interaction(question, response, cliente_id, attempt_id, db)

    return AgentResponse(text=response.output_text)
```

**API escolhida:** OpenAI **Responses API** (não Assistants API — a Assistants está sendo descontinuada pela OpenAI em favor da Responses API).

---

### 21.5 `tools.py` — Funções Autorizadas

O modelo nunca acessa o banco diretamente. Ele só pode chamar estas funções explicitamente definidas, cada uma com checagem de `cliente_id`.

```python
# backend/ai_analyst/tools.py

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "get_attempt_context",
        "description": "Retorna scores, faixas e top/bottom de um participante específico. Não retorna nome nem email.",
        "parameters": {
            "attempt_id": {"type": "string", "description": "ID do attempt"}
        }
    },
    {
        "type": "function",
        "name": "get_cohort_stats",
        "description": "Retorna médias, medianas e distribuição de um cliente ou setor.",
        "parameters": {
            "cliente_id": {"type": "string"},
            "setor_id": {"type": "string", "optional": True},
            "rodada_id": {"type": "string", "optional": True}
        }
    },
    {
        "type": "function",
        "name": "get_dimension_definition",
        "description": "Retorna nome, área, competência RH e textos interpretativos de uma dimensão.",
        "parameters": {
            "letter": {"type": "string", "description": "Letra da dimensão (A..T)"}
        }
    },
    {
        "type": "function",
        "name": "get_library_text",
        "description": "Retorna o texto interpretativo de uma dimensão para um score específico.",
        "parameters": {
            "letter": {"type": "string"},
            "score": {"type": "integer"},
            "library": {"type": "string", "enum": ["basic", "premium"]}
        }
    },
    {
        "type": "function",
        "name": "get_premium_manager_blocks",
        "description": "Retorna os bullets dos blocos Gestor/RH relevantes para um perfil.",
        "parameters": {
            "top_letters": {"type": "array", "items": {"type": "string"}},
            "bottom_letters": {"type": "array", "items": {"type": "string"}}
        }
    },
    {
        "type": "function",
        "name": "compare_rodadas",
        "description": "Compara médias por dimensão entre duas rodadas do mesmo cliente.",
        "parameters": {
            "cliente_id": {"type": "string"},
            "rodada_id_1": {"type": "string"},
            "rodada_id_2": {"type": "string"}
        }
    }
]

async def execute(tool_calls: list, cliente_id: str, db: AsyncSession) -> list:
    results = []
    for call in tool_calls:
        # SEGURANÇA: valida que o cliente_id está presente em toda chamada
        result = await _dispatch(call.name, call.arguments, cliente_id, db)
        results.append({"tool_call_id": call.id, "output": json.dumps(result)})
    return results
```

**Regra crítica de segurança:** Toda função valida `cliente_id` antes de executar qualquer query. O modelo não pode acessar dados de outro cliente mesmo que tente passar um `cliente_id` diferente — a função usa sempre o `cliente_id` da sessão HTTP, não o argumento do modelo.

---

### 21.6 `prompts.py` — System Prompts Versionados

```python
# backend/ai_analyst/prompts.py

SYSTEM_PROMPT = """
Você é um assistente especializado em análise comportamental para consultores de RH e gestão.
Você trabalha com o instrumento ProfileDNA, que avalia 20 dimensões comportamentais em 3 áreas.

REGRAS DE COMPORTAMENTO — INEGOCIÁVEIS:

1. USE APENAS OS DADOS FORNECIDOS PELAS FERRAMENTAS. Nunca invente scores, textos ou dimensões.

2. LINGUAGEM DE HIPÓTESE. Sempre use: "tende a", "pode indicar", "sugere", "no contexto de".
   Nunca use: "é", "definitivamente", "certamente", "sempre". Você descreve tendências, não diagnósticos.

3. CITE AS DIMENSÕES USADAS. Ao final de cada resposta, informe quais dimensões e scores você utilizou.

4. SEM PII. Não use nomes de participantes nas respostas. Use "o participante" ou "o colaborador".

5. BIBLIOTECA FECHADA. Não crie novos textos interpretativos. Use apenas os textos das bibliotecas
   disponíveis pelas ferramentas.

6. TRANSPARÊNCIA SOBRE AMOSTRAS. Quando comparar com grupo, informe o tamanho da amostra
   ("com base em X participantes").

7. TOM PROFISSIONAL. Responda como um consultor sênior de RH: objetivo, acionável, sem julgamentos.

8. LIMITES DO INSTRUMENTO. Se a pergunta exigir inferências além dos dados disponíveis,
   declare claramente: "Os dados disponíveis não permitem concluir isso com confiança."

FORMATO DE RESPOSTA:
- Resposta direta (2-4 parágrafos ou lista de bullets, conforme o tipo de pergunta)
- Seção final: "Dimensões utilizadas: [A=7, D=8, M=2]"
"""

# Versão do prompt — incrementar ao mudar as regras
PROMPT_VERSION = "v1.0"
```

---

### 21.7 `models.py` — Auditoria de IA

Toda interação com o agente é registrada. Isso é obrigatório por três motivos: rastreabilidade em caso de resposta incorreta, controle de custos da API OpenAI, e conformidade com LGPD (saber o que foi processado sobre quem).

```python
# backend/ai_analyst/models.py

class AIInteractionLog(Base):
    __tablename__ = "ai_interaction_logs"

    id: UUID                    # PK
    admin_user_id: UUID         # FK → admin_users (quem perguntou)
    cliente_id: UUID            # FK → clientes (contexto da pergunta)
    attempt_id: UUID | None     # FK → attempts (se a pergunta foi sobre um participante)
    
    question_sanitized: str     # pergunta com PII removido
    tools_called: JSONB         # lista de tools chamadas e parâmetros (sem PII)
    response_text: str          # resposta final do agente
    prompt_version: str         # versão do system prompt usado
    
    model_used: str             # "gpt-4o"
    tokens_input: int           # para controle de custo
    tokens_output: int          # para controle de custo
    cost_usd: float             # custo estimado da chamada
    
    duration_ms: int            # tempo de resposta
    created_at: datetime
```

---

### 21.8 `services.py` — Preparação do Contexto

```python
# backend/ai_analyst/services.py

def sanitize_input(text: str) -> str:
    """Remove padrões de PII da pergunta antes de enviar para a OpenAI."""
    # Remove emails, CPFs, telefones que possam ter sido digitados acidentalmente
    text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '[EMAIL REMOVIDO]', text)
    text = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', '[CPF REMOVIDO]', text)
    return text

async def build_context_pack(
    attempt_id: str | None,
    cliente_id: str,
    db: AsyncSession
) -> dict:
    """
    Monta o contexto inicial enviado com a pergunta.
    Contém apenas dados não-PII necessários para o modelo entender o contexto.
    """
    context = {
        "cliente_nome": await get_cliente_nome(db, cliente_id),  # nome da empresa (não do participante)
        "total_participantes": await count_submitted(db, cliente_id),
        "rodadas_disponiveis": await list_rodadas_names(db, cliente_id),
    }

    if attempt_id:
        result = await repo_result.get_computed_result(db, attempt_id)
        context["participante_scores"] = result.scores      # SEM nome/email
        context["participante_bands"] = result.bands
        context["participante_top3"] = result.top3
        context["participante_bottom3"] = result.bottom3
        context["tipo_aplicacao"] = result.tipo_aplicacao

    return context
```

---

### 21.9 `router.py` — Endpoints do Chat

```
POST /admin/ai/chat
     Body: {question: str, attempt_id?: str, cliente_id: str}
     Auth: JWT obrigatório
     Retorna: {response: str, dimensions_used: list, interaction_id: UUID}

GET  /admin/ai/history/{cliente_id}
     Auth: JWT obrigatório
     Retorna: últimas 20 interações do agente para aquele cliente
```

---

### 21.10 Templates do Chat

#### `templates/ai_analyst/chat_panel.html`

Painel de chat embedded no painel admin. Aparece como sidebar ou modal ao lado do relatório do participante ou do BI do cliente. Campo de texto para digitar a pergunta, botão enviar, área de resposta com loading spinner.

#### `templates/ai_analyst/chat_messages.html`

Fragmento HTMX: uma mensagem do chat (pergunta da DNA + resposta do agente + dimensões utilizadas). Appended na área de conversa via `hx-swap="beforeend"` sem reload da página.

---

### 21.11 Onde o agente aparece no painel

**No detalhe do participante** (`/admin/participants/{id}`):
O painel de chat aparece à direita do relatório. Contexto pré-carregado: scores e top/bottom daquele participante. A DNA pode perguntar sobre ele diretamente.

**No BI do cliente** (`/admin/bi/cliente/{id}`):
O painel de chat aparece abaixo dos gráficos. Contexto pré-carregado: médias e distribuições do cliente. A DNA pode perguntar sobre o grupo.

---

### 21.12 Minimização de dados enviados à OpenAI

| Enviado para OpenAI | Não enviado para OpenAI |
|---------------------|------------------------|
| Scores A..T (0..10) | Nome do participante |
| Faixas (baixo/médio/alto) | Sobrenome do participante |
| Top3/Top5/Bottom3 | E-mail do participante |
| Textos da biblioteca (trechos relevantes) | Respostas A/B brutas |
| Médias do grupo (sem identificação) | CPF, telefone |
| Nome da empresa cliente | Qualquer outro PII |

---

### 21.13 Custos estimados

| Operação | Tokens estimados | Custo estimado (gpt-4o) |
|----------|-----------------|------------------------|
| Pergunta simples sobre 1 participante | ~1.500 tokens | ~US$ 0,006 |
| Comparação entre dois setores | ~3.000 tokens | ~US$ 0,012 |
| Análise de evolução entre rodadas | ~4.000 tokens | ~US$ 0,016 |

Valores de referência para Fevereiro 2026. Monitorar via `AIInteractionLog.cost_usd`.

---

### 21.14 Adições ao modelo de dados

```sql
-- Nova tabela de auditoria do agente
ai_interaction_logs:
    id, admin_user_id, cliente_id, attempt_id (nullable)
    question_sanitized, tools_called (JSONB), response_text
    prompt_version, model_used, tokens_input, tokens_output
    cost_usd, duration_ms, created_at

-- Índices para controle de custo e auditoria
CREATE INDEX idx_ai_logs_cliente ON ai_interaction_logs(cliente_id);
CREATE INDEX idx_ai_logs_user ON ai_interaction_logs(admin_user_id);
CREATE INDEX idx_ai_logs_created ON ai_interaction_logs(created_at);
```

---

### 21.15 Nova variável de ambiente necessária

```env
# Adicionar ao .env.example
OPENAI_API_KEY=sua_chave_openai_aqui
OPENAI_MODEL=gpt-4o
AI_ENABLED=true   # false para desativar o módulo sem remover o código
```

---

### 21.16 Adições à ordem de desenvolvimento (Seção 18)

Inserir após a Etapa 25 (testes de integração):

| # | Arquivo(s) | O que faz | Depende de |
|---|-----------|-----------|------------|
| 29 | `backend/ai_analyst/models.py` | Tabela de auditoria AIInteractionLog | models/ |
| 30 | `backend/ai_analyst/tools.py` | Funções autorizadas do agente | repositories/ + ssot/ |
| 31 | `backend/ai_analyst/prompts.py` | System prompts versionados | — |
| 32 | `backend/ai_analyst/services.py` | Sanitização + montagem de contexto | repositories/ |
| 33 | `backend/ai_analyst/agent.py` | Wrapper OpenAI Responses API | tools.py + prompts.py |
| 34 | `backend/ai_analyst/router.py` | Endpoints do chat | agent.py + schemas/ |
| 35 | Templates do chat | UI embedded no painel | router.py |
| 36 | Testes do agente | Permissões, sanitização, anti-PII | agent.py |

---

### 21.17 Testes obrigatórios do módulo

#### `tests/unit/ai_analyst/test_tools_permissions.py`

Verifica que nenhuma tool retorna dados de um `cliente_id` diferente do autorizado. Simula tentativa de injeção de `cliente_id` via argumento do modelo.

#### `tests/unit/ai_analyst/test_sanitization.py`

Verifica que `sanitize_input()` remove e-mails, CPFs e telefones antes do envio à OpenAI.

#### `tests/unit/ai_analyst/test_prompt_safety.py`

Verifica que o system prompt não contém instruções que poderiam expor PII e que `PROMPT_VERSION` está definido.

#### `tests/integration/test_agent_flow.py`

Fluxo completo com mock da OpenAI: pergunta → tool call → resultado → resposta. Verifica que auditoria é gravada corretamente.

---

### 21.18 Estrutura de pastas atualizada (adição à Seção 5)

```
backend/
├── ...
├── ai_analyst/                          ← NOVO: módulo do agente IA
│   ├── agent.py                         ← wrapper OpenAI Responses API + tool calling
│   ├── tools.py                         ← funções autorizadas (checagem de cliente_id)
│   ├── prompts.py                       ← system prompts versionados v1.0
│   ├── models.py                        ← AIInteractionLog (auditoria obrigatória)
│   ├── services.py                      ← sanitização de entrada + context pack
│   ├── router.py                        ← POST /admin/ai/chat + GET /admin/ai/history
│   └── templates/
│       ├── chat_panel.html              ← UI do chat embedded no painel
│       └── chat_messages.html           ← fragmentos HTMX das mensagens
```

---

*Seção 21 adicionada ao SSOT_PROFILEDNA_v2_0.md*
*Status: Arquitetura definida — implementar após primeira rodada de dados reais*


---

## ADDENDUMS (Registros de mudanças)

- **2026-03-14** — Addendum: `ADDENDUM_20260314_public_views_service.md` — criação de `backend/services/public_views.py` para centralizar review/report/confirm/pdf (router fino; persistência nos repositories).

- **2026-03-12** — Addendum: `ADDENDUM_20260312_public_flow_service.md` — criação de `backend/services/public_flow.py` para organizar regras do fluxo público (router fino; persistência nos repositories).

- **2026-03-14** — E2E smoke script (canônico): `tests/e2e/test_e2e_full_smoke.sh`
  - cobre: start/autosave/review/confirm/submit/report/pdf + aliases SSOT `/t/*` + checks DB + idempotência do submit.
  - execução: `bash tests/e2e/test_e2e_full_smoke.sh`
