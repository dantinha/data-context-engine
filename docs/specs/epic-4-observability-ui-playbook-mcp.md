# Épico 4: Observability UI (Anti-AI Design), Playbook Loop & MCP Server — Especificação Funcional e de Negócio

- **Projeto:** Data Context Engine
- **Épico:** 4 de 4
- **Status:** Em Revisão Técnica
- **Responsável:** Produto, Frontend Engineering & Integrações MCP

---

## 1. Visão de Negócio e Objetivo do Épico

O Épico 4 transforma toda a inteligência construída nos Épicos 1, 2 e 3 em duas interfaces tangíveis de produto:
1. **A Aplicação Analítica de Observabilidade (Streamlit com *Anti-AI Design*):** A vitrine onde o analista de negócios e o avaliador técnico interagem com o motor. Em vez de uma caixa de chat genérica, apresenta um **Workbench de Engenharia de Contexto** com desambiguação guiada, execução instantânea, **Painel de Inspeção de Contexto (Nível 2)** e o ciclo de **Playbooks Recorrentes**.
2. **O Servidor MCP (*Model Context Protocol*):** Permite plugar o Data Context Engine diretamente em qualquer agente de mercado (Claude Desktop, VS Code, Cursor), expondo a camada semântica, o montador de contexto e a execução SQL segura como ferramentas padronizadas.

---

## 2. Diretrizes de Design e Experiência (*Anti-AI Design Rules*)

Seguindo estritamente a skill `anti-ai-design`:
- **Proibido:** Gradientes neon roxo/rosa, caixas de chat vazias no meio da tela, excesso de emojis infantis, cards gigantes com 2 linhas de texto.
- **Paleta Sóbria (Linear / Supabase Style):**
  - Superfície base: `#09090b` (Zinc-950), Cards elevados: `#18181b` (Zinc-900), Bordas hairline: `1px solid #27272a` (Zinc-800).
  - Cor de destaque única (Accent): `#4f46e5` (Indigo-600) para ações primárias e `#10b981` (Emerald-500) para indicadores de economia de tokens / validação de segurança.
- **Tipografia & Densidade:**
  - Fonte de interface: Inter / System Sans compacta (`13px`–`14px`).
  - Fonte de código e métricas numéricas: `JetBrains Mono` / monospace com `font-variant-numeric: tabular-nums`.

---

## 3. Fluxos Funcionais da Aplicação (`app/streamlit_app.py`)

A interface possui uma barra lateral enxuta (seletor de Nível de Contexto `L0`–`L4`, seletor de Provedor `Replay Cache / Gemini API`, e atalhos para **Playbooks Salvos**) e 3 abas principais no canvas central:

### 3.1 Aba 1: Workbench Analítico & Inspeção de Contexto (Tela Principal)

#### Passo 1: Entrada ou Seleção de Playbook
- Barra de pergunta superior compacta com seletor rápido de perguntas de exemplo (incluindo perguntas ambíguas e perguntas com armadilhas do Olist) + botão `Executar Consulta`.

#### Passo 2: Alerta de Desambiguação Semântica (Opção B - Human-in-the-Loop)
- Se o `SemanticClarifier` detectar ambiguidade (ex: usuário perguntou *"Quem são os nossos 10 melhores clientes?"*), a tela **não** gera SQL às cegas.
- Exibe um card de decisão estruturado:
  - Mensagem: *"O termo 'melhores clientes' possui 3 definições oficiais no Glossário de Negócios. Selecione o critério desejado:"*
  - Botões/Chips interativos para cada `ClarificationOption` (mostrando nome da métrica, descrição executiva e prévia da regra SQL).
  - Ao clicar na opção desejada, a execução prossegue imediatamente com a métrica vinculada (`was_clarified_by_user = True`).

#### Passo 3: Split-View de Entrega (Resultado de Negócio | Inspeção de Contexto Nível 2)
A tela se divide em duas colunas (proporção `60%` esquerda / `40%` direita):

- **Coluna Esquerda (60%) — Resultado de Negócio & Ação de Playbook:**
  1. **Resumo Executivo:** Explicação concisa da resposta e da regra aplicada.
  2. **Tabela de Dados Densa:** DataFrame formatado com números alinhados à direita e contagens de linhas.
  3. **Visualização Gráfica Automática:** Gráfico de barras/linhas limpo quando o resultado contiver 1 dimensão e 1 métrica numérica.
  4. **SQL Auditado:** Bloco de código SQL expansível/visível com badge de segurança `AST Verified (Read-Only) • DuckDB XX ms`.
  5. **Botão `⭐ Salvar como Processo Recorrente (Playbook)`:**
     - Abre um formulário inline rápido (Título do Playbook + Tags).
     - Ao confirmar, salva em `data/playbooks/saved_playbooks.json` e dispara o hot-reload do `HybridRetriever` (RF-2.2), transformando a análise validada em um novo exemplo *Few-Shot* para consultas futuras!

- **Coluna Direita (40%) — Painel de Inspeção de Contexto (Nível 2):**
  1. **Economia de Tokens & Prefix Cache:**
     - Cards comparativos: `Schema Bruto (L1): X.XXX tokens` → `Contexto Montado (L4): XXX tokens` (`-XX% de redução`) + `Prefix Cacheable: XX%`.
     - Barra de progresso visual do orçamento de tokens.
  2. **Tabelas Selecionadas pelo Retriever:**
     - Lista cada tabela incluída (ex: `marts.fct_orders`, `marts.dim_customers`), o **motivo da seleção** (*Direct Semantic Match* vs *Relational Graph Bridge*) e o score de relevância.
  3. **Métrica Canônica & Guardrails Vinculados:**
     - Exibe a definição YAML injetada (ex: `customer_ltv`, filtros obrigatórios `order_status = 'delivered'`) e os avisos de joins proibidos (`forbidden_joins_warned`).
  4. **Exemplos Few-Shot Recuperados:**
     - Lista os títulos dos exemplos similares ou Playbooks que guiaram a geração.
  5. **Visualizador do Prompt Real:**
     - Aba/expander mostrando exatamente o bloco `[STATIC PREFIX]` e o bloco `[DYNAMIC SUFFIX]` enviados ao modelo.

### 3.2 Aba 2: Comparador Side-by-Side de Níveis (`L1 Naive` vs `L4 Context Engine`)
- Permite que o usuário veja, para a mesma pergunta, o que acontece quando se usa o `L1` (schema bruto sem contexto de negócio — onde o modelo frequentemente esquece de filtrar cancelados ou usa `customer_id` errado) lado a lado com o `L4` (onde o Context Engine acerta a regra de negócio gastando muito menos tokens).

### 3.3 Aba 3: Painel do Benchmark & Arquitetura (`L0` a `L4`)
- Exibe a tabela consolidada do benchmark (`results/benchmark_summary.json`), o gráfico de evolução da **Execution Accuracy × Consumo de Tokens** de `L0` a `L4`, e a exploração detalhada pergunta por pergunta do Gold Set.

---

## 4. Ciclo de Persistência de Playbooks (`PlaybookStore`)

- Arquivo de persistência: `data/playbooks/saved_playbooks.json`.
- Modelo `SavedPlaybook`:
  - `id: str`
  - `title: str`
  - `question: str`
  - `resolved_metric_id: str | None`
  - `sql_query: str`
  - `tables_used: list[str]` (extraídas deterministicamente da AST via `sqlglot`)
  - `created_at: str`
  - `tags: list[str]`
- Operações: `list_playbooks(tag: str | None = None)`, `save_playbook(...)`, `delete_playbook(id)`.
- **Prevenção de Re-Clarificação no Clique do Atalho:** Quando o usuário clica em um Playbook salvo na barra lateral, a UI passa simultaneamente `(question=playbook.question, selected_metric_id=playbook.resolved_metric_id)` para o `SemanticClarifier`, pulando o prompt de desambiguação e executando imediatamente.
- **Desambiguação na Indexação Few-Shot:** Sempre que `save_playbook()` é chamado, o `PlaybookStore` persiste no JSON e notifica o `HybridRetriever`. Se `resolved_metric_id` existir, o texto indexado como exemplo *Few-Shot* é enriquecido com `f"{playbook.question} [Critério: {resolved_metric_id}]"` para não conflitar com outras métricas do mesmo grupo de ambiguidade.

---

## 5. Especificação do Servidor MCP (`src/dce/mcp_server.py`)

Implementado com o SDK oficial `mcp` (`FastMCP`), expondo 7 ferramentas padronizadas via protocolo stdio/SSE:

1. **`clarify_and_assemble_context(question: str, selected_metric_id: str | None = None, level: str = "L4")`**:
   - Executa o `SemanticClarifier`. Se precisar de clarificação, retorna `needs_clarification=True`, `agent_directive="STOP_AND_ASK_USER"` e as `options`. Se estiver claro, retorna `static_prefix`, `dynamic_suffix` e o `ContextInspectionReport`.
2. **`search_warehouse_context(query: str, top_k_per_category: int = 3)`**:
   - Busca híbrida particionada retornando `{"tables": [...], "metrics": [...], "examples": [...], "forbidden_joins": [...]}`.
3. **`get_canonical_metric(metric_id: str)`**:
   - Retorna a definição oficial, SQL canônico, `base_table` e filtros obrigatórios de uma métrica (ou lista todas as métricas disponíveis se `metric_id="*"` ou não encontrado).
4. **`describe_mart_table(table_name: str, sample_rows: int = 3)`**:
   - Aceita nomes com ou sem prefixo `marts.`. Retorna documentação `dbt`, colunas, tipos, grão, relacionamentos e amostra segura de linhas.
5. **`list_saved_playbooks(tag: str | None = None)`**:
   - Lista todos os processos analíticos recorrentes salvos pelos usuários.
6. **`save_verified_playbook(title: str, question: str, sql_query: str, resolved_metric_id: str | None = None, tags: list[str] | None = None)`**:
   - Valida a query no `SafeSQLExecutor`, persiste no `PlaybookStore` e atualiza o índice *Few-Shot* em tempo real.
7. **`execute_safe_sql(sql_query: str, max_rows: int = 100)`**:
   - Valida a query no `SQLGuardrail` (`sqlglot` AST) e executa em modo somente-leitura no DuckDB com `max_rows=100` (protegendo a janela de contexto do cliente MCP), retornando os dados, `tables_referenced`, `governance_warnings` e `remediation_hint` em caso de erro.

---

## 6. Requisitos Funcionais (RF)

- **RF-4.1 (Gerenciador de Playbooks com Retroalimentação Few-Shot):** Salvar um Playbook deve persistir em disco e torná-lo imediatamente recuperável pelo `HybridRetriever` em consultas `L4`.
- **RF-4.2 (Fluxo de Clarificação Interativa na UI):** A interface Streamlit deve renderizar os chips/botões de `ClarificationOption` quando `needs_clarification=True` e reexecutar com a métrica escolhida.
- **RF-4.3 (Painel de Inspeção de Contexto Nível 2):** A UI deve exibir métricas de economia de tokens, tabelas selecionadas com justificativa, métrica vinculada e o prompt particionado em prefixo estático + sufixo dinâmico.
- **RF-4.4 (Servidor MCP Funcional):** Todas as 6 tools MCP devem responder com JSON/texto estruturado e possuir testes unitários/integração diretos.

---

## 7. Critérios de Aceite (Definition of Done)

- [ ] **CA-4.1:** Salvar uma análise pelo `PlaybookStore` adiciona o item em `data/playbooks/saved_playbooks.json` e uma nova busca no `HybridRetriever` por pergunta similar recupera esse Playbook como exemplo *Few-Shot*.
- [ ] **CA-4.2:** As 6 tools do servidor MCP executam e passam nos testes automatizados em `tests/test_mcp_server.py`.
- [ ] **CA-4.3:** A aplicação Streamlit (`app/streamlit_app.py`) inicializa sem erros, respeita a paleta e tipografia *Anti-AI Design*, e permite testar os fluxos de Desambiguação, Inspeção Nível 2, Playbooks e visualização do Benchmark 100% offline (usando o Replay Cache) ou online (com Gemini API Key).
