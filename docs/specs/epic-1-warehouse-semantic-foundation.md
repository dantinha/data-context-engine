# Épico 1: Warehouse & Semantic Foundation — Especificação Funcional e de Negócio

- **Projeto:** Data Context Engine
- **Épico:** 1 de 4
- **Status:** Em Revisão Técnica
- **Responsável:** Produto & Engenharia de Dados

---

## 1. Visão de Negócio e Objetivo do Épico

Construir a fundação de dados analíticos e metadados de negócio sobre o dataset real brasileiro **Olist E-Commerce** no **DuckDB**. 

Em um ambiente corporativo real, o banco de dados possui tabelas brutas (`raw`), tabelas intermediárias (`staging`) e tabelas analíticas consolidadas (`marts`), além de armadilhas naturais de modelagem que levam LLMs comuns ao erro (como duplicar valores em joins 1:N ou confundir o ID de um pedido com o ID único do cliente).

O objetivo deste épico é:
1. Disponibilizar um warehouse local rápido, determinístico e zero-custo em DuckDB (funcionando tanto com uma amostra versionada de ~2.000 pedidos para CI/Demo rápida quanto com o dataset completo de ~100.000 pedidos).
2. Modelar as camadas `raw`, `staging` e `marts` documentadas em formato compatível com `dbt` (`schema.yml`).
3. Formalizar a **Camada Semântica (`semantic_layer.yml`)** contendo o Glossário de Negócios, as Métricas Canônicas, os **Grupos de Ambiguidade** (para guiar o usuário na Opção B de clarificação) e o Grafo de Relacionamentos.

---

## 2. Regras de Negócio e "Armadilhas Naturais" do Domínio Olist

O motor de contexto será posto à prova contra 7 armadilhas reais do domínio de e-commerce da Olist. A camada semântica e a documentação `dbt` devem explicitar essas regras:

| Código | Armadilha Natural no Olist | Regra de Negócio Oficial (Gabarito Canônico) |
| :--- | :--- | :--- |
| **RN-01** | **`customer_id` vs `customer_unique_id`** | Na Olist, cada pedido gera um novo `customer_id`. Para contar clientes distintos, calcular retenção, recompra ou LTV por cliente, **DEVE-SE** usar obrigatoriamente `customer_unique_id` da dimensão `dim_customers`. |
| **RN-02** | **Status de Pedido em Receita (`order_status`)** | Pedidos com status `canceled` ou `unavailable` **NÃO** compõem receita realizada (GMV / Faturamento Líquido). Apenas pedidos `delivered` (ou para GMV faturado: `delivered`, `shipped`, `invoiced`) entram nas métricas financeiras oficiais. |
| **RN-03** | **Fan-out em Joins (`order_items` × `order_payments`)** | Um pedido pode ter múltiplos itens (`fct_order_items`) e múltiplas parcelas/meios de pagamento (`fct_order_payments`). Fazer `JOIN` direto entre itens e pagamentos sem pré-agregar por `order_id` multiplica indevidamente os valores financeiros. |
| **RN-04** | **Preço do Produto vs Valor Total (`price` vs `freight_value` vs `payment_value`)** | Em `fct_order_items`, `price` é o valor unitário do item sem frete, `freight_value` é o frete daquele item, e a soma `price + freight_value` compõe o valor total dos itens. Já `payment_value` em `fct_order_payments` é o valor efetivamente cobrado (incluindo juros de parcelamento ou vouchers). |
| **RN-05** | **Atraso de Entrega (`delivery_delay`)** | Um pedido é considerado **atrasado** exclusivamente quando `order_status = 'delivered'` e `CAST(order_delivered_customer_date AS DATE) > CAST(order_estimated_delivery_date AS DATE)`. `delivery_days` e `delay_days` são `NULL` quando `order_status != 'delivered'`. Para pedidos entregues no prazo, `delay_days = 0` e `is_delayed = FALSE`; a métrica `avg_delay_days` filtra `WHERE is_delayed = TRUE`. |
| **RN-06** | **Categorias em Português vs Inglês** | Em `marts.dim_products`, produtos possuem `category_name_pt` em português (ex: `beleza_saude`, fallback `'nao_informado'`) e tradução em `category_name_en` (fallback `'not_informed'`). |
| **RN-07** | **Poluição de Camadas (`raw` e `staging` vs `marts`)** | O warehouse contém schemas `raw` e `staging` com colunas cruas e sem tratamento. Agentes e usuários analíticos **DEVEM** consultar exclusivamente o schema `marts`. |

---

## 3. Arquitetura de Dados (Schemas e Tabelas)

O banco DuckDB (`data/warehouse.duckdb`) terá 3 schemas:

### 3.1 Schema `raw` (Tabelas Originais Olist)
- `raw.olist_orders_dataset`
- `raw.olist_order_items_dataset`
- `raw.olist_order_payments_dataset`
- `raw.olist_order_reviews_dataset`
- `raw.olist_customers_dataset`
- `raw.olist_sellers_dataset`
- `raw.olist_products_dataset`
- `raw.product_category_name_translation`
- `raw.olist_geolocation_dataset` (agregado por prefixo de CEP para evitar duplicatas cartesianas)

### 3.2 Schema `staging` (Limpeza, Tipagem e Padronização)
- `staging.stg_orders`: padronização de timestamps, flags booleanas basais.
- `staging.stg_order_items`: tipagem decimal de `price` e `freight_value`.
- `staging.stg_order_payments`: agregação e tipagem de pagamentos.
- `staging.stg_order_reviews`: notas de avaliação (`review_score` 1 a 5).
- `staging.stg_customers`, `staging.stg_sellers`, `staging.stg_products`.

### 3.3 Schema `marts` (Camada Oficial de Consumo Analítico)
1. **`marts.fct_orders`** (Grão: 1 linha por `order_id`):
   - Chaves: `order_id` (PK), `customer_id` (FK operacional), `customer_unique_id` (FK para `dim_customers`).
   - Atributos: `order_status`, `order_purchase_timestamp`, `order_purchase_date`, `order_approved_at`, `order_delivered_customer_date`, `order_estimated_delivery_date`.
   - Métricas pré-calculadas no pedido (evita fan-out RN-03 e deduplica múltiplos reviews por pedido): `items_count`, `total_items_price`, `total_freight_value`, `total_order_value` (`price + freight`), `total_payment_value`, `payment_installments_max`, `primary_payment_type`, `review_score` (`AVG(review_score)` por pedido, `NULL` quando sem avaliação), `is_delivered`, `is_canceled`, `is_delayed`, `delivery_days`, `delay_days`.
2. **`marts.fct_order_items`** (Grão: 1 linha por `order_id` + `order_item_id`):
   - Chaves: `order_id`, `order_item_id`, `product_id` (FK), `seller_id` (FK), `customer_unique_id` (FK).
   - Atributos e fatos: `order_status`, `is_delivered`, `order_purchase_timestamp`, `order_purchase_date`, `price`, `freight_value`, `total_item_value`, `review_score`.
3. **`marts.fct_order_payments`** (Grão: 1 linha por `order_id` + `payment_sequential`):
   - Chaves: `order_id`, `payment_sequential`.
   - Atributos e fatos: `order_status`, `order_purchase_date`, `payment_type` (`credit_card`, `boleto`, `voucher`, `debit_card`), `payment_installments`, `payment_value`.
4. **`marts.dim_customers`** (Grão: 1 linha por `customer_unique_id`):
   - Chaves: `customer_unique_id` (PK).
   - Atributos: `customer_city` e `customer_state` (UF extraída do pedido mais recente via `ARG_MAX`), `first_order_date`, `last_order_date`, `total_orders`, `delivered_orders`, `lifetime_value` (soma de `total_payment_value` em pedidos entregues), `avg_ticket` (`lifetime_value / delivered_orders` quando `delivered_orders > 0`, senão `0`), `is_repeat_customer` (`delivered_orders > 1`).
5. **`marts.dim_products`** (Grão: 1 linha por `product_id`):
   - Chaves: `product_id` (PK).
   - Atributos: `category_name_pt` (fallback `'nao_informado'`), `category_name_en` (fallback `'not_informed'`), `product_weight_g`, `product_length_cm`, `product_height_cm`, `product_width_cm`.
6. **`marts.dim_sellers`** (Grão: 1 linha por `seller_id`):
   - Chaves: `seller_id` (PK).
   - Atributos: `seller_city`, `seller_state` (UF), `total_orders_sold`, `total_items_sold`, `total_revenue_generated` (soma de `price` em pedidos `delivered`), `avg_review_score`.

---

## 4. Contrato da Camada Semântica (`semantic_layer.yml`)

O arquivo `metadata/semantic_layer.yml` define 3 estruturas obrigatórias:

1. **`metrics` (Métricas Canônicas)**:
   - `id`: identificador único (ex: `net_revenue`, `gross_merchandise_value`, `average_order_value`, `customer_ltv`, `delivery_delay_rate`, `repeat_purchase_rate`, `avg_review_score`).
   - `name`: nome amigável em português.
   - `description`: definição executiva clara.
   - `canonical_sql`: expressão SQL exata usando tabelas `marts`.
   - `base_table`: tabela principal recomendada.
   - `filters_required`: filtros obrigatórios (ex: `order_status = 'delivered'`).
   - `synonyms`: lista de termos que os usuários costumam digitar.
2. **`ambiguity_groups` (Gatilhos de Desambiguação Ativa - Opção B)**:
   - Mapeia termos vagos ou amplos para 2 a 4 `metrics` candidatas.
   - Exemplos obrigatórios:
     - Termo `"melhor cliente"` / `"top clientes"` / `"cliente mais valioso"` → Opções: (1) Maior LTV Acumulado (`customer_ltv`), (2) Maior Número de Pedidos Entregues (`customer_order_count`), (3) Maior Ticket Médio por Pedido (`customer_avg_ticket`).
     - Termo `"faturamento"` / `"receita"` / `"vendas"` → Opções: (1) Receita Realizada de Pedidos Entregues (`net_revenue`), (2) GMV Bruto Total incluindo enviados (`gross_merchandise_value`), (3) Receita exclusiva de Produto sem Frete (`product_only_revenue`).
     - Termo `"melhor vendedor"` / `"top sellers"` → Opções: (1) Maior Receita de Itens Vendidos (`seller_revenue`), (2) Maior Volume de Unidades Vendidas (`seller_units_sold`), (3) Melhor Nota Média de Avaliação (`seller_avg_review`).
     - Termo `"entrega"` / `"performance logística"` → Opções: (1) Taxa de Pedidos com Atraso (`delivery_delay_rate`), (2) Tempo Médio de Entrega em Dias (`avg_delivery_days`), (3) Dias Médios de Atraso (`avg_delay_days`).
3. **`relationships` (Grafo de Joins Permitidos e Proibidos)**:
   - Arestas seguras (`allowed_joins`):
     - `marts.fct_orders` ↔ `marts.dim_customers` via `customer_unique_id` (N:1).
     - `marts.fct_order_items` ↔ `marts.fct_orders` via `order_id` (N:1 — nunca somar totais do pedido após este join sem deduplicar).
     - `marts.fct_order_items` ↔ `marts.dim_products` via `product_id` (N:1).
     - `marts.fct_order_items` ↔ `marts.dim_sellers` via `seller_id` (N:1).
     - `marts.fct_order_items` ↔ `marts.dim_customers` via `customer_unique_id` (N:1 — ponte de 1 salto entre itens/produtos/sellers e demografia do cliente).
     - `marts.fct_order_payments` ↔ `marts.fct_orders` via `order_id` (N:1).
   - Joins proibidos (`forbidden_joins`):
     - `marts.fct_order_items` ↔ `marts.fct_order_payments` direto por `order_id` (RN-03: multiplica itens por parcelas).
     - `marts.fct_orders` ↔ `marts.dim_customers` por `customer_id` (RN-01: usar sempre `customer_unique_id`).
   - Definições exatas do Grupo 2 (Receita):
     - `net_revenue`: `SUM(total_payment_value)` em `marts.fct_orders` onde `order_status = 'delivered'`.
     - `gross_merchandise_value` (GMV): `SUM(total_order_value)` em `marts.fct_orders` onde `order_status IN ('delivered', 'shipped', 'invoiced')`.
     - `product_only_revenue`: `SUM(total_items_price)` em `marts.fct_orders` onde `order_status = 'delivered'`.

---

## 5. Requisitos Funcionais (RF)

- **RF-1.1 (Gerador de Amostra Determinística):** O sistema deve fornecer um gerador/carregador determinístico em `data/sample/` com ~2.000 pedidos realistas da Olist (preservando todas as 7 armadilhas naturais: clientes com múltiplos `customer_id`, pedidos cancelados, pagamentos parcelados em múltiplas linhas, itens múltiplos, atrasos de entrega, categorias diversas e notas de review) para permitir execução 100% offline no CI e no modo demo rápido sem exigir credenciais do Kaggle.
- **RF-1.2 (Download Opcional Kaggle):** Deve existir um comando CLI para baixar o dataset completo de ~100k pedidos via Kaggle caso o usuário deseje rodar sobre a base integral.
- **RF-1.3 (Pipeline de Transformação Warehouse):** Um construtor de warehouse (`src/dce/warehouse/builder.py` + modelos SQL/dbt) deve construir todas as tabelas dos schemas `raw`, `staging` e `marts` no DuckDB local em menos de 10 segundos para o sample (e < 60s para o full).
- **RF-1.4 (Catálogo de Metadados dbt):** O arquivo `metadata/schema.yml` deve documentar cada tabela e coluna do schema `marts` com descrições ricas, tipos, chaves primárias/estrangeiras e exemplos de valores枚举 (enums).
- **RF-1.5 (Validador de Integridade do Warehouse):** Testes automatizados que validem unicidade de PKs, ausência de nulos em chaves críticas e confirmação matemática de que `fct_orders` não sofre de fan-out quando comparada a `fct_order_items` e `fct_order_payments`.

---

## 6. Critérios de Aceite (Definition of Done)

- [ ] **CA-1.1:** Executar o build do warehouse cria `data/warehouse.duckdb` contendo os schemas `raw`, `staging` e `marts` populados sem erros.
- [ ] **CA-1.2:** As 7 armadilhas naturais (RN-01 a RN-07) estão presentes nos dados de `data/sample/` e são comprovadas por testes automatizados em `tests/test_warehouse.py`.
- [ ] **CA-1.3:** O arquivo `metadata/semantic_layer.yml` é carregado e validado por modelos Pydantic sem erros de schema, contendo pelo menos 10 métricas canônicas e 4 grupos de desambiguação.
- [ ] **CA-1.4:** O arquivo `metadata/schema.yml` documenta 100% das tabelas e colunas de `marts`.
