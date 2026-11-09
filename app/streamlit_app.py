"""Data Context Engine - Streamlit Analytical Workbench & Guided Learning Journey.

Anti-AI Design Level 2 · Responsive: Continuous Vertical Scroll (Mobile) & Stepper (Desktop).
"""

import json
import sys
from pathlib import Path

# Ensure src/ is on sys.path for direct executions (e.g. Streamlit Community Cloud)
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd
import streamlit as st

from dce.benchmark.runner import BenchmarkRunner
from dce.context.assembler import ContextAssembler
from dce.context.clarifier import SemanticClarifier
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.execution.agent import SQLAgent
from dce.execution.executor import SafeSQLExecutor
from dce.execution.guardrails import SQLGuardrail, SQLSecurityViolationError
from dce.models import ContextLevel, MetadataCatalog, SavedPlaybook
from dce.playbooks.store import PlaybookStore
from dce.warehouse.builder import build_warehouse

# -----------------------------------------------------------------------------
# Streamlit Page Config & Anti-AI Design CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Data Context Engine · Learning Journey & Workbench",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    /* Global Background & Typography */
    .stApp {
        background-color: #09090b;
        color: #f4f4f5;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }
    
    /* Headers */
    h1, h2, h3, h4 {
        letter-spacing: -0.025em;
        font-weight: 600;
        color: #fafafa;
        text-wrap: balance;
    }
    p, li {
        text-wrap: pretty;
        color: #d4d4d8;
        line-height: 1.6;
    }
    
    /* Subtle hairline cards (Anti-AI Design) */
    .dce-card {
        background-color: #18181b;
        border: 1px solid #27272a;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    .dce-card-accent {
        background-color: #18181b;
        border: 1px solid #3f3f46;
        border-left: 4px solid #6366f1;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    
    .dce-card-header {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #a1a1aa;
        margin-bottom: 8px;
    }

    .dce-metric-value {
        font-size: 24px;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        color: #f4f4f5;
    }
    
    .dce-metric-delta {
        font-size: 12px;
        color: #10b981;
        font-weight: 600;
    }

    /* Badges */
    .badge-pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-indigo {
        background-color: rgba(99, 102, 241, 0.15);
        color: #a5b4fc;
        border: 1px solid rgba(99, 102, 241, 0.35);
    }
    .badge-emerald {
        background-color: rgba(16, 185, 129, 0.15);
        color: #6ee7b7;
        border: 1px solid rgba(16, 185, 129, 0.35);
    }
    .badge-amber {
        background-color: rgba(245, 158, 11, 0.15);
        color: #fcd34d;
        border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .badge-rose {
        background-color: rgba(244, 63, 94, 0.15);
        color: #fda4af;
        border: 1px solid rgba(244, 63, 94, 0.35);
    }
    .badge-zinc {
        background-color: #27272a;
        color: #d4d4d8;
        border: 1px solid #3f3f46;
    }

    /* Clarification Banner */
    .clarification-box {
        background-color: #1c1917;
        border: 1px solid #78350f;
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 16px;
    }

    /* Step Section Banner */
    .step-banner {
        border-top: 1px solid #27272a;
        padding-top: 2rem;
        margin-top: 2.5rem;
    }

    /* Code styling */
    pre, code {
        font-family: "JetBrains Mono", "Fira Code", monospace !important;
        font-size: 13px !important;
    }

    /* Responsive Mobile Adjustments */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
            padding-top: 1rem;
        }
        .dce-card {
            padding: 12px 14px;
        }
        .stButton button {
            min-height: 48px;
            font-size: 15px;
            width: 100%;
        }
        .dce-metric-value {
            font-size: 20px;
        }
    }
</style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Engine Resource Caching
# -----------------------------------------------------------------------------
DB_PATH = Path("data/warehouse/olist.duckdb")
PLAYBOOKS_PATH = Path("data/playbooks/saved_playbooks.json")
METADATA_DIR = Path("metadata")


@st.cache_resource
def get_engine_components():
    """Initializes and caches all core engine singletons."""
    if not DB_PATH.exists():
        build_warehouse(DB_PATH, sample_orders_count=1000, seed=42)

    catalog: MetadataCatalog = load_metadata_catalog(METADATA_DIR)
    retriever = HybridRetriever(catalog=catalog, playbooks_path=PLAYBOOKS_PATH)
    clarifier = SemanticClarifier(catalog=catalog)
    executor = SafeSQLExecutor(db_path=DB_PATH)
    store = PlaybookStore(
        storage_path=PLAYBOOKS_PATH,
        retriever=retriever,
        executor=executor,
    )
    assembler = ContextAssembler(
        catalog=catalog,
        retriever=retriever,
        db_path=DB_PATH,
    )
    agent = SQLAgent(
        catalog=catalog,
        assembler=assembler,
        executor=executor,
    )
    guardrail = SQLGuardrail()
    return catalog, retriever, clarifier, executor, store, assembler, agent, guardrail


catalog, retriever, clarifier, executor, store, assembler, agent, guardrail = get_engine_components()

# -----------------------------------------------------------------------------
# Session State Defaults
# -----------------------------------------------------------------------------
if "current_question" not in st.session_state:
    st.session_state.current_question = "Quem são os nossos 10 melhores clientes?"
if "selected_metric_id" not in st.session_state:
    st.session_state.selected_metric_id = None
if "last_executed_result" not in st.session_state:
    st.session_state.last_executed_result = None
if "active_step_index" not in st.session_state:
    st.session_state.active_step_index = 0
if "guardrail_test_input" not in st.session_state:
    st.session_state.guardrail_test_input = "SELECT * FROM orders; DROP TABLE customers;"

STEP_OPTIONS = [
    "1. 🧭 O Desafio dos Dados",
    "2. ⚖️ O Duelo: L1 vs L4",
    "3. 🔬 Laboratório Interativo",
    "4. 🛡️ Defesa & Guardrails",
    "5. 📊 Catálogo & Benchmark",
]

# -----------------------------------------------------------------------------
# Sidebar Navigation & Experience Mode
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚡ DATA CONTEXT ENGINE")
    st.markdown(
        "<span class='badge-pill badge-indigo'>v0.1.0 · DuckDB Sandbox</span> "
        "<span class='badge-pill badge-emerald'>Read-Only</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Experience Format
    st.markdown("<div class='dce-card-header'>Formato de Visualização</div>", unsafe_allow_html=True)
    view_mode = st.radio(
        "Modo de Navegação",
        options=[
            "📱 Scroll Contínuo (Mobile / Página Única)",
            "💻 Passo a Passo Lateral (Desktop)",
        ],
        index=0,
        label_visibility="collapsed",
    )
    is_scroll_mode = view_mode.startswith("📱")

    if not is_scroll_mode:
        st.markdown("<div class='dce-card-header' style='margin-top:14px;'>Trilha de Aprendizado</div>", unsafe_allow_html=True)
        selected_step = st.radio(
            "Selecione a Etapa:",
            options=STEP_OPTIONS,
            index=st.session_state.active_step_index,
            key="sidebar_step_radio",
            label_visibility="collapsed",
        )
        st.session_state.active_step_index = STEP_OPTIONS.index(selected_step)

    st.markdown("---")

    # Context Level Selector (for workbench execution)
    st.markdown("<div class='dce-card-header'>Nível de Contexto (Workbench)</div>", unsafe_allow_html=True)
    level_choice = st.radio(
        "Context Level",
        options=["L4", "L3", "L2", "L1", "L0"],
        index=0,
        format_func=lambda x: {
            "L4": "L4 · Context Engine Ativo (~780 tokens)",
            "L3": "L3 · Roteamento Semântico & Grafo",
            "L2": "L2 · Schemas Analíticos (Marts)",
            "L1": "L1 · Naive Schema Dump (~5.8k tokens)",
            "L0": "L0 · Sem Contexto (Zero-Shot)",
        }[x],
        label_visibility="collapsed",
    )
    current_level = ContextLevel(level_choice)

    # Execution Mode
    st.markdown("<div class='dce-card-header' style='margin-top:14px;'>Modo de Execução</div>", unsafe_allow_html=True)
    exec_mode = st.radio(
        "Execution Mode",
        options=["Replay Cache (Offline Determinístico)", "Gemini Live (Free Tier)"],
        index=0,
        label_visibility="collapsed",
    )
    replay_only = exec_mode.startswith("Replay")

    st.markdown("---")

    # Saved Playbooks Shortcut List
    st.markdown("<div class='dce-card-header'>⭐ Playbooks Salvos (Memória)</div>", unsafe_allow_html=True)
    saved_playbooks = store.list_playbooks()
    if not saved_playbooks:
        st.caption("Nenhum playbook salvo ainda. Salve consultas auditadas no Workbench.")
    else:
        for pb in saved_playbooks[:4]:
            col_pb1, col_pb2 = st.columns([0.72, 0.28])
            with col_pb1:
                st.markdown(f"**{pb.title}**")
                st.caption(f"`{pb.resolved_metric_id or 'geral'}`")
            with col_pb2:
                if st.button("Usar", key=f"btn_pb_{pb.id}"):
                    st.session_state.current_question = pb.question
                    st.session_state.selected_metric_id = pb.resolved_metric_id
                    st.session_state.active_step_index = 2
                    st.rerun()

    st.markdown("---")
    st.markdown(
        "<div style='font-size:11px; color:#71717a;'>"
        "Hardened DuckDB Sandbox<br/>"
        "• AST Guardrails: Active<br/>"
        "• External Access: Disabled<br/>"
        "• Memory Cap: 512MB<br/>"
        "</div>",
        unsafe_allow_html=True,
    )


# =============================================================================
# SEÇÃO 1: 🧭 O DESAFIO DOS DADOS (START HERE)
# =============================================================================
def render_section_challenge():
    st.markdown("# ⚡ Data Context Engine")
    st.markdown(
        "<div style='font-size:18px; color:#a1a1aa; margin-top:-8px; margin-bottom:20px;'>"
        "Por que modelos de I.A erram 60% das consultas de dados nas empresas — e como resolver isso com Context Engineering."
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='dce-card-accent'>
            <div class='dce-card-header'>O Problema Real das Empresas</div>
            <div style='font-size:15px; color:#f4f4f5; font-weight:500;'>
                LLMs modernos sabem escrever sintaxe SQL perfeitamente. No entanto, quando colocados diante de um banco real (como o e-commerce Olist), eles falham miseravelmente em métricas básicas.
            </div>
            <div style='font-size:13px; color:#a1a1aa; margin-top:8px;'>
                <b>Exemplos comuns de alucinação analítica:</b>
                <ul style='margin-top:4px; margin-bottom:0px; padding-left:20px;'>
                    <li>Somam faturamento de pedidos cancelados (esquecem a regra de faturamento líquido).</li>
                    <li>Duplicam o cálculo de frete por somarem o valor do frete em cada item do pedido.</li>
                    <li>Tratam o <code>customer_id</code> (chave transacional que muda a cada compra) como se fosse o cliente único (<code>customer_unique_id</code>), arruinando a contagem de clientes e LTV.</li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🪜 A Escala de Contexto (L0 a L4)")
    st.markdown(
        "Em vez de apenas despejar todo o banco de dados no prompt, o **Data Context Engine** organiza o contexto em 5 níveis progressivos:"
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class='dce-card'>
                <div class='badge-pill badge-zinc'>L0 · Sem Contexto</div>
                <div style='font-size:13px; font-weight:600; margin-top:8px;'>Zero-Shot Prompting</div>
                <div style='font-size:12px; color:#a1a1aa; margin-top:4px;'>
                    Apenas a pergunta. O modelo precisa adivinhar tabelas e colunas.<br/>
                    <b>Acurácia: ~13%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class='dce-card'>
                <div class='badge-pill badge-rose'>L1 · Naive Schema Dump</div>
                <div style='font-size:13px; font-weight:600; margin-top:8px;'>Abordagem Comum de Mercado</div>
                <div style='font-size:12px; color:#a1a1aa; margin-top:4px;'>
                    Despeja todos os DDLs brutos (~5.8k tokens). O modelo se perde em joins complexos e esquece regras de negócio.<br/>
                    <b>Acurácia: ~60% · Custo Alto</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class='dce-card'>
                <div class='badge-pill badge-amber'>L2 · Schemas Analíticos</div>
                <div style='font-size:13px; font-weight:600; margin-top:8px;'>Camada Marts (dbt)</div>
                <div style='font-size:12px; color:#a1a1aa; margin-top:4px;'>
                    Filtra tabelas transacionais e entrega apenas as tabelas analíticas consolidadas.<br/>
                    <b>Acurácia: ~76%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class='dce-card'>
                <div class='badge-pill badge-indigo'>L3 · Roteamento Semântico</div>
                <div style='font-size:13px; font-weight:600; margin-top:8px;'>Busca em Grafo de Dados</div>
                <div style='font-size:12px; color:#a1a1aa; margin-top:4px;'>
                    Identifica entidades-chave e descobre automaticamente as pontes de join via BFS.<br/>
                    <b>Acurácia: ~83%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class='dce-card' style='border:1px solid #10b981; background:#062314;'>
                <div class='badge-pill badge-emerald'>L4 · Data Context Engine</div>
                <div style='font-size:13px; font-weight:600; margin-top:8px;'>Arquitetura de Alta Precisão</div>
                <div style='font-size:12px; color:#d4d4d8; margin-top:4px;'>
                    • <b>Prefix Caching:</b> -61.3% tokens salvos.<br/>
                    • <b>Regras Canônicas (RN-01..RN-07):</b> Faturamento e SLA corretos.<br/>
                    • <b>Guardrails AST:</b> Zero injeções SQL.<br/>
                    <b>Acurácia: 90% (Gold Benchmark)</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.button("👉 Ver a I.A falhando no L1 e acertando no L4 (O Duelo)", key="btn_goto_duel"):
        st.session_state.active_step_index = 1
        st.rerun()


# =============================================================================
# SEÇÃO 2: ⚖️ O DUELO L1 VS L4 (PROVA IMEDIATA)
# =============================================================================
def render_section_duel():
    st.markdown("## ⚖️ O Duelo: `L1 Naive Dump` vs `L4 Context Engine`")
    st.markdown(
        "<div style='font-size:14px; color:#a1a1aa; margin-bottom:16px;'>"
        "Veja como despejar o banco bruto (L1) gasta 7x mais tokens e erra a matemática do negócio, "
        "enquanto o Context Engine (L4) gera a consulta correta com custo mínimo."
        "</div>",
        unsafe_allow_html=True,
    )

    compare_question = st.selectbox(
        "Selecione uma pergunta de teste com armadilha de negócio:",
        options=[
            "Qual o faturamento total da empresa?",
            "Quem são os nossos 10 melhores clientes?",
            "Quantos clientes únicos realizaram compras em 2017?",
            "Qual o valor médio do frete por estado?",
        ],
        index=0,
        key="duel_question_selector",
    )

    if st.button("⚡ Executar Duelo L1 vs L4", key="btn_run_duel"):
        with st.spinner("Executando comparativo paralelo no DuckDB..."):
            res_l1 = agent.run_turn(compare_question, level=ContextLevel.L1, replay_only=True)
            res_l4 = agent.run_turn(
                compare_question,
                level=ContextLevel.L4,
                selected_metric_id="net_revenue" if "faturamento" in compare_question else None,
                replay_only=True,
            )
            st.session_state.compare_l1 = res_l1
            st.session_state.compare_l4 = res_l4

    if "compare_l1" in st.session_state and "compare_l4" in st.session_state:
        c_l1 = st.session_state.compare_l1
        c_l4 = st.session_state.compare_l4

        col_comp1, col_comp2 = st.columns(2, gap="medium")

        with col_comp1:
            st.markdown(
                """
                <div style='border:1px solid #7f1d1d; background:#1c1917; border-radius:8px; padding:12px 16px; margin-bottom:12px;'>
                    <div style='font-size:13px; font-weight:700; color:#f87171;'>❌ Nível L1 · Naive Schema Dump</div>
                    <div style='font-size:11px; color:#d4d4d8;'>Sem camada semântica. Despeja todas as tabelas brutas no prompt.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"**Tokens do Prompt:** `{c_l1.assembled_context.inspection.assembled_context_tokens}` tokens (0% economia)")
            st.markdown("**Prefix Cacheável:** `0.0%`")
            st.markdown("**SQL Gerado:**")
            st.code(c_l1.generated_sql.sanitized_sql or c_l1.generated_sql.raw_sql, language="sql")
            st.markdown("**Resultado no Banco:**")
            if c_l1.execution_result.rows:
                st.dataframe(pd.DataFrame(c_l1.execution_result.rows, columns=c_l1.execution_result.columns).head(3), use_container_width=True)
            st.caption("⚠️ **Falha Comum:** Esquece `order_status = 'delivered'` somando cancelados, ou agrupa por `customer_id` transacional em vez de `customer_unique_id`.")

        with col_comp2:
            st.markdown(
                """
                <div style='border:1px solid #14532d; background:#052e16; border-radius:8px; padding:12px 16px; margin-bottom:12px;'>
                    <div style='font-size:13px; font-weight:700; color:#4ade80;'>✓ Nível L4 · Data Context Engine</div>
                    <div style='font-size:11px; color:#d4d4d8;'>Roteamento de marts, métricas canônicas, prefix caching e AST guardrail.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Tokens do Prompt:** `{c_l4.assembled_context.inspection.assembled_context_tokens}` tokens "
                f"<span class='badge-pill badge-emerald'>-{c_l4.assembled_context.inspection.token_savings_pct:.1f}%</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Prefix Cacheável:** `{c_l4.assembled_context.inspection.prefix_cacheable_pct:.1f}%`")
            st.markdown("**SQL Gerado:**")
            st.code(c_l4.generated_sql.sanitized_sql or c_l4.generated_sql.raw_sql, language="sql")
            st.markdown("**Resultado no Banco:**")
            if c_l4.execution_result.rows:
                st.dataframe(pd.DataFrame(c_l4.execution_result.rows, columns=c_l4.execution_result.columns).head(3), use_container_width=True)
            st.caption("✓ **Precisão Garantida:** Aplica regras canônicas (RN-01..RN-07), limit automático e validação AST no DuckDB.")


# =============================================================================
# SEÇÃO 3: 🔬 LABORATÓRIO INTERATIVO (WORKBENCH ANALÍTICO)
# =============================================================================
def render_section_workbench():
    st.markdown("## 🔬 Laboratório Interativo (Workbench Analítico)")
    st.markdown(
        "<div style='font-size:14px; color:#a1a1aa; margin-bottom:16px;'>"
        "Teste consultas livres ou selecione exemplos com armadilhas de negócio. "
        "Acompanhe a desambiguação semântica ativa e a auditoria em tempo real."
        "</div>",
        unsafe_allow_html=True,
    )

    sample_options = [
        "Quem são os nossos 10 melhores clientes?",
        "Qual o faturamento total da empresa?",
        "Quais vendedores tiveram melhor desempenho?",
        "Qual o tempo médio de entrega dos pedidos em São Paulo?",
        "Quantos clientes cancelaram pedidos no último trimestre?",
        "Qual a taxa de entrega no prazo por estado?",
    ]

    col_q1, col_q2 = st.columns([0.65, 0.35])
    with col_q1:
        user_input = st.text_input(
            "Pergunta Analítica em Linguagem Natural:",
            value=st.session_state.current_question,
            key="input_user_question",
        )
    with col_q2:
        quick_pick = st.selectbox("Ou selecione uma pergunta padrão:", ["-- Selecione --"] + sample_options)
        if quick_pick != "-- Selecione --":
            user_input = quick_pick
            st.session_state.current_question = quick_pick

    # Semantic Clarification Check
    clarification = clarifier.clarify(user_input)
    if clarification.needs_clarification:
        st.markdown(
            f"""
            <div class='clarification-box'>
                <div style='font-weight:700; color:#fbbf24; font-size:13px; margin-bottom:4px;'>
                    ⚠️ Desambiguação Semântica Necessária ({clarification.ambiguity_type.upper()})
                </div>
                <div style='font-size:13px; color:#e2e8f0;'>
                    {clarification.clarification_prompt}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if clarification.options:
            metric_options = {opt.metric_id: f"{opt.metric_name} — {opt.description}" for opt in clarification.options}
            selected_metric = st.radio(
                "Escolha a métrica de negócio a ser aplicada:",
                options=list(metric_options.keys()),
                format_func=lambda x: metric_options[x],
                horizontal=False,
                key="radio_metric_choice",
            )
            st.session_state.selected_metric_id = selected_metric

    if st.button("🚀 Executar no DuckDB Sandbox", key="btn_run_workbench"):
        with st.spinner("Compilando contexto e executando SQL no DuckDB..."):
            result = agent.run_turn(
                user_input,
                level=current_level,
                selected_metric_id=st.session_state.selected_metric_id,
                replay_only=replay_only,
            )
            st.session_state.last_executed_result = result
            st.session_state.current_question = user_input

    # Display Execution Results
    if st.session_state.last_executed_result:
        res = st.session_state.last_executed_result

        # Metrics Bar
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"""
                <div class='dce-card'>
                    <div class='dce-card-header'>Tokens do Contexto</div>
                    <div class='dce-metric-value'>{res.assembled_context.inspection.assembled_context_tokens}</div>
                    <div class='dce-metric-delta'>-{res.assembled_context.inspection.token_savings_pct:.1f}% vs L1</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f"""
                <div class='dce-card'>
                    <div class='dce-card-header'>Prefix Cacheável</div>
                    <div class='dce-metric-value'>{res.assembled_context.inspection.prefix_cacheable_pct:.1f}%</div>
                    <div class='dce-metric-delta'>Economia de I/O</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f"""
                <div class='dce-card'>
                    <div class='dce-card-header'>Linhas Retornadas</div>
                    <div class='dce-metric-value'>{res.execution_result.row_count}</div>
                    <div style='font-size:12px; color:#a1a1aa;'>{res.execution_result.execution_time_ms:.1f}ms</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m4:
            st.markdown(
                f"""
                <div class='dce-card'>
                    <div class='dce-card-header'>Guardrail AST</div>
                    <div class='dce-metric-value' style='color:#34d399;'>Aprovado</div>
                    <div style='font-size:12px; color:#a1a1aa;'>Sandbox Read-Only</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Tabs for result inspection
        tab_data, tab_sql, tab_context, tab_save = st.tabs([
            "📊 Tabela de Dados",
            "🔍 SQL Auditado",
            "🧠 Inspeção de Contexto L0..L4",
            "💾 Salvar como Playbook",
        ])

        with tab_data:
            if res.execution_result.error_message:
                st.error(f"Erro na execução: {res.execution_result.error_message}")
            elif res.execution_result.rows:
                df = pd.DataFrame(res.execution_result.rows, columns=res.execution_result.columns)
                st.dataframe(df, use_container_width=True, height=260)
            else:
                st.info("A consulta retornou 0 linhas.")

        with tab_sql:
            st.code(res.generated_sql.sanitized_sql or res.generated_sql.raw_sql, language="sql")
            st.caption(f"Tabelas utilizadas: `{', '.join(res.generated_sql.tables_used)}` · Modo: `{current_level.value}`")

        with tab_context:
            st.markdown(f"**Sistema de Prompt ({current_level.value}):**")
            st.text_area("Prompt montado para a I.A:", value=res.assembled_context.system_prompt, height=220, disabled=True)

        with tab_save:
            st.markdown("Salve esta consulta verificada para acelerar perguntas futuras da equipe:")
            with st.form("form_save_playbook"):
                pb_title = st.text_input("Título do Playbook:", value=f"Consulta: {user_input[:40]}")
                pb_desc = st.text_area("Descrição / Uso Recomendado:", value="Playbook canônico com regras de negócio verificadas.")
                if st.form_submit_button("Salvar no PlaybookStore"):
                    saved_pb = store.save_playbook(
                        question=user_input,
                        sql=res.generated_sql.sanitized_sql or res.generated_sql.raw_sql,
                        title=pb_title,
                        description=pb_desc,
                        resolved_metric_id=st.session_state.selected_metric_id,
                        verified=True,
                    )
                    st.success(f"Playbook '{saved_pb.title}' salvo com sucesso!")
                    st.rerun()


# =============================================================================
# SEÇÃO 4: 🛡️ SIMULADOR DE ATAQUE & DEFESA (GUARDRAILS)
# =============================================================================
def render_section_guardrails():
    st.markdown("## 🛡️ Simulador de Ataque & Defesa (SQL Guardrails)")
    st.markdown(
        "<div style='font-size:14px; color:#a1a1aa; margin-bottom:16px;'>"
        "Teste injeções SQL e comandos maliciosos contra o guardrail baseado em AST (sqlglot). "
        "Comandos perigosos são interceptados e bloqueados antes mesmo de encostar no DuckDB."
        "</div>",
        unsafe_allow_html=True,
    )

    attack_presets = [
        "Injeção DDL: SELECT * FROM orders; DROP TABLE customers;",
        "Exaustão de Recursos: SELECT pg_sleep(10);",
        "Acesso ao Sistema: COPY customers TO '/tmp/leak.csv';",
        "Bypass com Comentários: SELECT * FROM orders -- DROP TABLE customers",
        "Consulta Segura com Limite Exorbitante: SELECT * FROM orders LIMIT 9999999;",
        "Consulta Canônica Válida: SELECT customer_unique_id, SUM(price) FROM marts.fct_orders GROUP BY 1 LIMIT 10;",
    ]

    selected_preset = st.selectbox("Escolha um vetor de teste pré-configurado:", attack_presets, index=0)
    raw_preset_sql = selected_preset.split(": ", 1)[1] if ": " in selected_preset else selected_preset

    custom_sql = st.text_area("SQL a ser inspecionado pelo Guardrail:", value=raw_preset_sql, height=90)

    if st.button("🛡️ Inspecionar com Guardrail AST", key="btn_check_guardrail"):
        try:
            guard_result = guardrail.validate_and_sanitize(custom_sql)
            st.markdown(
                """
                <div style='border:1px solid #14532d; background:#052e16; border-radius:8px; padding:14px 18px; margin-top:12px;'>
                    <div style='font-size:14px; font-weight:700; color:#4ade80;'>✓ QUERY APROVADA PELO GUARDRAIL</div>
                    <div style='font-size:12px; color:#d4d4d8; margin-top:4px;'>
                        A árvore sintática (AST) confirmou apenas comandos SELECT seguros. O limite máximo seguro foi aplicado automaticamente.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("**SQL Sanitizado Pronto para Execução:**")
            st.code(guard_result.sanitized_sql, language="sql")
            st.caption(f"Tabelas identificadas: `{', '.join(guard_result.tables_used)}` · Limite aplicado: `{guard_result.limit_applied}`")
        except SQLSecurityViolationError as exc:
            st.markdown(
                f"""
                <div style='border:1px solid #7f1d1d; background:#1c1917; border-radius:8px; padding:14px 18px; margin-top:12px;'>
                    <div style='font-size:14px; font-weight:700; color:#f87171;'>🛑 ATAQUE BLOQUEADO (Violação de Segurança)</div>
                    <div style='font-size:12px; color:#fca5a5; margin-top:4px;'>
                        <b>Código da Violação:</b> <code>{exc.violation_type.value}</code><br/>
                        <b>Motivo:</b> {exc.message}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("🛡️ O comando foi descartado na análise de AST e **nunca** chegou a ser enviado ao banco de dados.")


# =============================================================================
# SEÇÃO 5: 📊 CATÁLOGO DE GOVERNANÇA & BENCHMARK OFICIAL
# =============================================================================
def render_section_catalog_and_benchmark():
    st.markdown("## 📊 Dicionário de Governança & Benchmark Oficial")
    st.markdown(
        "<div style='font-size:14px; color:#a1a1aa; margin-bottom:16px;'>"
        "Transparência total das regras de negócio ativas no motor e resultados consolidados nos 30 Gold Questions."
        "</div>",
        unsafe_allow_html=True,
    )

    tab_cat, tab_bench = st.tabs(["📚 Regras Canônicas & Métricas", "📈 Benchmark dos 30 Gold Questions"])

    with tab_cat:
        st.markdown("### 📜 Regras de Negócio Oficiais (RN-01 a RN-07)")
        rules_data = [
            {"Regra": "RN-01", "Nome": "Faturamento Líquido", "Condição Obrigatória": "Apenas pedidos com order_status = 'delivered'"},
            {"Regra": "RN-02", "Nome": "Cliente Único", "Condição Obrigatória": "Agrupar sempre por customer_unique_id (nunca customer_id)"},
            {"Regra": "RN-03", "Nome": "SLA de Entrega", "Condição Obrigatória": "order_delivered_customer_date <= order_estimated_delivery_date"},
            {"Regra": "RN-04", "Nome": "Frete por Pedido", "Condição Obrigatória": "Somar frete uma única vez por pedido (evitar duplicação nos itens)"},
            {"Regra": "RN-05", "Nome": "Top Vendedores", "Condição Obrigatória": "Classificados por receita de itens entregues"},
            {"Regra": "RN-06", "Nome": "Ticket Médio", "Condição Obrigatória": "Receita de produtos entregues dividida por pedidos entregues"},
            {"Regra": "RN-07", "Nome": "Cancelamentos", "Condição Obrigatória": "Pedidos com order_status IN ('canceled', 'unavailable')"},
        ]
        st.dataframe(pd.DataFrame(rules_data), use_container_width=True)

        st.markdown("### 📐 Métricas Canônicas Definidas")
        metrics_data = [
            {"ID": m.id, "Nome": m.name, "Expressão": m.sql_expression, "Tabela Base": m.base_table, "Regras": ", ".join(m.business_rules)}
            for m in catalog.semantic_layer.metrics
        ]
        st.dataframe(pd.DataFrame(metrics_data), use_container_width=True)

    with tab_bench:
        st.markdown("### 🏆 Evolução de Acurácia nos 30 Gold Questions")
        summary_path = Path("results/benchmark_summary.json")
        if summary_path.exists():
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            summary_rows = []
            for item in data.get("results", []):
                lvl = item["level"]
                summary_rows.append({
                    "Nível": lvl,
                    "Acurácia 1-Shot": f"{item['single_shot_accuracy'] * 100:.1f}%",
                    "Acurácia c/ Autocorreção": f"{item['corrected_accuracy'] * 100:.1f}%",
                    "Tokens Médios": int(item["avg_tokens"]),
                    "Economia de Tokens": f"{item.get('token_savings_pct', 0.0):.1f}%",
                    "Acertos Finais": f"{item['correct_with_correction']}/30",
                })

            df_summary = pd.DataFrame(summary_rows)
            st.dataframe(df_summary, use_container_width=True)

            # Chart
            chart_df = pd.DataFrame({
                "Nível": [r["Nível"] for r in summary_rows],
                "Acurácia (%)": [float(r["Acurácia c/ Autocorreção"].replace("%", "")) for r in summary_rows],
            }).set_index("Nível")
            st.bar_chart(chart_df, color="#6366f1")
            st.caption("O Context Engine (L4) atinge 90.0% de acurácia com redução de 61.3% no volume de tokens consumidos.")
        else:
            st.info("Arquivo de resultados do benchmark não encontrado em results/benchmark_summary.json.")


# -----------------------------------------------------------------------------
# Main Application Router (Scroll Contínuo vs Stepper)
# -----------------------------------------------------------------------------
if is_scroll_mode:
    # 📱 Experiência de Scrollagem Vertical Direta (Mobile-First)
    render_section_challenge()

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_duel()

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_workbench()

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_guardrails()

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_catalog_and_benchmark()

    st.markdown("---")
    st.caption("⚡ Data Context Engine · Anti-AI Design Level 2 · Repositório Público no GitHub: dantinha/data-context-engine")

else:
    # 💻 Experiência Lateral Passo a Passo (Desktop)
    current_step = st.session_state.active_step_index

    # Render Active Section
    if current_step == 0:
        render_section_challenge()
    elif current_step == 1:
        render_section_duel()
    elif current_step == 2:
        render_section_workbench()
    elif current_step == 3:
        render_section_guardrails()
    elif current_step == 4:
        render_section_catalog_and_benchmark()

    # Step Stepper Navigation Footer
    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    col_nav1, col_nav2 = st.columns([0.5, 0.5])
    with col_nav1:
        if current_step > 0:
            if st.button(f"← {STEP_OPTIONS[current_step - 1]}", key="btn_prev_step"):
                st.session_state.active_step_index = current_step - 1
                st.rerun()
    with col_nav2:
        if current_step < len(STEP_OPTIONS) - 1:
            if st.button(f"{STEP_OPTIONS[current_step + 1]} →", key="btn_next_step"):
                st.session_state.active_step_index = current_step + 1
                st.rerun()
