# ADDENDUM — Seção 5 do Relatório Final ProfileDNA

## 1. Finalidade deste addendum

Este addendum tem como objetivo **formalizar e congelar** a regra de apresentação da:

- **Seção 5 — Oportunidades de Desenvolvimento (Bottom 3)**

Este documento:

- **não altera** o SSOT principal
- **não substitui** o Documento Programa
- **não altera** regras de motor, scoring, ranking ou bibliotecas
- apenas registra a **interpretação editorial e de apresentação aprovada** para garantir consistência entre:
  - tela pública (`Ver resultado`)
  - snapshot persistido
  - PDF final

Este addendum deve ser entendido como **registro complementar interpretativo**, subordinado ao SSOT e compatível com o Documento Programa.

## 2. Hierarquia documental

A hierarquia continua sendo:

1. **SSOT_PROFILEDNA_v2_0.md** = fonte absoluta de verdade
2. **DOCUMENTO PROGRAMA TESTE PERFIL DNA.pdf** = documento complementar
3. **ADDENDUM_Seções_2_e_6_do_Relatório_Final_ProfileDNA.md** = registro complementar interpretativo
4. **ADDENDUM_Seção_5_do_Relatório_Final_ProfileDNA.md** = registro complementar interpretativo

Se houver conflito entre este addendum e o SSOT, **o SSOT prevalece**.

Se houver conflito entre este addendum e o Documento Programa, **o SSOT prevalece** e este addendum deverá ser revisado.

## 3. Escopo congelado

Este addendum se aplica somente a:

- `backend/templates/reports/sections/section_bottom3.html`
- payloads que alimentam a Seção 5
- validação visual entre tela, snapshot e PDF da Seção 5

Não se aplica às demais seções do relatório.

## 4. Seção 5 — Regra documental congelada

A Seção 5 continua sendo oficialmente:

- **Oportunidades de Desenvolvimento (Bottom 3)**

Sua função é apresentar, de forma objetiva e resumida, as 3 dimensões de menor recorrência do perfil.

## 5. Regra editorial congelada de apresentação

A Seção 5 deve permanecer com estrutura simples, contendo para cada item:

- letra/dimensão
- nome da dimensão
- área
- texto interpretativo curto

A Seção 5 deve permanecer como **camada objetiva de identificação** das menores recorrências do perfil, sem converter-se em bloco consultivo expandido.

## 6. Regra de não duplicação com a Seção 6

Fica formalmente congelado que a Seção 5:

- **não deve** conter tratamento consultivo expandido
- **não deve** conter ações recomendadas
- **não deve** conter comportamentos-alvo
- **não deve** conter rotina prática
- **não deve** conter métrica/indicador de acompanhamento

Esses elementos pertencem à:

- **Seção 6 — Competências-Chave para PDI**

Regra funcional congelada:

- **Seção 5 identifica**
- **Seção 6 desenvolve**

A Seção 5 não deve competir estruturalmente com a Seção 6.

## 7. Contrato mínimo esperado da Seção 5

A Seção 5 deve ser sustentada pelo contrato mínimo:

- `ranking.bottom3`
- `interpretations[letter].name`
- `interpretations[letter].area`
- `interpretations[letter].text`

Qualquer enriquecimento além disso deve ser considerado indevido se gerar sobreposição com a Seção 6.

## 8. Regra de paridade obrigatória

A Seção 5 deve permanecer em **paridade estrutural e semântica** entre:

- tela pública (`/resultado`)
- snapshot persistido
- PDF final

Diferença aceitável:

- pequenas variações de quebra de linha e paginação

Diferença não aceitável:

- Seção 5 simples em um canal e consultiva em outro
- duplicação da lógica da Seção 6 dentro da Seção 5

## 9. Estado congelado aprovado

Fica congelado como estado aprovado:

- Seção 5 simples
- Bottom 3 apenas
- leitura curta por item
- sem enriquecimento consultivo
- sem duplicação com a Seção 6
- sem competição estrutural com a Seção 6

## 10. Observação final

Este addendum formaliza a decisão de que a Seção 5 deve permanecer objetiva, enquanto a Seção 6 concentra o desdobramento consultivo/PDI do desenvolvimento.

A intenção é preservar:

- aderência ao SSOT
- aderência ao Documento Programa
- consistência entre tela, snapshot e PDF
- não duplicação funcional entre Seção 5 e Seção 6
- congelamento auditável da apresentação final
