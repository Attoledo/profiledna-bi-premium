# LOVABLE UI REFERENCE — ProfileDNA

## 1. Objetivo

Este documento congela a interface gerada no Lovable como **referência visual e funcional oficial** para a camada administrativa do ProfileDNA.

Ele **não substitui** o SSOT do produto.  
Seu papel é servir como **baseline de UX/UI**, para que a implementação real no projeto ProfileDNA reproduza, com a maior fidelidade possível:

- navegação
- hierarquia visual
- organização das telas
- densidade de informação
- identidade visual
- padrões de interação

## 2. Hierarquia de verdade

### 2.1 Fonte de verdade de produto
A fonte de verdade de produto continua sendo:

- `SSOT_PROFILEDNA_v2_0.md`
- `DOCUMENTO PROGRAMA TESTE PERFIL DNA.pdf`

### 2.2 Fonte de verdade visual
Para UI administrativa, a referência visual congelada é o conjunto Lovable enviado pelo cliente, composto por:

- `src/components/AppShell.tsx`
- `src/router.tsx`
- `src/styles.css`
- `src/routes/__root.tsx`
- `src/routes/_app.tsx`
- `src/routes/_app.dashboard.tsx`
- `src/routes/_app.bi.visao-geral.tsx`
- `src/routes/_app.bi.comparativo.tsx`
- `src/routes/_app.participantes.index.tsx`
- `src/routes/_app.participantes.$id.tsx`
- `src/routes/_app.dana.tsx`
- `src/routes/index.tsx`
- `src/routes/login.tsx`
- `src/mocks/data.ts`
- `src/lib/utils.ts`
- `src/hooks/use-mobile.tsx`
- `src/components/ui/*`
- `src/assets/dna-logo.png`

## 3. Escopo das telas cobertas

Este baseline cobre as seguintes telas administrativas:

1. Login
2. Dashboard
3. BI — Visão Geral
4. BI — Comparativo
5. Participantes — Lista
6. Participante — Detalhe / relatório individual
7. DANA — Assistente analítica

## 4. Princípios visuais gerais

A interface Lovable consolida os seguintes princípios visuais:

### 4.1 Leitura executiva
As telas foram organizadas para leitura rápida por gestor/operador:

- título claro no topo
- contexto curto abaixo do título
- cards com borda suave
- poucos ruídos visuais
- blocos densos, mas organizados

### 4.2 Marca DNA
A identidade visual usa:

- fundo claro e limpo
- navy institucional como base
- gradiente DNA laranja → coral como destaque
- sombras suaves
- cantos arredondados
- aparência premium e corporativa

### 4.3 Padrão de cards
Quase toda a UI é organizada em cards com:

- borda sutil
- fundo branco
- padding generoso
- sombra leve
- título curto
- subtítulo discreto

### 4.4 Padrão de navegação
A navegação principal é horizontal, persistente no topo, com:

- logo DNA
- nome do produto `/ ProfileDNA`
- menu principal
- seletor de cliente
- saída/logout

## 5. Estrutura de navegação

A shell principal (`AppShell.tsx`) organiza a navegação em cinco áreas:

- Dashboard
- BI · Visão Geral
- BI · Comparativo
- Participantes
- DANA

### 5.1 Comportamento esperado
- o item ativo aparece destacado
- o seletor de cliente permanece visível
- a navegação deve estar disponível em todas as telas internas
- a área de conteúdo fica abaixo da barra superior

## 6. Tela por tela — referência funcional

## 6.1 Login

### Objetivo
Ser a porta institucional de entrada do painel.

### Estrutura
- lado esquerdo com branding forte da DNA
- lado direito com formulário simples
- texto de valor do produto
- CTA único e claro

### Sensação desejada
- segurança
- sofisticação
- clareza
- produto maduro

---

## 6.2 Dashboard

### Objetivo
Ser o hall de entrada do operador.

### O que mostra
- saudação
- cliente atual em destaque
- KPIs rápidos
- atalhos principais
- rodadas do cliente
- atividade recente

### Função prática
Permitir que o operador decida rapidamente por onde continuar:

- olhar o grupo
- comparar rodadas
- entrar em um participante
- abrir a DANA

---

## 6.3 BI — Visão Geral

### Objetivo
Mostrar o retrato consolidado do grupo.

### O que mostra
- filtros por cliente, rodada e setor
- radar das 3 áreas
- distribuição das 20 dimensões
- top 5 forças coletivas
- bottom 3 pontos de atenção
- ranking completo das médias das 20 dimensões

### Função prática
Permitir leitura coletiva do recorte atual:
- onde o grupo está mais forte
- onde o grupo está mais frágil
- como as 20 dimensões se distribuem
- quais temas merecem aprofundamento individual

---

## 6.4 BI — Comparativo

### Objetivo
Comparar dois recortes.

### O que mostra
- seleção de recorte A
- seleção de recorte B
- insight automático
- sobreposição das 3 áreas
- dimensões com maior mudança
- delta completo por dimensão

### Função prática
Responder:
- o que mudou
- onde houve evolução
- onde houve regressão
- quais dimensões merecem leitura gerencial

---

## 6.5 Participantes — Lista

### Objetivo
Ser a visão operacional de pessoas avaliadas.

### O que mostra
- busca por nome
- filtro por status
- filtro por setor
- tabela de participantes
- ação de abrir relatório individual

### Função prática
Permitir localizar rapidamente:
- quem concluiu
- quem está em andamento
- quem ainda não começou
- quem deve ser aberto para leitura individual

---

## 6.6 Participante — Detalhe

### Objetivo
Transformar o resultado individual em leitura executiva.

### O que mostra
- cabeçalho forte com identidade da pessoa
- botão de PDF
- botão para DANA
- síntese executiva
- radar por área
- top 5 pontos fortes
- bottom 3 oportunidades de desenvolvimento
- 20 dimensões detalhadas
- recomendações para gestor / RH

### Função prática
Dar ao gestor uma leitura pronta para:
- devolutiva
- PDI
- acompanhamento
- leitura individual aprofundada

---

## 6.7 DANA

### Objetivo
Ser a assistente analítica contextual do painel.

### O que mostra
- contexto do participante em foco
- histórico recente de conversas
- área de chat
- sugestões de pergunta
- input principal

### Função prática
Transformar dados em ação:
- interpretar perfil
- ajudar em PDI
- sugerir acompanhamento
- ajudar em feedback
- apoiar leitura gerencial

## 7. Padrões visuais recorrentes

## 7.1 Gradiente DNA
Uso recorrente em:
- botões principais
- ícones destacados
- avatar/monograma
- cabeçalhos estratégicos

## 7.2 Tipografia
- títulos fortes e curtos
- subtítulos discretos
- textos de apoio com baixa agressividade
- boa leitura para contexto executivo

## 7.3 Status
Badges de status seguem lógica simples:
- concluído
- em andamento
- convite enviado

## 7.4 Tabelas
As tabelas devem:
- ser limpas
- ter leitura rápida
- manter colunas operacionais claras
- usar ação forte apenas quando necessário

## 7.5 Gráficos
Os gráficos seguem leitura gerencial e não acadêmica:
- radar simples
- barras ordenadas
- pizza/distribuição enxuta
- comparativo visual direto

## 8. Padrões de UX

## 8.1 Hierarquia
Em quase todas as telas:
1. contexto da tela
2. bloco-resumo
3. exploração analítica
4. detalhamento

## 8.2 Ações
As ações importantes são sempre poucas e visíveis:
- abrir
- baixar PDF
- conversar com DANA
- comparar
- filtrar

## 8.3 Clareza
A interface evita:
- excesso de botões
- excesso de cor
- excesso de texto introdutório
- excesso de elementos decorativos

## 9. Restrições de implementação

### 9.1 O que este documento NÃO autoriza
Este documento não autoriza:
- trocar a stack do produto pelo stack do Lovable
- substituir o frontend real por TanStack/React em v1
- inventar telas não aprovadas
- alterar a lógica de negócio do SSOT

### 9.2 O que este documento autoriza
Este documento autoriza:
- usar o Lovable como blueprint visual
- reproduzir layout, hierarquia e comportamento
- portar visualmente as telas para a arquitetura real do ProfileDNA

## 10. Critério de fidelidade

Uma tela portada só será considerada aderente quando reproduzir, com alta fidelidade:

- mesma organização macro
- mesma hierarquia visual
- mesma função
- mesma leitura executiva
- mesma sensação de marca

## 11. Status

Status deste documento: **BASELINE VISUAL CONGELADA**

Mudanças futuras no padrão visual só devem ocorrer se:
- forem aprovadas explicitamente
- não quebrarem o SSOT
- forem documentadas em addendum de UI
