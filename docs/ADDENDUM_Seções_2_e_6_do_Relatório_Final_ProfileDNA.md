# ADDENDUM — Seções 2 e 6 do Relatório Final ProfileDNA

## 1. Finalidade deste addendum

Este addendum tem como objetivo **formalizar e congelar** a regra de apresentação das:

- **Seção 2 — Síntese Executiva**
- **Seção 6 — Competências-Chave para PDI**

Este documento:

- **não altera** o SSOT principal
- **não substitui** o Documento Programa
- **não altera** regras de motor, scoring, ranking ou bibliotecas
- atua como **registro complementar interpretativo**, aprovado para garantir consistência entre:
  - tela pública (`Ver resultado`)
  - snapshot persistido
  - PDF final

## 2. Hierarquia documental

A hierarquia continua sendo:

1. **SSOT_PROFILEDNA_v2_0.md** = fonte absoluta de verdade
2. **DOCUMENTO PROGRAMA TESTE PERFIL DNA.pdf** = documento complementar
3. **Este addendum (`ADDENDUM_Seções_2_e_6_do_Relatório_Final_ProfileDNA.md`)** = registro complementar interpretativo, subordinado ao SSOT e ao Documento Programa

Se houver conflito entre este addendum e o SSOT, **o SSOT prevalece**.

Se houver conflito entre este addendum e o Documento Programa, **o SSOT prevalece** e este addendum deverá ser revisado.

## 3. Escopo congelado

Este addendum se aplica somente a:

- `backend/templates/reports/sections/section_sintese_executiva.html`
- `backend/templates/reports/sections/section_pdi.html`
- payloads que alimentam essas seções
- validação visual entre tela, snapshot e PDF dessas duas seções

Não se aplica a outras seções do relatório.

---

# 4. Seção 2 — Síntese Executiva

## 4.1 Regra documental base

A Seção 2 continua sendo oficialmente a:

- **“Síntese Executiva (1 parágrafo)”**

O parágrafo da Síntese Executiva deve seguir a lógica documental já aprovada:

- citar **Top 3**
- incluir **1 risco típico**
- incluir **1 recomendação objetiva**

## 4.2 Regra editorial congelada de apresentação

Fica formalmente aprovado que a Seção 2 seja apresentada no relatório final com a seguinte estrutura:

1. **Título da seção**
2. **1 parágrafo obrigatório**
3. **3 cards auxiliares oficiais**
   - **Destaques principais**
   - **Ampliação de potencial**
   - **Pontos de atenção**

## 4.3 Natureza dos 3 cards auxiliares

Os 3 cards auxiliares:

- são **permitidos**
- são **oficiais**
- são considerados **camada auxiliar de leitura**
- **não substituem** o parágrafo obrigatório
- **não alteram** a regra documental da seção
- existem para melhorar clareza, escaneabilidade e valor consultivo do relatório

## 4.4 Regra de precedência visual da Seção 2

A ordem oficial da Seção 2 fica congelada assim:

1. parágrafo executivo
2. cards auxiliares

Os cards **não podem aparecer acima do parágrafo**.

## 4.5 Contrato mínimo esperado da Seção 2

Payload mínimo esperado:

- `sintese_executiva.texto`
- `sintese_executiva.destaques_principais`
- `sintese_executiva.ampliacao_potencial`
- `sintese_executiva.pontos_atencao`

Payload analítico enriquecido permitido:

- `sintese_executiva.risco_tipico`
- `sintese_executiva.recomendacao_objetiva`
- aliases legados compatíveis (`strengths`, `growth`, `attention`), desde que não quebrem o contrato principal

## 4.6 Regra de conteúdo congelada do parágrafo da Seção 2

O parágrafo obrigatório deve consolidar, em texto contínuo:

- forças centrais do **Top 3**
- **risco típico** da dimensão alta principal
- **recomendação objetiva** derivada da dimensão baixa prioritária

O parágrafo é o elemento obrigatório da seção.

## 4.7 Regra dos cards da Seção 2

### Card 1 — Destaques principais
Deve representar a leitura de forças predominantes.

### Card 2 — Ampliação de potencial
Pode continuar exibindo leitura ampliada de potencial, inclusive usando Top 5 quando o backend canônico assim entregar.

### Card 3 — Pontos de atenção
Deve representar prioridades de atenção e desenvolvimento.

## 4.8 Regra de compatibilidade

A presença desses 3 cards é considerada **compatível** com o Documento Programa, desde que:

- o parágrafo obrigatório permaneça presente
- a lógica principal da seção continue centrada no resumo executivo
- os cards sejam interpretados como camada auxiliar e não como redefinição estrutural da seção

---

# 5. Seção 6 — Competências-Chave para PDI

## 5.1 Regra documental base

A Seção 6 continua sendo oficialmente:

- **Competências-Chave para PDI**

A regra de conteúdo documental permanece:

- **Potencializar = Top 3**
- **Desenvolver = Bottom 3**
- competência média adicional de equilíbrio = **opcional**

## 5.2 Regra editorial congelada de apresentação

Fica formalmente aprovado que a Seção 6 seja apresentada com a seguinte estrutura:

1. **Título da seção**
2. **Texto introdutório curto**
3. **Bloco: Competências para potencializar**
4. **Itens derivados do Top 3**
5. **Bloco: Competências para desenvolver**
6. **Itens derivados do Bottom 3**

## 5.3 Regra dos blocos da Seção 6

### Competências para potencializar
Representa forças já presentes que devem ser consolidadas e usadas com mais intencionalidade.

### Competências para desenvolver
Representa prioridades práticas de desenvolvimento derivadas das menores recorrências do perfil.

## 5.4 Competência média adicional

A competência média adicional de equilíbrio:

- continua **permitida**
- continua **opcional**
- sua ausência **não caracteriza falha**
- só deve ser incluída se houver regra canônica específica de backend para isso

## 5.5 Contrato mínimo esperado por item do PDI

Cada item da Seção 6 deve poder sustentar:

- `titulo`
- `descricao`
- `eixo`
- `letter`
- `dimensao_nome`
- `area`
- `acoes`
- `comportamentos_alvo`
- `rotina_pratica`
- `indicador_evolucao`

Campos analíticos adicionais são permitidos, desde que não quebrem este contrato mínimo.

## 5.6 Regra de apresentação por item

Cada competência pode ser exibida com:

- título editorial da competência
- eixo (`potencializar` ou `desenvolver`)
- dimensão de origem
- área
- descrição curta
- ações recomendadas
- comportamentos-alvo
- rotina prática
- indicador de evolução

Essa estrutura consultiva fica **formalmente aprovada**.

---

# 6. Naming editorial congelado da Seção 6

## 6.1 Princípio

Fica formalmente aprovado o uso de **títulos editoriais de competência** derivados do mapa sugerido do Documento Programa, desde que respeitem a dimensão de origem.

## 6.2 Exemplos aprovados

Exemplos aprovados como compatíveis com o Documento Programa:

- **Maturidade organizacional / gestão de hierarquia**
- **Orientação a processos / conformidade**
- **Liderança e direcionamento**
- **Autogestão emocional / equilíbrio**
- **Resiliência e persistência (com flexibilidade)**
- **Orientação a resultados / carreira**
- **Disciplina e consistência**
- **Comunicação e influência**
- **Gestão de conflitos / assertividade**
- **Empatia e relacionamento**
- **Gestão de energia e ritmo de execução**
- **Adaptabilidade e inovação**
- **Presença e posicionamento**
- **Planejamento e gestão de prioridades**
- **Qualidade e atenção a detalhes**
- **Gestão de risco e autonomia decisória**
- **Pensamento analítico / tomada de decisão baseada em dados**

## 6.3 Regra de uso

O naming editorial:

- deve continuar semanticamente aderente à dimensão original
- não pode contradizer o mapa sugerido do Documento Programa
- não pode inventar nova taxonomia de competências fora da lógica do produto
- pode ser usado para tornar o relatório mais consultivo, claro e executivo

---

# 7. Regra de paridade obrigatória

As Seções 2 e 6 devem permanecer em **paridade estrutural e semântica** entre:

- tela pública (`/resultado`)
- snapshot persistido
- PDF final

Diferença visual aceitável:

- pequenas variações naturais de quebra de linha, paginação ou densidade tipográfica entre HTML e PDF

Diferença não aceitável:

- perda de campos
- cards vazios em um canal e completos em outro
- parágrafo completo em um canal e reduzido em outro
- PDI consultivo em um canal e fallback pobre em outro

---

# 8. Regra de manutenção

Qualquer mudança futura que altere:

- a estrutura da Seção 2
- a estrutura da Seção 6
- a natureza dos cards auxiliares da Seção 2
- a lógica Potencializar / Desenvolver da Seção 6
- o naming editorial canônico do PDI

deve gerar:

1. nova decisão explícita
2. atualização deste addendum
3. novo audit de paridade tela x snapshot x PDF

---

# 9. Estado congelado aprovado

Fica congelado como estado aprovado:

## Seção 2
- 1 parágrafo obrigatório
- 3 cards auxiliares oficiais
- cards abaixo do parágrafo
- cards como camada auxiliar de leitura

## Seção 6
- estrutura consultiva congelada
- Potencializar = Top 3
- Desenvolver = Bottom 3
- competência média adicional = opcional
- naming editorial atual = aprovado como compatível com o Documento Programa

---

# 10. Observação final

Este addendum existe para **formalizar uma decisão já validada no fluxo real**, preservando:

- aderência ao SSOT
- aderência ao Documento Programa
- consistência entre tela e PDF
- congelamento auditável da apresentação final
