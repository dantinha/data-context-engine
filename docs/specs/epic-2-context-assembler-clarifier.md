# Épico 2: Context Assembler, Hybrid Retriever & Semantic Clarifier — Especificação Funcional e de Negócio

- **Projeto:** Data Context Engine
- **Épico:** 2 de 4
- **Status:** Em Revisão Técnica
- **Responsável:** Engenharia de Contexto & IA

---

## 1. Visão de Negócio e Objetivo do Épico

O **Context Engine** é o diferencial competitivo do projeto. Enquanto soluções ingênuas despejam todo o schema bruto do banco no prompt (gerando alto custo em tokens, confusão entre tabelas `raw`/`staging`/`marts` e alucinação de métricas), este motor opera em 3 estágios inteligentes:

1. **Desambiguação Semântica Ativa (*Semantic Clarifier*):** Antes de chamar o LLM para gerar SQL, analisa a pergunta do usuário contra os `ambiguity_groups` da camada semântica. Se houver ambiguidade (e o usuário ainda não tiver escolhido uma métrica), interrompe o fluxo e devolve as opções claras de negócio.
2. **Recuperação Híbrida + Expansão de Grafo (*Hybrid Retriever*):** Busca apenas as tabelas, colunas, métricas do glossário e exemplos *Few-Shot* relevantes para a pergunta, expandindo pelas chaves de relacionamento (`relationships`) para garantir que tabelas de ligação necessárias para `JOIN` nunca fiquem de fora.
3. **Montagem Otimizada para Prefix Caching e Economia de Tokens (*Context Assembler*):** Comprime o DDL das tabelas selecionadas, ordena os blocos do prompt colocando conteúdo estático no prefixo (para 80-90% de *cache hit* na API do LLM) e gera o relatório detalhado de **Inspeção de Contexto (Nível 2)**.

---

## 2. Especificação dos 5 Níveis de Contexto (`ContextLevel`)

Para que o benchmark (Épico 3) e a interface (Épico 4) possam comparar objetivamente o ganho de cada técnica de Context Engineering, o montador deve suportar 5 níveis explícitos:

| Nível | Nome | O que entra no Prompt enviado ao LLM | Objetivo no Benchmark |
| :--- | :--- | :--- | :--- |
| **`L0`** | **Zero Context (Baseline)** | Apenas a pergunta do usuário e a instrução de dialeto DuckDB. | Medir o que o LLM chuta sem conhecer o banco. |
| **`L1`** | **Raw Full Schema Dump** | `CREATE TABLE` bruto de **todas** as tabelas do banco (`raw` + `staging` + `marts`), sem descrições e sem filtro. | Simular a abordagem ingênua tradicional (alto custo de tokens e ruído das camadas `raw`/`staging`). |
| **`L2`** | **Marts Schema + dbt Docs** | DDL comprimido das tabelas `marts` + descrições de tabelas, colunas e enums vindos de `metadata/schema.yml`. | Medir o impacto isolado de uma boa modelagem e documentação `dbt`. |
| **`L3`** | **L2 + Camada Semântica** | L2 + Métricas Canônicas (`canonical_sql`, filtros obrigatórios), Regras de Negócio (RN-01 a RN-07) e Joins Proibidos de `metadata/semantic_layer.yml`. | Medir o salto de acurácia ao ensinar as definições financeiras e operacionais da empresa. |
| **`L4`** | **Full Context Engine (Pruned + Few-Shot)** | **Seleção cirúrgica via Retriever** (apenas as tabelas `marts` relevantes + vizinhas de grafo) + DDL comprimido + Métricas recuperadas + Top-K **Exemplos Few-Shot** (incluindo Playbooks salvos) + Ordem estrita de Prefix Caching. | Provar que o motor completo atinge a maior acurácia consumindo **menos tokens** que L1, L2 e L3. |

---

## 3. Regras de Negócio e Funcionamento Interno

### 3.1 Motor de Desambiguação Semântica (`SemanticClarifier`)
- **Entrada:** `question: str`, `selected_metric_id: str | None = None`.
- **Comportamento:**
  1. Se `selected_metric_id` já foi informado pelo usuário (ou se a pergunta já especifica inequivocamente a métrica, ex: *"qual o ticket médio..."* ou *"qual o LTV..."*), o clarificador aprova a pergunta (`needs_clarification = False`) e anexa a métrica correspondente.
  2. Se `selected_metric_id` for `None` e a pergunta acionar um `ambiguity_group` do `semantic_layer.yml` (ex: pergunta contém *"melhores clientes"*, *"clientes top"*, *"qual o faturamento"* sem especificar bruto/líquido/entregue), retorna `ClarificationRequest`:
     - `needs_clarification = True`
     - `ambiguous_term`: termo detectado
     - `message`: explicação amigável ao usuário
     - `options`: lista de `ClarificationOption(metric_id, label, description, formula_preview)`

### 3.2 Recuperador Híbrido e Expansão de Grafo (`HybridRetriever`)
- **Fontes Indexadas:**
  1. `tables`: tabelas do schema `marts` (nome, descrição, nomes e descrições de colunas, valores de exemplo).
  2. `metrics`: métricas canônicas e regras de negócio do `semantic_layer.yml`.
  3. `examples`: biblioteca de pares `pergunta -> SQL` validados (`metadata/few_shot_examples.yml` + `data/playbooks/saved_playbooks.json`).
- **Algoritmo de Busca Híbrida (CPU-friendly, sem exigir GPU):**
  - Combina pontuação léxica (BM25 / TF-IDF de n-gramas de palavras e caracteres, excelente para nomes exatos de colunas e termos em português) com similaridade semântica vetorial (usando embeddings locais leves ou decomposição SVD/LSA em CPU + armazenamento em disco/LanceDB).
- **Expansão pelo Grafo Relacional:**
  - Se a pergunta recupera `dim_products` (ex: categoria de produto) e `dim_customers` (ex: estado do cliente), o retriever percorre o grafo de `relationships` em `semantic_layer.yml` e inclui automaticamente a tabela fato conectora (`fct_order_items` / `fct_orders`), garantindo que o LLM tenha o caminho completo do `JOIN`.

### 3.3 Compressão de DDL e Orçamento de Tokens (`ContextAssembler`)
- **Compressão Semântica de DDL:**
  - Converte metadados verbosos para formato Markdown tabular ultracompacto:
    ```markdown
    ### Table: marts.fct_orders (Grain: 1 row per order_id)
    Description: Consolidated orders fact table with pre-aggregated item and payment totals.
    Columns:
    - order_id (VARCHAR, PK): Unique order identifier
    - customer_unique_id (VARCHAR, FK -> marts.dim_customers.customer_unique_id): True unique customer ID (use for counting customers/LTV)
    - order_status (VARCHAR, enum=['delivered','shipped','canceled','unavailable','invoiced','processing']): Current status
    - total_payment_value (DECIMAL): Total paid for the order
    ```
- **Estrutura de Prefix Caching:**
  - Todo prompt montado é dividido em 2 blocos explícitos:
    1. `static_prefix`: Instruções do sistema + Regras globais do dialeto DuckDB + Schema/Glossário base estático do nível.
    2. `dynamic_suffix`: Tabelas/Métricas específicas recuperadas + Exemplos Few-Shot + Pergunta do usuário.
- **Alocador de Orçamento (`token_budget`):**
  - Limite padrão configurável (ex: `max_context_tokens = 2500` para L4). Calcula a contagem estimada de tokens e registra quantos tokens o schema bruto completo (`L1`) consumiria vs quantos tokens o contexto montado consumiu (`token_savings_pct`).

---

## 4. Contrato de Inspeção de Contexto Nível 2 (`ContextInspectionReport`)

Toda execução do `ContextAssembler` produz um objeto estruturado `AssembledContext` contendo o prompt final e o `inspection: ContextInspectionReport` (que abastece o painel lateral do Streamlit no Épico 4):

```python
class RetrievedExampleInfo(BaseModel):
    id: str
    title: str
    source: Literal["static_few_shot", "saved_playbook"]
    similarity_score: float
    resolved_metric_id: str | None = None

class SelectedTableInfo(BaseModel):
    table_name: str
    selection_type: Literal["direct_match", "graph_bridge", "baseline_dump"]
    reason: str          # "Direct match on 'categoria'" ou "Graph bridge between dim_products and dim_customers"
    relevance_score: float
    columns_included: list[str]

class SelectedMetricInfo(BaseModel):
    metric_id: str
    name: str
    description: str
    base_table: str
    canonical_sql: str
    filters_required: list[str]
    was_clarified_by_user: bool

class ContextInspectionReport(BaseModel):
    level: ContextLevel
    token_budget: int
    raw_full_schema_tokens: int
    assembled_context_tokens: int
    token_savings_pct: float
    prefix_cacheable_tokens: int
    prefix_cacheable_pct: float
    selected_tables: list[SelectedTableInfo]
    selected_metrics: list[SelectedMetricInfo]
    retrieved_examples_count: int
    retrieved_examples: list[RetrievedExampleInfo]
    business_rules_injected: list[str]
    forbidden_joins_warned: list[str]

class AssembledContext(BaseModel):
    static_prefix: str
    dynamic_suffix: str
    full_prompt: str
    inspection: ContextInspectionReport
```

---

## 5. Requisitos Funcionais (RF)

- **RF-2.1 (Indexação Automática):** O indexador deve ler o DuckDB (`data/warehouse.duckdb`), `metadata/schema.yml`, `metadata/semantic_layer.yml`, `metadata/few_shot_examples.yml` e `data/playbooks/saved_playbooks.json`, construindo o índice local em menos de 5 segundos.
- **RF-2.2 (Hot-Reload de Playbooks):** Quando um novo Playbook for salvo pelo usuário (Épico 4), o índice de exemplos Few-Shot deve incorporá-lo imediatamente sem precisar reiniciar a aplicação.
- **RF-2.3 (Detecção de Ambiguidade):** O `SemanticClarifier` deve identificar perguntas ambíguas mapeadas nos 4 grupos de ambiguidade principais e retornar `ClarificationRequest` antes de qualquer chamada ao LLM.
- **RF-2.4 (Geração dos 5 Níveis L0–L4):** O `ContextAssembler` deve montar deterministicamente os prompts de `L0`, `L1`, `L2`, `L3` e `L4`.
- **RF-2.5 (Economia Comprovada de Tokens em L4):** Em perguntas típicas que envolvem 1 a 3 tabelas, o nível `L4` deve reduzir o consumo de tokens de schema em pelo menos **50%** em relação ao `L1` (schema bruto completo), mantendo 100% das tabelas necessárias para a query de referência.

---

## 6. Critérios de Aceite (Definition of Done)

- [ ] **CA-2.1:** Perguntar *"Quem são os nossos melhores clientes?"* sem `selected_metric_id` retorna `needs_clarification=True` com as 3 opções de negócio do glossário.
- [ ] **CA-2.2:** Passar `selected_metric_id="customer_ltv"` resolve a ambiguidade e injeta a definição canônica de LTV no prompt montado.
- [ ] **CA-2.3:** Para uma pergunta que cruza *categoria de produto* com *estado do cliente*, o retriever em `L4` seleciona `dim_products`, `dim_customers` e inclui automaticamente a tabela de ligação (`fct_order_items` / `fct_orders`) via expansão de grafo.
- [ ] **CA-2.4:** O `ContextInspectionReport` retorna os cálculos exatos de `raw_full_schema_tokens`, `assembled_context_tokens` e `token_savings_pct > 50%` nos testes de `L4`.
