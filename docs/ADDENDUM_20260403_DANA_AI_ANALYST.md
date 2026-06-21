# ADDENDUM — DANA AI Analyst
## ProfileDNA v2.0
## Data: 2026-04-03

### Status
Addendum oficial complementar ao `SSOT_PROFILEDNA_v2_0.md`.

### Regra de precedência
- O `SSOT_PROFILEDNA_v2_0.md` continua sendo a fonte única e principal de verdade do produto.
- Este addendum complementa e detalha especificamente a arquitetura, o escopo funcional, os limites e a direção evolutiva do módulo `backend/ai_analyst`.
- Em caso de conflito com regras centrais do produto — especialmente scoring, fluxo do participante, relatório oficial, segurança-base, imutabilidade do resultado, contratos centrais e SSOT de conteúdo — o SSOT prevalece.
- Este addendum passa a ser a referência oficial complementar para o audit e para a evolução do módulo DANA.

---

# 1. Objetivo deste addendum

Este addendum formaliza a expansão funcional do módulo de IA do ProfileDNA, denominado **DANA**, como assistente analítica especializada do painel administrativo da DNA Agência.

A DANA deve atuar como uma consultora inteligente de apoio ao gestor/admin do sistema, capaz de:

- ler e interpretar integralmente os **relatórios finais consolidados** dos participantes;
- ler e interpretar dados agregados do **BI do sistema**;
- comparar clientes, rodadas, grupos, setores e participantes, conforme os filtros autorizados;
- responder com base factual nos dados oficiais já consolidados no produto;
- enriquecer a análise com base documental especializada mantida em `backend/ai_analyst/docsIA`.

A DANA **não substitui** o motor determinístico do produto e **não recalcula** resultados oficiais.

---

# 2. Nome oficial e identidade funcional

O nome oficial do agente é:

**DANA**

Uso oficial nas telas:
- **Análise Inteligente Dana**
- **Chat com a Dana**
- **Dana — Assistente Analítica**

A DANA deve responder com linguagem:
- profissional;
- humanizada;
- acolhedora;
- tecnicamente precisa;
- consultiva;
- agradável na interação;
- sem perder rastreabilidade;
- sem perder responsabilidade técnica.

---

# 3. Escopo oficial da DANA

## 3.1 O que a DANA faz

A DANA é um agente de análise e interpretação que apoia o gestor/admin na leitura dos resultados do sistema.

Ela pode:
- interpretar resultados finais individuais;
- interpretar grupos de participantes;
- interpretar dados por cliente;
- interpretar dados por rodada;
- interpretar dados por setor;
- interpretar dados por cargo;
- interpretar comparativos entre clientes;
- interpretar comparativos entre rodadas;
- apoiar leitura do BI — Cliente;
- apoiar leitura do BI — Comparativo;
- sugerir hipóteses, perguntas de aprofundamento, riscos de gestão, focos de desenvolvimento e possibilidades de leitura consultiva;
- usar trechos relevantes dos documentos de `docsIA` como base complementar de conhecimento.

## 3.2 O que a DANA não faz

A DANA não pode:
- recalcular scoring;
- alterar ranking Top 3 / Top 5 / Bottom 3;
- alterar `computed_results`;
- alterar `report_snapshots`;
- alterar o relatório final oficial;
- alterar o BI oficial;
- inventar dimensões, regras, scores ou interpretações fora da base oficial do sistema;
- substituir avaliação técnica complementar, entrevista estruturada ou análise profissional humana;
- criar “novos resultados oficiais” paralelos ao motor do produto.

---

# 4. Base factual obrigatória da DANA

A DANA deve operar prioritariamente sobre os **dados oficiais já consolidados** do sistema.

## 4.1 Fontes factuais permitidas

A DANA pode consumir:
- `computed_results.scores`
- `computed_results.bands`
- `computed_results.top3`
- `computed_results.top5`
- `computed_results.bottom3`
- `computed_results.interpretations`
- `computed_results.premium_data`
- `report_snapshots.html_content`
- dados de identificação e contexto do relatório final exibido ao admin, observadas as regras de proteção de dados deste addendum e do SSOT;
- agregados de BI por cliente, rodada, setor, cargo e tipo de aplicação;
- comparativos oficiais do BI;
- metadados do escopo selecionado no painel admin.

## 4.2 Regra fixa sobre respostas brutas

Fica expressamente definido que a DANA **não depende de respostas A/B brutas** para operar.

A DANA:
- não precisa consumir a lista das 100 respostas individuais;
- não precisa reconstruir o teste pergunta a pergunta;
- não precisa enviar respostas A/B ao modelo externo;
- não deve ser tratada como leitora da prova bruta, mas como leitora e intérprete do **resultado final oficial consolidado**.

O foco da DANA é o **resultado final oficial consolidado**, não a matéria-prima bruta do teste.

---

# 5. Leitura integral do relatório final

A DANA deve conseguir acessar e interpretar **todas as informações presentes no relatório final estruturado**.

## 5.1 Seções mínimas obrigatórias do relatório final que entram no contexto da DANA

1. Identificação
2. Síntese Executiva
3. Painel de Resultados por Área
4. Pontos Fortes (Top 5)
5. Oportunidades de Desenvolvimento (Bottom 3)
6. Competências-Chave para PDI
7. Recomendações para Gestor / RH
8. Dimensões Detalhadas (20)
9. Nota Técnica

## 5.2 Regra funcional

Tudo o que estiver apresentado no relatório final ao admin deve poder ser:
- lido pela DANA;
- discutido pela DANA;
- contextualizado pela DANA;
- aprofundado pela DANA com apoio de `docsIA`.

A DANA não pode contradizer o relatório oficial do sistema.

## 5.3 Regra prática de interpretação

A DANA deve ser capaz de discutir com o gestor/admin:
- destaques principais;
- pontos de atenção;
- médias por área;
- Top 5;
- Bottom 3;
- competências para potencializar;
- competências para desenvolver;
- ações recomendadas;
- comportamentos-alvo;
- rotinas práticas;
- indicadores de evolução;
- recomendações para Gestor/RH;
- dimensões detalhadas;
- enquadramento metodológico e nota técnica.

---

# 6. Pasta docsIA — base documental do agente

## 6.1 Local oficial

A base documental da DANA deve existir em:

`/srv/profiledna/backend/ai_analyst/docsIA`

## 6.2 Finalidade

A pasta `docsIA` conterá documentos em PDF que servirão como base complementar de conhecimento especializado da DANA.

Exemplos de temas:
- psicologia comportamental;
- PDCI;
- DISC;
- liderança;
- desenvolvimento humano;
- feedback;
- gestão de desempenho;
- comportamento organizacional;
- materiais técnicos correlatos aprovados pela DNA Agência.

## 6.3 Regra de uso

Os documentos de `docsIA`:
- servem para enriquecer interpretação e orientação consultiva;
- não substituem o SSOT do produto;
- não alteram scoring;
- não alteram dimensões;
- não alteram bibliotecas oficiais do relatório;
- não alteram regras do motor do sistema;
- não podem ser usados para sobrescrever a verdade oficial já consolidada pelo produto.

## 6.4 Estrutura recomendada

`docsIA/` deve conter ao menos:
- `README.md`
- `manifest.json`
- subpastas temáticas
- PDFs versionados e rastreáveis

## 6.5 Manifesto documental

O `manifest.json` deve catalogar cada documento com pelo menos:
- `document_id`
- `title`
- `theme`
- `source_type`
- `version`
- `status`
- `tags`
- `file_path`
- `hash`
- `included_at`

---

# 7. Nova página oficial do painel admin

## 7.1 Nome da página

A nova página oficial do painel deve se chamar:

**Análise Inteligente Dana**

## 7.2 Finalidade

Esta página será o ambiente principal de interação entre o gestor/admin e a DANA.

## 7.3 Layout obrigatório

A página deve ser dividida em duas metades principais.

### Lado esquerdo
Painel de dados e contexto do escopo selecionado:
- cliente;
- participante;
- grupo;
- rodada;
- setor;
- comparativo;
- BI relacionado;
- relatório final relacionado.

### Lado direito
Chat com a DANA:
- histórico da conversa;
- respostas do agente;
- loading/status;
- fontes usadas;
- rastreabilidade da análise.

---

# 8. Busca flexível da DANA

A página “Análise Inteligente Dana” deve oferecer busca flexível para o gestor/admin.

## 8.1 Filtros e eixos mínimos de busca

A busca deve permitir, isoladamente ou em combinação, recortes por:
- cliente;
- participante;
- participante por cliente;
- data;
- rodada;
- setor;
- cargo;
- área;
- dimensão;
- tipo de aplicação;
- grupos de participantes;
- cliente vs cliente;
- rodada vs rodada;
- BI — Cliente;
- BI — Comparativo.

## 8.2 Regra de comportamento

A busca deve ser:
- flexível;
- rastreável;
- reproduzível;
- aderente ao escopo autorizado do painel admin.

---

# 9. Regras de contexto e resposta

## 9.1 Dupla base de resposta

A DANA deve responder sempre combinando duas bases:

### Base factual
- dados oficiais do sistema;
- relatório final;
- BI consolidado;
- comparativos oficiais.

### Base consultiva
- trechos relevantes recuperados da `docsIA`.

## 9.2 Regra de transparência

A DANA deve distinguir claramente:
- o que é dado factual do sistema;
- o que é interpretação consultiva;
- o que é hipótese;
- o que é recomendação.

## 9.3 Linguagem obrigatória

A DANA deve usar linguagem:
- clara;
- humana;
- agradável;
- profissional;
- respeitosa;
- tecnicamente responsável.

Sempre que extrapolar para leitura interpretativa, deve usar linguagem de hipótese, como:
- “tende a”
- “pode indicar”
- “sugere”
- “no contexto observado”
- “à luz dos dados disponíveis”

---

# 10. Proteção de dados e envio ao modelo externo

## 10.1 Regra mantida

Este addendum não autoriza envio irrestrito de dados ao modelo externo.

## 10.2 Regra consolidada

A arquitetura da DANA deve separar claramente:
- o que o sistema consegue acessar internamente;
- o que é efetivamente serializado para o modelo externo.

## 10.3 Diretriz operacional

A DANA deve priorizar envio ao modelo de:
- resultados consolidados;
- blocos do relatório final;
- métricas agregadas de BI;
- trechos relevantes de `docsIA`;
- contexto analítico necessário à pergunta do gestor.

A DANA não precisa enviar as respostas A/B brutas.

## 10.4 Regra de PII

Permanece obrigatório que a DANA não envie à OpenAI:
- nome do participante;
- sobrenome do participante;
- e-mail do participante;
- telefone, CPF ou qualquer outro dado pessoal sensível;
- respostas A/B brutas.

A arquitetura deve montar contexto analítico suficiente para interpretação sem expor PII ao modelo externo.

---

# 11. Arquitetura alvo do módulo ai_analyst

Importante: a estrutura abaixo representa a **arquitetura alvo oficial** do módulo DANA.

Ela **não implica** que todos os arquivos já existam no estado atual do repositório.

O audit deverá avaliar o estado atual do código em relação a este alvo.

```text
backend/ai_analyst/
├── agent.py
├── tools.py
├── prompts.py
├── models.py
├── services.py
├── router.py
├── context_builder.py
├── retrieval.py
├── search.py
├── docsIA/
│   ├── README.md
│   ├── manifest.json
│   ├── psicologia_comportamental/
│   ├── pdci/
│   ├── disc/
│   ├── lideranca/
│   ├── feedback/
│   ├── desenvolvimento_humano/
│   └── outros/
├── templates/
│   ├── analysis_inteligente_dana.html
│   ├── analysis_results_panel.html
│   ├── analysis_chat_panel.html
│   ├── chat_panel.html
│   └── chat_messages.html
└── ingest/
    ├── extractor.py
    ├── chunker.py
    ├── embeddings.py
    ├── indexer.py
    └── validators.py
