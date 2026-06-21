# docsIA — Base Documental da DANA

## Finalidade

A pasta `docsIA` é a base documental complementar da DANA, assistente analítica do ProfileDNA.

Seu objetivo é armazenar documentos técnicos e conceituais que podem enriquecer a interpretação consultiva da DANA no painel administrativo, especialmente em interações via chat com gestores e administradores.

Esta base documental é complementar ao sistema e não substitui:

- o SSOT do produto;
- o motor determinístico de scoring;
- o relatório final oficial;
- os resultados oficiais consolidados do sistema;
- o BI oficial e os comparativos oficiais do sistema.

## Regra de precedência

A hierarquia obrigatória é:

1. `SSOT_PROFILEDNA_v2_0.md`
2. addendums oficiais do projeto, incluindo `ADDENDUM_20260403_DANA_AI_ANALYST.md`
3. resultados oficiais consolidados do sistema
4. base documental `docsIA` como apoio consultivo complementar

Se houver qualquer tensão entre um documento desta pasta e o resultado oficial do produto, prevalece sempre o resultado oficial do sistema.

## Uso permitido pela DANA

A DANA pode usar os documentos desta pasta para:

- enriquecer interpretação consultiva;
- apoiar explicações conceituais;
- sugerir hipóteses de leitura;
- aprofundar perguntas de desenvolvimento;
- apoiar recomendações práticas ao gestor;
- trazer referências complementares em linguagem acessível e tecnicamente responsável.

## Uso proibido pela DANA

A DANA não pode usar os documentos desta pasta para:

- recalcular scoring;
- alterar Top 3, Top 5 ou Bottom 3;
- alterar `computed_results`;
- alterar `report_snapshots`;
- alterar o relatório final oficial;
- alterar o BI oficial;
- criar resultados paralelos;
- sobrescrever regras oficiais do produto;
- inventar dimensões, scores, rankings ou bibliotecas oficiais.

## Estrutura oficial desta pasta

A base documental deve ser organizada nas seguintes subpastas:

- `BIG_FIVE/`
- `DISC/`
- `MBTI/`
- `PDI/`
- `PERSONALIDADES_PERFIS/`
- `TESTES_COMPORTAMENTAIS/`

Cada subpasta deve conter documentos correlatos ao tema indicado pelo nome da pasta.

## Regra de catalogação

Todo documento desta base deve ser catalogado no arquivo:

- `backend/ai_analyst/docsIA/manifest.json`

Documento físico sem entrada válida no `manifest.json` não deve ser tratado como documento oficial da base consultiva da DANA.

## Campos obrigatórios do manifesto

Cada documento catalogado no manifesto deve conter, no mínimo:

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

## Regras de naming e rastreabilidade

### Nome do arquivo físico

Os arquivos devem usar nomes estáveis, legíveis e sem ambiguidade operacional.

Preferir:

- minúsculas ou padrão estável definido pelo time;
- separação por underscore;
- indicação de versão quando aplicável.

Exemplo:

- `guia_pdci_gestores_v1.pdf`
- `fundamentos_disc_aplicado_v2.pdf`

### `document_id`

O `document_id` deve ser único e estável.

Formato recomendado:

- `<tema>_<sequencial>`
- `<tema>_<slug_curto>_<versao>`

Exemplos:

- `pdci_001`
- `disc_fundamentos_v1`
- `mbti_aplicacoes_gestao_v2`

## Regras de status

Os status permitidos no manifesto são:

- `approved`
- `draft`
- `archived`

### approved

Documento aprovado para uso consultivo da DANA.

### draft

Documento ainda não liberado para uso oficial.

### archived

Documento mantido para histórico, mas não elegível para uso ativo da DANA.

## Regra de hash

Todo documento deve ter hash SHA-256 registrado no manifesto.

O hash é obrigatório para:

- rastreabilidade;
- auditoria;
- validação de integridade;
- controle de versões;
- prevenção de divergência entre catálogo e arquivo físico.

## Regra sobre conteúdo permitido

Podem existir nesta base documentos relacionados a:

- Big Five;
- DISC;
- MBTI;
- PDI;
- perfis e personalidades;
- testes comportamentais;
- desenvolvimento humano;
- liderança;
- feedback;
- gestão de desempenho;
- comportamento organizacional;
- materiais técnicos correlatos aprovados pela DNA Agência.

## Regra sobre conteúdo não permitido

Não devem entrar nesta base:

- documentos sem origem clara;
- documentos sem aprovação interna;
- materiais conflitantes com o SSOT do produto;
- materiais que tentem redefinir scoring ou regras do ProfileDNA;
- arquivos duplicados sem versionamento claro;
- documentos sem catalogação no manifesto.

## Relação com a arquitetura do módulo DANA

Esta pasta é parte da arquitetura oficial complementar do módulo:

- `backend/ai_analyst/docsIA`

O pipeline futuro de ingestão deverá validar esta base antes de qualquer uso em recuperação documental.

Etapas futuras esperadas:

1. validação do `manifest.json`
2. validação de existência dos arquivos
3. validação de hash
4. extração de texto
5. chunking
6. indexação
7. recuperação controlada no chat da DANA

## Regra de segurança e privacidade

Os documentos desta pasta não autorizam envio irrestrito de dados ao modelo externo.

O uso pela DANA deve continuar respeitando:

- não envio de PII desnecessária;
- não envio de respostas A/B brutas;
- priorização de contexto consolidado e controlado;
- rastreabilidade do que foi usado na resposta.

## Regra final

A `docsIA` é uma base de apoio consultivo especializada.

Ela existe para ampliar a qualidade analítica da DANA sem comprometer:

- a verdade oficial do produto;
- a auditabilidade;
- a rastreabilidade;
- a segurança;
- a imutabilidade dos resultados oficiais.
