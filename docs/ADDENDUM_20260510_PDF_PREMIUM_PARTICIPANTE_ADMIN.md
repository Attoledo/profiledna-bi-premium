# ADDENDUM_20260510_PDF_PREMIUM_PARTICIPANTE_ADMIN.md

## 1. Objetivo

Este addendum formaliza a criação de um **segundo PDF administrativo** no módulo **Resultado Individual · Gestão** do ProfileDNA.

A partir deste addendum, o sistema passa a suportar dois artefatos distintos de relatório individual no painel administrativo:

1. **Baixar PDF do Participante**
   - Relatório técnico, denso e interno
   - Voltado à leitura especializada da equipe gestora / operação do sistema
   - Mantido como já existe hoje

2. **Baixar PDF Teste de Perfil - Profile DNA**
   - Novo relatório premium
   - Voltado à apresentação para cliente / participante / gestor final
   - Linguagem simples, elegante, consultiva e comercialmente valorizada
   - Sem exposição de siglas, letras técnicas ou códigos das dimensões

Este addendum **não substitui** o relatório técnico atual.  
Ele adiciona um **novo produto de saída**, paralelo, reutilizando a mesma base oficial de dados e respeitando integralmente o motor determinístico já definido no SSOT.

---

## 2. Decisão formal de produto

### 2.1 Dois PDFs distintos no admin

Na área **Resultado Individual · Gestão**, o sistema deve disponibilizar **dois botões distintos**:

- **Baixar PDF do Participante**
- **Baixar PDF Teste de Perfil - Profile DNA**

O primeiro permanece como relatório técnico interno.  
O segundo passa a ser o relatório premium de apresentação.

### 2.2 Participante não acessa mais o resultado diretamente

Fica formalizado que o participante **não terá mais acesso direto** ao resultado final nem ao PDF após a conclusão do teste.

Após o envio final, a experiência do participante deve encerrar em uma tela institucional de agradecimento, informando que o resultado será posteriormente apresentado pelo gestor responsável.

O acesso ao resultado individual passa a ser exclusivamente administrativo.

### 2.3 O gestor é o ponto de distribuição

O novo PDF premium será gerado no painel administrativo e ficará disponível para uso do gestor / avaliador / equipe interna.

Nesta etapa, o fluxo oficial é:

- o admin acessa o resultado individual
- o admin escolhe qual PDF baixar
- o admin decide como compartilhar externamente

### 2.4 Acesso do PDF premium

O PDF premium é **administrativo** nesta fase.

Ele será baixado apenas pelo admin/gestor autenticado, dentro do painel.

O participante não terá rota pública para:
- visualizar o resultado
- baixar PDF
- acessar versão premium

### 2.5 Estratégia de geração do PDF premium

O PDF premium será implementado com estratégia de **geração lazy com congelamento do artefato**:

- no primeiro download, o sistema gera o PDF premium
- o artefato premium gerado é persistido
- nos downloads seguintes, o sistema reutiliza o mesmo arquivo já salvo

Com isso, o PDF premium passa a funcionar como documento final congelado daquele attempt, preservando consistência, rastreabilidade e repetibilidade.

---

## 3. Regra de não regressão

A implementação do novo PDF premium deve obedecer às seguintes restrições obrigatórias:

- não alterar o motor de scoring
- não alterar contagens, faixas, top3, top5, bottom3 ou critérios de desempate
- não alterar o relatório técnico já existente
- não alterar a rota técnica já existente
- não alterar o snapshot técnico atual
- não alterar o fluxo administrativo já validado
- não reabrir o acesso do participante ao resultado
- não introduzir lógica paralela de cálculo fora do motor oficial

O PDF premium deve ser apenas uma **nova camada de apresentação**, construída sobre os mesmos dados oficiais já calculados pelo sistema.

---

## 4. Fonte de dados do PDF premium

O PDF premium deve usar exclusivamente dados oficiais já consolidados no resultado do participante, incluindo, quando aplicável:

- identificação do participante
- cargo
- empresa
- data da avaliação
- scores oficiais das dimensões
- bands oficiais
- top3
- top5
- bottom3
- síntese executiva derivada do resultado oficial
- competências para PDI derivadas do resultado oficial
- demais interpretações oficiais disponíveis no pipeline atual

É proibido recalcular manualmente o resultado dentro:
- do template premium
- do renderer premium
- da rota administrativa premium
- de qualquer helper visual do premium

---

## 5. Posicionamento do PDF premium

O **PDF Teste de Perfil - Profile DNA** é definido como um material de:

- alto valor percebido
- linguagem acessível
- leitura leiga
- uso corporativo elegante
- orientação consultiva
- apresentação profissional
- valor comercial

O cliente final deve perceber este material como um relatório premium de consultoria comportamental, e não como uma saída técnica de sistema.

---

## 6. Diretriz central de linguagem

O PDF premium deve usar escrita:

- humanizada
- profissional
- clara
- consultiva
- elegante
- acessível para público não técnico

Evitar:

- linguagem robótica
- excesso de tecnicismo
- siglas não explicadas
- jargão psicológico excessivo
- visual de planilha ou laudo frio

---

## 7. Regra obrigatória de nomenclatura das dimensões

O PDF premium **não pode exibir letras, siglas técnicas ou códigos internos** das dimensões no corpo principal do relatório.

### 7.1 Proibido no corpo principal

Não exibir como título principal ou como eixo central de leitura:

- A — Atitude Analítica
- B — Organização
- E — Necessidade de se Comunicar
- K — ...
- SCORE 5
- FAIXA MID
- HIGH / LOW / MID
- códigos equivalentes

### 7.2 Obrigatório no corpo principal

Exibir sempre nomes descritivos, amigáveis e autoexplicativos, por exemplo:

- **Atitude Analítica**
- **Necessidade de se Comunicar**
- **Esforço no Trabalho**
- **Organização**
- **Liderança**
- **Adaptabilidade**
- **Persistência**
- **Sociabilidade**
- **Gestão Emocional**
- **Ritmo de Execução**

Se necessário, o sistema pode usar um mapa de tradução entre a camada técnica interna e a camada descritiva do relatório premium.

### 7.3 Regra de interpretação

A tradução do nome da dimensão não altera:

- score
- faixa
- ranking
- top/bottom
- interpretação base

Ela altera somente a forma de apresentação ao leitor final.

---

## 8. Estrutura obrigatória do PDF premium

O novo PDF premium deve seguir a estrutura abaixo.

### 8.1 Capa

A capa deve conter:

- nome do colaborador
- cargo
- empresa
- data da avaliação
- logo da DNA Agência
- estética premium
- visual corporativo moderno
- paleta institucional da DNA Agência

### 8.2 Resumo Executivo

Deve apresentar um texto consultivo e acessível explicando:

- perfil predominante
- forma de trabalhar
- tomada de decisão
- comunicação
- reação sob pressão
- funcionamento em equipe
- talentos centrais
- pontos de atenção

### 8.3 Gráficos

Os gráficos devem ser simples, intuitivos e visualmente limpos.

Preferências aceitas:

- barras horizontais
- pizza / donut
- indicadores visuais simples
- escalas visuais modernas

Evitar gráficos excessivamente técnicos ou poluídos.

### 8.4 Análise completa das dimensões

O PDF premium deve detalhar todas as dimensões avaliadas.

Para cada dimensão, incluir:

- nome descritivo da competência
- nível identificado
- explicação detalhada
- impactos positivos
- possíveis dificuldades
- reflexos no ambiente de trabalho
- orientação para o gestor
- tendência comportamental no dia a dia

### 8.5 Análise comportamental profunda

Adicionar leitura ampliada, sempre derivada dos dados oficiais, cobrindo temas como:

- estilo de liderança
- proatividade
- comunicação
- inteligência emocional
- capacidade analítica
- organização
- adaptabilidade
- gestão de conflitos
- trabalho em equipe
- foco em resultado
- ritmo de execução
- reação à pressão
- necessidade de reconhecimento
- perfil motivacional

### 8.6 PDI — Plano de Desenvolvimento Individual

O PDF premium deve encerrar com um PDI robusto, consultivo e utilizável pelo gestor.

Para cada item do PDI, incluir:

- competência a desenvolver
- objetivo do desenvolvimento
- impacto esperado
- ações práticas
- sugestões de treinamento
- acompanhamento do gestor
- metas comportamentais
- prazo recomendado
- indicadores de evolução

### 8.7 Encerramento institucional

O fechamento deve reforçar:

- caráter de desenvolvimento
- uso responsável do relatório
- apoio à evolução profissional
- posicionamento premium da DNA Agência

---

## 9. Implementação técnica formalizada

### 9.1 Separação obrigatória do premium em relação ao técnico

O PDF premium será implementado de forma separada do relatório técnico atual.

Diretriz arquitetural formal:

- manter o renderer técnico atual
- manter o template técnico atual
- manter a rota técnica atual
- criar renderer premium próprio
- criar template premium próprio
- criar seções premium próprias
- criar rota administrativa própria para exportação premium
- criar persistência separada do artefato premium

### 9.2 Persistência separada do premium

O PDF premium **não utilizará o mesmo snapshot nem o mesmo pdf_path do relatório técnico**.

O premium deverá possuir persistência separada, de modo que:

- o técnico continue íntegro
- o premium seja gerado e congelado de forma independente
- cada artefato tenha sua própria rastreabilidade

A modelagem física final poderá ser definida na implementação técnica, mas a separação lógica é obrigatória.

### 9.3 Geração lazy com congelamento

O fluxo técnico oficial do premium será:

1. admin solicita o PDF premium
2. sistema verifica se já existe artefato premium persistido para o attempt
3. se existir:
   - retorna o arquivo premium já salvo
4. se não existir:
   - monta o payload premium a partir dos dados oficiais
   - renderiza o HTML premium
   - gera o PDF premium
   - persiste o snapshot/artefato premium
   - retorna o arquivo gerado

### 9.4 Mesma base oficial de dados

Embora tenha renderer, template, rota e persistência próprios, o PDF premium deve usar a mesma base oficial de resultado já consolidada no sistema.

### 9.5 Compatibilidade com PDF

O layout do premium deve ser construído com foco explícito em geração estável via HTML + CSS + WeasyPrint, respeitando:

- A4
- quebras de página inteligentes
- preservação visual
- legibilidade
- alinhamento de gráficos
- ausência de sobreposição
- ausência de blocos quebrados visualmente

---

## 10. Escopo exato desta implementação

Esta implementação cobre:

- existência formal do segundo PDF
- manutenção do PDF técnico atual
- novo botão premium no admin
- rota administrativa separada para o premium
- renderer premium separado
- template premium separado
- seções premium separadas
- persistência separada do artefato premium
- geração lazy com congelamento
- acesso exclusivamente administrativo ao premium
- proibição de acesso direto do participante ao resultado
- uso de linguagem leiga e consultiva no premium
- ocultação de letras/siglas técnicas no corpo principal do premium

Esta implementação **não cobre nesta etapa**:

- envio automático do premium por e-mail
- liberação de rota pública de download
- compartilhamento automático ao participante
- reabertura de resultado ao participante
- alteração do motor de scoring
- substituição do relatório técnico atual

---

## 11. Regra de versionamento

Qualquer mudança futura em:

- estrutura do premium
- conteúdo consultivo base
- política de exibição ao participante
- mapas de tradução de dimensões
- persistência do snapshot premium
- política de envio externo

deve gerar novo addendum versionado.

---

## 12. Status

**Status:** APROVADO PARA IMPLEMENTAÇÃO TÉCNICA  
**Data:** 2026-05-10  
**Escopo:** Relatório premium administrativo paralelo ao relatório técnico  
**Prioridade:** Alta  
**Impacto esperado:** aumento de valor percebido do produto, melhoria comercial e melhoria da experiência de apresentação do resultado ao cliente final
