# Épico 3: Execution Guardrails, Text-to-SQL Agent & Reproducible Benchmark — Especificação Funcional e de Negócio

- **Projeto:** Data Context Engine
- **Épico:** 3 de 4
- **Status:** Em Revisão Técnica
- **Responsável:** Engenharia de IA, Segurança & Avaliação

---

## 1. Visão de Negócio e Objetivo do Épico

Conectar um LLM a um banco de dados corporativo exige duas garantias inegociáveis:
1. **Segurança Operacional Absoluta (*Guardrails*):** O modelo jamais pode executar comandos destrutivos (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `COPY`, `ATTACH`), ler arquivos arbitrários do sistema operacional (`read_csv_auto('/etc/passwd')`) ou travar o banco com um produto cartesiano infinito.
2. **Prova Científica de Valor (*Benchmark Reprodutível*):** Para comprovar empiricamente que a Engenharia de Contexto funciona, precisamos de um benchmark objetivo baseado em **Execution Accuracy** (comparação matemática entre o resultado da SQL gerada e o resultado da SQL gabarito) ao longo dos 5 níveis de contexto (`L0` a `L4`).

---

## 2. Regras de Segurança e Guardrails (`SQLGuardrail`)

Toda consulta SQL gerada pelo agente (ou enviada via MCP) passa obrigatoriamente por um pipeline de validação baseado em **Abstract Syntax Tree (AST)** usando `sqlglot` (dialeto `duckdb`) **antes** de tocar no banco:

| Regra | Código | Verificação AST (`sqlglot 30.30.0`) | Comportamento Esperado |
| :--- | :--- | :--- | :--- |
| **Statement Único** | **SEC-01** | `sqlglot.parse(sql, read="duckdb")` deve conter exatamente 1 árvore sintática não-nula. | Bloqueia injeção de múltiplos comandos (`SELECT 1; DROP TABLE ...`). |
| **Somente Leitura (`SELECT` / `SetOperation`)** | **SEC-02** | Desembrulha `exp.Subquery` externo e exige raiz `isinstance(root, (exp.Select, exp.SetOperation))` (cobrindo CTEs `WITH` e `UNION`/`INTERSECT`/`EXCEPT`). Qualquer nó `Insert`, `Update`, `Delete`, `Drop`, `Create`, `Alter`, `Command`, `Grant`, `Attach`, `Detach`, `Copy`, `Pragma`, `Set`, `Load`, `Install`, `Kill`, `Transaction`, `Commit`, `Rollback` na árvore é proibido. | Rejeita imediatamente com `SQLSecurityViolationError`. |
| **Bloqueio de Funções de Sistema/Arquivo e Replacement Scans** | **SEC-03** | Bloqueia nós `exp.ReadCSV`, `exp.ReadParquet` e qualquer `exp.Func` cujo `(node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()` esteja em `{'read_csv', 'read_csv_auto', 'read_parquet', 'read_json', 'read_json_auto', 'glob', 'parquet_scan', 'sqlite_scan', 'postgres_scan'}`. Também bloqueia qualquer `exp.Table` cujo `table.name` contenha `/`, `\` ou extensões de arquivo (`.csv`, `.parquet`, `.json`, `.db`, `.duckdb`, `.sqlite`, `.txt`), barrando *Replacement Scans* do DuckDB. | Impede exfiltração de arquivos locais do servidor (Local File Inclusion via SQL). |
| **Restrição de Schema & Extração de Tabelas Reais** | **SEC-04** | Coleta `cte_names = {c.alias_or_name.lower() for c in parsed.find_all(exp.CTE)}` e extrai apenas tabelas físicas (`t.name.lower() not in cte_names`). Emite `governance_warnings` se consultar `raw.*` ou `staging.*`. | Garante conformidade com RN-07 sem falso positivo em CTEs. |
| **Injeção de `LIMIT` de Segurança** | **SEC-05** | Se a query raiz não possuir cláusula `LIMIT` (ou se `LIMIT > max_rows`), aplica `.limit(max_rows)` (padrão `1000` na UI/Benchmark e `100` no MCP). | Previne estouro de memória na aplicação. |

---

## 3. Sandbox de Execução DuckDB (`SafeSQLExecutor`)

- Abre conexão com **Defesa em Profundidade**: `duckdb.connect(db_path, read_only=True, config={"enable_external_access": False})` (segunda barreira nativa em C++ contra acesso externo ao filesystem/rede).
- Mede o tempo exato de execução em milissegundos (`execution_time_ms`).
- Converte o resultado para `pandas.DataFrame` (ou lista de dicionários serializáveis) e retorna `SQLExecutionResult`:
  - `success: bool`
  - `sql_executed: str`
  - `tables_referenced: list[str]`
  - `rows: list[dict[str, Any]]`
  - `columns: list[str]`
  - `row_count: int`
  - `truncated: bool`
  - `execution_time_ms: float`
  - `ast_verified: bool`
  - `limit_applied: int | None`
  - `governance_warnings: list[str]`
  - `error_message: str | None`
  - `remediation_hint: str | None`
  - `security_violation: bool`

---

## 4. Agente Pergunta → SQL (`SQLAgent`) e Cache Determinístico

### 4.1 Arquitetura do Agente
- Suporta múltiplos provedores gratuitos configuráveis via variável de ambiente:
  1. **Gemini API Free Tier** (`gemini-2.5-flash` / `gemini-2.0-flash` via `google-genai` ou `pydantic-ai`).
  2. **Groq Free Tier** / **Ollama Local** (opcional).
  3. **Deterministic Replay Cache (`results/cache/`)**:
     - Lookup em 2 níveis para máxima resiliência:
       - Chave Primária (Exact Prompt): `sha256(f"{cache_version}|{model_name}|{context_level}|{retry_attempt}|{normalized_prompt}")` (com quebras de linha `\r\n` normalizadas para `\n`).
       - Chave de Fallback para `--replay`: `sha256(f"{cache_version}|{model_name}|{context_level}|{retry_attempt}|{normalized_question}|{selected_metric_id or ''}")`.
     - **Isolamento do Benchmark (`include_user_playbooks=False`):** Durante a execução do `BenchmarkRunner`, o `HybridRetriever` consulta exclusivamente `metadata/few_shot_examples.yml` (ignorando `saved_playbooks.json` criados na UI), garantindo determinismo e zero vazamento de dados.
     - Permite que qualquer pessoa que clonar o repositório no GitHub rode `bench --replay` ou interaja com as perguntas de demonstração na UI **100% offline, instantaneamente e sem precisar configurar chave de API**.

### 4.2 Loop de Autocorreção (`Self-Correction Loop`)
- **Tentativa 0 (Single-Shot):** O agente recebe o `AssembledContext` (gerado no Épico 2) e produz `GeneratedSQLResponse(sql_query, explanation, metrics_used, tables_used)`.
- **Validação e Execução:** O `SafeSQLExecutor` valida a AST e executa no DuckDB.
- **Tentativas 1..N (Self-Correction, padrão `max_retries=2`):**
  - Se a execução falhar por erro de sintaxe ou coluna inexistente no DuckDB (e **não** for violação de segurança maliciosa), o agente recebe o erro exato devolvido pelo DuckDB (`Binder Error: Referenced column "x" not found in FROM clause...`) e gera a query corrigida.
  - O resultado final registra tanto o sucesso na 1ª tentativa (`first_attempt_success`) quanto o sucesso após autocorreção (`final_success` e `retries_used`).

---

## 5. Suíte de Benchmark Reprodutível (`BenchmarkRunner`)

### 5.1 Gold Question Set (`benchmarks/gold_questions.yml`)
- Conjunto curado de **30 a 60 perguntas de negócio em português** sobre o Olist, cobrindo:
  - Dificuldades: `easy` (agregações simples em 1 tabela), `medium` (joins entre 2-3 tabelas + filtros de negócio), `hard` (coortes de recompra, LTV por estado, taxa de atraso por categoria, participação percentual com window functions, prevenção de fan-out).
  - Tags de armadilhas exercitadas: `RN-01` (`customer_unique_id`), `RN-02` (`order_status`), `RN-03` (`fanout_prevention`), `RN-04` (`price_vs_payment`), `RN-05` (`delivery_delay`), `RN-06` (`category_translation`), `RN-07` (`schema_layer`).
- Cada item possui: `id`, `question`, `difficulty`, `trap_tags`, `resolved_metric_id` (quando aplicável), `gold_sql` (testada contra `marts`).

### 5.2 Comparador Matemático de Result Sets (`compare_results`)
Duas queries SQL diferentes podem produzir exatamente a mesma resposta de negócio. Portanto, a avaliação **NÃO** compara strings SQL, e sim os dados retornados (**Execution Accuracy**):
1. Executa `gold_sql` e `generated_sql` no mesmo banco `warehouse.duckdb` com o mesmo `max_rows=1000`.
2. Converte colunas numéricas e `decimal.Decimal` para `float64` (tolerância `atol=1e-2, rtol=1e-2, equal_nan=True`) e normaliza datas/timestamps para string ISO `YYYY-MM-DD`.
3. Ignora os nomes dados aos aliases das colunas e encontra o pareamento bijetivo entre colunas equivalentes caso o LLM tenha permutado a ordem das colunas no `SELECT`.
4. Ordena canonicamente as linhas (arredondando floats em `round(2)` para estabilidade de desempate e tratando `None`/`NaN` com `na_position="last"`).

### 5.3 Verificador Anti-Vazamento (`test_no_leakage`)
- Um teste automatizado verifica que nenhuma pergunta de `benchmarks/gold_questions.yml` existe de forma idêntica (ou com similaridade textual de Jaccard/cosseno > 0.85) dentro de `metadata/few_shot_examples.yml`, garantindo honestidade científica no ganho do nível `L4`.

### 5.4 Artefatos Gerados pelo Benchmark
Rodar o benchmark gera automaticamente em `results/`:
- `results/benchmark_summary.json` (métricas completas por nível `L0`..`L4`).
- `results/benchmark_report.md` (tabela Markdown formatada pronta para o `README.md`).
- `results/accuracy_by_level.svg` (gráfico visual limpo comparando Execution Accuracy × Consumo de Tokens de L0 a L4).

---

## 6. Requisitos Funcionais (RF)

- **RF-3.1 (Validador AST `sqlglot`):** Implementar `SQLGuardrail` bloqueando 100% das instruções DDL/DML, múltiplos statements e funções de leitura de arquivo do DuckDB.
- **RF-3.2 (Executor Read-Only):** Implementar `SafeSQLExecutor` abrindo o DuckDB em modo `read_only=True` com medição de latência e limite seguro de linhas.
- **RF-3.3 (Agente com Replay Cache + Gemini API):** Implementar `SQLAgent` capaz de operar via Gemini API Free Tier e via Replay Cache determinístico offline.
- **RF-3.4 (Comparador de Execution Accuracy):** Implementar `ResultComparator` tolerante a aliases de coluna e arredondamento de ponto flutuante.
- **RF-3.5 (Runner do Benchmark L0–L4):** Executar todas as perguntas do Gold Set nos níveis `L0`, `L1`, `L2`, `L3` e `L4`, reportando Execution Accuracy (Single-Shot e com Self-Correction `N=2`), média de tokens de contexto e economia percentual.

---

## 7. Critérios de Aceite (Definition of Done)

- [ ] **CA-3.1:** Testes de segurança em `tests/test_guardrails.py` comprovam que `DROP TABLE`, `DELETE`, `UPDATE`, `INSERT`, `COPY`, `read_csv_auto` e queries com `;` são bloqueadas antes da execução.
- [ ] **CA-3.2:** Todas as `gold_sql` de `benchmarks/gold_questions.yml` executam sem erro no DuckDB e retornam resultados não-vazios.
- [ ] **CA-3.3:** O teste anti-vazamento comprova que o conjunto `few_shot_examples.yml` é disjunto do `gold_questions.yml`.
- [ ] **CA-3.4:** O comando de benchmark em modo `--replay` roda 100% offline em menos de 15 segundos, gerando `results/benchmark_report.md` e `results/accuracy_by_level.svg` com progressão monotônica clara de acurácia de `L0` até `L4`.
