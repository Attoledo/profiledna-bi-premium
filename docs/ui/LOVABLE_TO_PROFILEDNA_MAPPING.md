# LOVABLE TO PROFILEDNA MAPPING

## 1. Objetivo

Este documento traduz a referência visual do Lovable para a implementação real do ProfileDNA.

Ele existe para evitar dois erros:

1. copiar a stack do Lovable para a produção v1
2. perder fidelidade visual ao portar as telas para o sistema real

O objetivo é responder, com precisão:

- qual tela do Lovable corresponde a qual tela do ProfileDNA
- quais arquivos reais devem ser criados ou alterados
- o que é puramente visual
- o que depende de integração real
- em que ordem a implementação deve acontecer

## 2. Regras gerais de mapeamento

## 2.1 Regra de arquitetura
A stack do produto real continua sendo a definida no SSOT.  
Logo:

- o Lovable é **referência visual**
- o ProfileDNA real é **implementação oficial**

## 2.2 Regra de aderência
Toda porta visual deve respeitar:
- SSOT
- Documento Programa
- layout de referência aprovado

## 2.3 Regra de não invenção
Este mapeamento não autoriza:
- criar telas extras
- criar novas entidades
- mudar contratos de negócio
- introduzir comportamento fora do SSOT

## 3. Mapa geral — Lovable → Produto real

| Lovable | Função | Destino real sugerido |
|---|---|---|
| `src/routes/login.tsx` | Login do painel | `backend/templates/admin/login.html` |
| `src/components/AppShell.tsx` | Shell/navegação global | `backend/templates/admin/base.html` + includes |
| `src/routes/_app.dashboard.tsx` | Dashboard do operador | `backend/templates/admin/dashboard.html` |
| `src/routes/_app.bi.visao-geral.tsx` | BI coletivo | `backend/templates/admin/bi_overview.html` |
| `src/routes/_app.bi.comparativo.tsx` | BI comparativo | `backend/templates/admin/bi_comparative.html` |
| `src/routes/_app.participantes.index.tsx` | Lista de participantes | `backend/templates/admin/participants.html` |
| `src/routes/_app.participantes.$id.tsx` | Relatório individual | `backend/templates/admin/participant_detail.html` |
| `src/routes/_app.dana.tsx` | Assistente analítica | `backend/templates/admin/dana.html` ou integração com `backend/ai_analyst/templates/*` |

## 4. Mapeamento detalhado por tela

## 4.1 Login

### Origem Lovable
- `src/routes/login.tsx`

### Destino ProfileDNA
- `backend/templates/admin/login.html`

### O que deve ser portado
- layout em duas colunas
- branding DNA no bloco esquerdo
- formulário limpo no bloco direito
- CTA principal em gradiente DNA
- rodapé curto de segurança/auditoria

### O que continua real no sistema
- autenticação real do admin
- cookie/JWT
- CSRF
- validação de credenciais

### Observação
O visual pode ser praticamente reproduzido integralmente.

---

## 4.2 Base shell / navegação

### Origem Lovable
- `src/components/AppShell.tsx`

### Destino ProfileDNA
- `backend/templates/admin/base.html`
- `backend/templates/admin/components/top_nav.html`
- `backend/templates/admin/components/client_selector.html`

### O que deve ser portado
- logo + `/ ProfileDNA`
- menu horizontal superior
- destaque visual do item ativo
- seletor de cliente
- saída/logout
- área central de conteúdo

### O que continua real no sistema
- URLs reais do painel
- permissões do admin
- troca real de contexto por cliente
- renderização server-side

### Observação
Esta é a fundação visual de todas as telas internas.  
Deve ser implementada antes das demais.

---

## 4.3 Dashboard

### Origem Lovable
- `src/routes/_app.dashboard.tsx`

### Destino ProfileDNA
- `backend/templates/admin/dashboard.html`
- `backend/static/admin/js/dashboard.js`

### O que deve ser portado
- saudação curta
- nome do cliente em destaque
- cards KPI
- atalhos para BI / comparativo / DANA
- bloco de rodadas
- atividade recente

### Dados reais necessários
- clientes ativos
- rodadas por cliente
- participantes concluídos
- participantes em andamento
- taxa de conclusão
- atividade recente

### Aderência ao SSOT
Totalmente compatível com o painel administrativo e acompanhamento operacional definidos no SSOT.

---

## 4.4 BI — Visão Geral

### Origem Lovable
- `src/routes/_app.bi.visao-geral.tsx`

### Destino ProfileDNA
- `backend/templates/admin/bi_overview.html`
- `backend/static/admin/js/bi_overview.js`

### O que deve ser portado
- filtros por cliente/rodada/setor
- radar de áreas
- distribuição das dimensões
- top 5 forças coletivas
- bottom 3 pontos de atenção
- ranking das 20 dimensões

### Dados reais necessários
- médias por dimensão
- médias por área
- contagem por faixas
- recorte por setor
- recorte por rodada
- top/bottom do grupo

### Aderência ao SSOT
Alta aderência com a seção de BI por cliente e com a proposta de leitura coletiva do grupo.

---

## 4.5 BI — Comparativo

### Origem Lovable
- `src/routes/_app.bi.comparativo.tsx`

### Destino ProfileDNA
- `backend/templates/admin/bi_comparative.html`
- `backend/static/admin/js/bi_comparative.js`

### O que deve ser portado
- seleção de recorte A
- seleção de recorte B
- insight automático
- radar A vs B
- maiores mudanças
- delta completo por dimensão

### Dados reais necessários
- médias do recorte A
- médias do recorte B
- cálculo de delta
- lista ordenada por diferença absoluta
- evolução/retração por dimensão

### Aderência ao SSOT
Alta aderência com o comparativo entre rodadas explicitamente previsto.

---

## 4.6 Participantes — Lista

### Origem Lovable
- `src/routes/_app.participantes.index.tsx`

### Destino ProfileDNA
- `backend/templates/admin/participants.html`
- `backend/static/admin/js/participants.js`

### O que deve ser portado
- busca
- filtros simples
- tabela operacional
- badge de status
- ação “Abrir relatório”

### Dados reais necessários
- lista paginada/filtrável de participantes
- status do convite/processo
- cliente
- rodada
- setor
- cargo
- ação de abertura

### Aderência ao SSOT
Alta aderência com o painel que mostra abertos, em andamento e concluídos.

---

## 4.7 Participante — Detalhe

### Origem Lovable
- `src/routes/_app.participantes.$id.tsx`

### Destino ProfileDNA
- `backend/templates/admin/participant_detail.html`
- `backend/static/admin/js/participant_detail.js`

### O que deve ser portado
- cabeçalho forte do participante
- ação de PDF
- ação de DANA
- síntese executiva
- radar por área
- top 5
- bottom 3
- 20 dimensões
- recomendações para gestor/RH

### Dados reais necessários
- dados do participante
- resultado consolidado oficial
- snapshot congelado
- top/bottom determinísticos
- relatório final compatível com SSOT
- PDF real

### Aderência ao SSOT
Muito alta.  
Esta é uma das telas mais importantes, porque tangencia diretamente o relatório final previsto no SSOT e no Documento Programa.

---

## 4.8 DANA

### Origem Lovable
- `src/routes/_app.dana.tsx`

### Destino ProfileDNA
Duas possibilidades, mantendo aderência ao que já existe no projeto:

#### opção principal
- `backend/templates/admin/dana.html`

#### integração mais aderente ao módulo atual
- `backend/ai_analyst/templates/chat_panel.html`
- `backend/ai_analyst/templates/chat_messages.html`
- composição dentro da área admin

### O que deve ser portado
- sidebar de conversas
- contexto do participante/cliente
- bubble de mensagens
- input de pergunta
- sugestões rápidas
- sensação de assistente analítico contextual

### Dados reais necessários
- contexto do participante
- histórico curto
- respostas do agente
- logs de interação
- escopo por `cliente_id`
- auditoria

### Aderência ao SSOT
Muito alta, desde que respeite:
- escopo por `cliente_id`
- auditoria obrigatória
- não recalcular resultados
- apenas interpretar dados existentes

## 5. Mapeamento de assets e estilo

## 5.1 Origem Lovable
- `src/styles.css`
- `src/assets/dna-logo.png`

## 5.2 Destino ProfileDNA
- `backend/static/admin/css/profiledna-admin.css`
- `backend/static/admin/img/dna-logo.png`

## 5.3 O que deve ser portado
- paleta DNA
- gradiente institucional
- cantos arredondados
- sombras suaves
- badges
- cards
- comportamento visual dos botões
- estados ativos da navegação

## 6. Mapeamento de componentes reutilizáveis

Mesmo sem copiar a stack do Lovable, os seguintes blocos devem virar componentes parciais reutilizáveis no produto real:

- top navigation
- client selector
- KPI card
- status badge
- filter bar
- chart card
- participant header
- dimension row
- dana chat bubble

### Destino sugerido
- `backend/templates/admin/components/*`

## 7. O que pode ser reproduzido quase 1:1

Pode ser reproduzido com altíssima fidelidade:

- estrutura da navegação
- distribuição dos blocos
- ordem de leitura
- hierarquia visual
- paleta
- gradiente
- proporção de cards
- tabelas
- badges
- cabeçalhos das telas

## 8. O que precisa de adaptação

Precisa de adaptação para o sistema real:

- filtros dinâmicos
- gráficos alimentados por dados reais
- links reais do painel
- estado ativo por rota server-side
- autenticação do login
- PDF real
- histórico real da DANA
- integração com `backend/ai_analyst/`

## 9. O que NÃO deve ser portado literalmente

Não deve ser portado literalmente:

- TanStack Router como base da v1
- mocks do Lovable como dado de produção
- fluxo fake do chat
- dependências React-only só para “parecer igual”
- decisões de stack que conflitem com o SSOT

## 10. Ordem de implementação recomendada

### Etapa 1 — fundação visual
1. `login.html`
2. `base.html`
3. componentes de navegação e estilo global

### Etapa 2 — operação básica
4. `dashboard.html`
5. `participants.html`

### Etapa 3 — leitura individual
6. `participant_detail.html`

### Etapa 4 — leitura coletiva
7. `bi_overview.html`
8. `bi_comparative.html`

### Etapa 5 — assistente analítica
9. `dana.html` / integração com templates do módulo IA

## 11. Critérios de aceite por tela

## 11.1 Critério geral
Cada tela portada deve passar em três níveis:

### A. Fidelidade visual
- mesma hierarquia
- mesma organização
- mesma sensação de marca

### B. Fidelidade funcional
- mesma função para o gestor
- mesmas ações principais
- mesma leitura executiva

### C. Fidelidade ao produto real
- aderente ao SSOT
- sem quebrar segurança
- sem inventar contrato
- sem trocar stack

## 12. Riscos principais

### 12.1 Risco de copiar a stack errada
Mitigação: usar o Lovable como blueprint, não como arquitetura final.

### 12.2 Risco de perder fidelidade visual
Mitigação: usar este documento junto com `LOVABLE_UI_REFERENCE.md` e os prints aprovados.

### 12.3 Risco de misturar visual com lógica
Mitigação: primeiro portar a camada visual, depois integrar os dados reais.

## 13. Resultado esperado ao final do porte

Quando o porte estiver concluído, o ProfileDNA real deverá apresentar:

- login com a identidade do protótipo aprovado
- shell administrativa consistente
- dashboard executivo limpo
- BI coletivo e comparativo claros
- leitura individual forte para gestor/RH
- DANA integrada ao painel com aparência madura

## 14. Status

Status deste documento: **MAPPING INICIAL APROVADO PARA INÍCIO DE IMPLEMENTAÇÃO**

Próxima etapa recomendada:
- auditar o repositório real
- mapear arquivos existentes
- iniciar o porte da primeira tela real
