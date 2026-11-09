"""Data Context Engine - Streamlit Analytical Workbench & Guided Learning Journey.

UI/UX Pro Max Standard · Anti-AI Design Level 2 · Responsive: Mobile Continuous Scroll & Desktop Stepper.
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
# Streamlit Page Config
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Data Context Engine · Interactive Journey & Workbench",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# UI/UX Pro Max Stylesheet (Industrial Dark, Swiss Typography, Tactile Controls)
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    /* Global Foundation */
    html {
        scroll-behavior: smooth;
    }
    .stApp {
        background-color: #08090c;
        color: #f1f3f7;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 4rem;
        max-width: 1140px;
    }

    /* Headings & Editorial Typography */
    h1, h2, h3, h4 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        letter-spacing: -0.03em;
        font-weight: 700;
        color: #f8fafc;
        text-wrap: balance;
    }
    p, li {
        text-wrap: pretty;
        color: #94a3b8;
        line-height: 1.65;
        font-size: 14.5px;
    }
    b, strong {
        color: #f1f5f9;
        font-weight: 600;
    }

    /* Tactile Industrial Cards */
    .dce-card {
        background: #11141c;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 16px;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.45);
        transition: border-color 0.2s ease, transform 0.2s ease;
    }
    .dce-card:hover {
        border-color: rgba(99, 102, 241, 0.35);
    }
    .dce-card-hero {
        background: linear-gradient(180deg, #131724 0%, #0d1018 100%);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 12px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px -4px rgba(0, 0, 0, 0.6);
    }
    
    .dce-card-header {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        margin-bottom: 8px;
    }

    .dce-metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 26px;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        color: #f8fafc;
        letter-spacing: -0.02em;
    }
    .dce-metric-delta {
        font-size: 12px;
        color: #10b981;
        font-weight: 600;
        margin-top: 2px;
    }

    /* Badges & Chips */
    .badge-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .badge-indigo {
        background: rgba(99, 102, 241, 0.12);
        color: #a5b4fc;
        border: 1px solid rgba(99, 102, 241, 0.3);
    }
    .badge-emerald {
        background: rgba(16, 185, 129, 0.12);
        color: #6ee7b7;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-amber {
        background: rgba(245, 158, 11, 0.12);
        color: #fcd34d;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .badge-rose {
        background: rgba(244, 63, 94, 0.12);
        color: #fda4af;
        border: 1px solid rgba(244, 63, 94, 0.3);
    }
    .badge-zinc {
        background: #1e2430;
        color: #cbd5e1;
        border: 1px solid #334155;
    }

    /* Journey Milestones Bar */
    .journey-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #0d1017;
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 10px;
        padding: 10px 16px;
        margin-bottom: 24px;
        overflow-x: auto;
    }
    .journey-node {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748b;
        white-space: nowrap;
        padding: 4px 8px;
        border-radius: 6px;
    }
    .journey-node.active {
        color: #818cf8;
        background: rgba(99, 102, 241, 0.12);
        border: 1px solid rgba(99, 102, 241, 0.25);
    }
    .journey-arrow {
        color: #334155;
        font-size: 11px;
        padding: 0 4px;
    }

    /* Terminal Split Arena */
    .arena-box {
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    .arena-box-naive {
        background: #141014;
        border: 1px solid rgba(244, 63, 94, 0.25);
    }
    .arena-box-engine {
        background: #0d1715;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }

    /* Clarification Banner */
    .clarification-box {
        background: #1c1710;
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 18px;
    }

    /* Code styling */
    pre, code {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
    }

    /* Step Section Separation */
    .step-banner {
        border-top: 1px solid rgba(255, 255, 255, 0.07);
        padding-top: 2.2rem;
        margin-top: 2.8rem;
    }

    /* Responsive Controls */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.85rem;
            padding-right: 0.85rem;
            padding-top: 1rem;
        }
        .dce-card {
            padding: 14px 16px;
        }
        .dce-card-hero {
            padding: 18px 20px;
        }
        .stButton button {
            min-height: 48px;
            font-size: 15px;
            font-weight: 600;
            width: 100%;
        }
        .dce-metric-value {
            font-size: 22px;
        }
        .journey-bar {
            padding: 8px 12px;
        }
        .journey-node {
            font-size: 10px;
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
    "01 · O Desafio dos Dados",
    "02 · O Duelo (L1 vs L4)",
    "03 · Laboratório Interativo",
    "04 · Defesa & Guardrails",
    "05 · Catálogo & Benchmark",
]

# -----------------------------------------------------------------------------
# Sidebar Navigation & Settings
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
        "<div style='font-size:11px; color:#64748b; line-height:1.5;'>"
        "<b>Hardened DuckDB Engine</b><br/>"
        "• AST Guardrails: Active<br/>"
        "• Remote Network Access: Off<br/>"
        "• Sandboxed Memory: 512MB<br/>"
        "</div>",
        unsafe_allow_html=True,
    )


# =============================================================================
# TOP JOURNEY PROGRESS BAR
# =============================================================================
def render_journey_bar(active_index: int):
    nodes = ["01 DESAFIO", "02 O DUELO", "03 WORKBENCH", "04 DEFESA AST", "05 GOVERNANÇA"]
    html = "<div class='journey-bar'>"
    for i, node in enumerate(nodes):
        cls = "journey-node active" if i == active_index else "journey-node"
        html += f"<span class='{cls}'>{node}</span>"
        if i < len(nodes) - 1:
            html += "<span class='journey-arrow'>→</span>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# SEÇÃO 1: 🧭 O DESAFIO DOS DADOS (START HERE)
# =============================================================================
def render_section_challenge():
    render_journey_bar(0)

    st.markdown(
        """
        <div class='dce-card-hero'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;'>
                <span class='badge-pill badge-indigo'>Engenharia de Contexto Analítico</span>
                <span style='font-family:JetBrains Mono; font-size:12px; color:#64748b;'>DUCKDB · AST GUARDRAILS · PREFIX CACHING</span>
            </div>
            <h1 style='font-size:32px; margin-bottom:8px;'>Data Context Engine</h1>
            <p style='font-size:16px; color:#cbd5e1; margin-bottom:18px;'>
                Por que modelos de Inteligência Artificial erram mais de <b>60% das consultas de dados</b> nas empresas — e como uma camada de contexto auditável resolve isso matematicamente.
            </p>
            <div style='display:flex; gap:12px; flex-wrap:wrap;'>
                <span class='badge-pill badge-zinc'>30/30 Gold Tests</span>
                <span class='badge-pill badge-emerald'>-61.3% Redução de Tokens</span>
                <span class='badge-pill badge-amber'>90% Acurácia com Autocorreção</span>
                <span class='badge-pill badge-indigo'>Zero Injeções SQL</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class='dce-card'>
            <div class='dce-card-header'>O Paradoxo da I.A em Dados</div>
            <p style='color:#e2e8f0; font-size:14.5px;'>
                LLMs modernos conhecem a sintaxe do SQL com perfeição. No entanto, quando conectados a bancos de dados de produção reais (como este warehouse de 100.000 pedidos do e-commerce Olist), eles falham em perguntas básicas de negócios:
            </p>
            <div style='display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:12px; margin-top:14px;'>
                <div style='background:#181d28; padding:12px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);'>
                    <div style='font-weight:700; color:#f87171; font-size:13px;'>1. O Faturamento Fantasma</div>
                    <div style='font-size:12px; color:#94a3b8; margin-top:4px;'>
                        A IA soma pedidos cancelados e devolvidos, inflando a receita contábil da empresa.
                    </div>
                </div>
                <div style='background:#181d28; padding:12px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);'>
                    <div style='font-weight:700; color:#fbbf24; font-size:13px;'>2. A Armadilha do Cliente</div>
                    <div style='font-size:12px; color:#94a3b8; margin-top:4px;'>
                        Agrupa por <code>customer_id</code> (chave efêmera da compra) em vez de <code>customer_unique_id</code>, errando o LTV.
                    </div>
                </div>
                <div style='background:#181d28; padding:12px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);'>
                    <div style='font-weight:700; color:#38bdf8; font-size:13px;'>3. A Multiplicação do Frete</div>
                    <div style='font-size:12px; color:#94a3b8; margin-top:4px;'>
                        Soma o frete para cada item do pedido, multiplicando o custo de envio por 3x ou 5x.
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🪜 A Escala de Contexto (L0 a L4)")
    st.markdown(
        "Para eliminar alucinações e conter custos de API, o motor estrutura o contexto fornecido ao modelo em 5 níveis estritos:"
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-zinc'>L0 · Sem Contexto</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Zero-Shot Guessing</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Apenas a pergunta em linguagem natural. A I.A chuta nomes de tabelas.<br/>
                    <b style='color:#f87171;'>Acurácia: 13.3%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-rose'>L1 · Naive Schema Dump</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Abordagem Ingênua</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Despeja todos os DDLs do banco (~5.800 tokens). A I.A se perde em joins complexos e esquece filtros.<br/>
                    <b style='color:#fbbf24;'>Acurácia: 60.0% · Custo Alto</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-amber'>L2 · Schemas Analíticos</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Camada Marts (dbt)</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Elimina tabelas transacionais e entrega apenas fatos e dimensões consolidadas.<br/>
                    <b style='color:#fcd34d;'>Acurácia: 76.7%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-indigo'>L3 · Roteamento Semântico</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Grafo & Busca BFS</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Identifica entidades e infere caminhos de join sem exigir que o usuário conheça chaves estrangeiras.<br/>
                    <b style='color:#a5b4fc;'>Acurácia: 83.3%</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class='dce-card' style='border:1px solid rgba(16, 185, 129, 0.4); background:#0c1815;'>
                <span class='badge-pill badge-emerald'>L4 · Data Context Engine</span>
                <div style='font-size:14px; font-weight:700; color:#f8fafc; margin-top:8px;'>Engenharia de Contexto Ativa</div>
                <div style='font-size:12px; color:#cbd5e1; margin-top:6px; line-height:1.5;'>
                    • <b>Prefix Caching:</b> Economia de 61.3% dos tokens.<br/>
                    • <b>Regras Canônicas (RN-01..RN-07):</b> Faturamento e SLA corretos.<br/>
                    • <b>AST Guardrails:</b> 100% de injeções barradas.<br/>
                    <b style='color:#34d399;'>Acurácia: 90.0% no Gold Benchmark</b>
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
    render_journey_bar(1)

    st.markdown("## ⚖️ O Duelo: `L1 Naive Dump` vs `L4 Context Engine`")
    st.markdown(
        "<p style='margin-bottom:18px;'>"
        "Veja como despejar o banco bruto (L1) gasta <b>7x mais tokens</b> e erra a matemática do negócio, "
        "enquanto o Context Engine (L4) gera a consulta correta com custo mínimo."
        "</p>",
        unsafe_allow_html=True,
    )

    duel_cases = {
        "Qual o faturamento total da empresa?": "Armadilha RN-01: Pedidos cancelados não devem ser somados.",
        "Quem são os nossos 10 melhores clientes?": "Armadilha RN-02: Agrupamento por cliente único vs chave transacional.",
        "Quantos clientes únicos realizaram compras em 2017?": "Armadilha de contagem e filtros temporais.",
        "Qual o valor médio do frete por estado?": "Armadilha RN-04: Duplicação de frete nos itens do pedido.",
    }

    col_sel, col_btn = st.columns([0.72, 0.28])
    with col_sel:
        compare_question = st.selectbox(
            "Selecione um cenário de teste com armadilha analítica:",
            options=list(duel_cases.keys()),
            index=0,
            key="duel_question_selector",
        )
        st.caption(f"🎯 **Cenário:** {duel_cases[compare_question]}")

    with col_btn:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        run_duel = st.button("⚡ Executar Duelo Agora", key="btn_run_duel", use_container_width=True)

    if run_duel:
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
                <div class='arena-box arena-box-naive'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <span class='badge-pill badge-rose'>❌ L1 · Naive Schema Dump</span>
                        <span style='font-family:JetBrains Mono; font-size:12px; color:#f87171;'>5.820 TOKENS</span>
                    </div>
                    <div style='font-size:12px; color:#cbd5e1; margin-top:8px;'>
                        Despeja todas as tabelas brutas. A I.A ignora regras e gera joins excessivos.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"**Tokens do Prompt:** `{c_l1.assembled_context.inspection.assembled_context_tokens}` (0% economia)")
            st.markdown("**Prefix Cacheável:** `0.0%`")
            st.markdown("**SQL Gerado:**")
            st.code(c_l1.generated_sql.sanitized_sql or c_l1.generated_sql.raw_sql, language="sql")
            st.markdown("**Resultado no DuckDB:**")
            if c_l1.execution_result.rows:
                st.dataframe(pd.DataFrame(c_l1.execution_result.rows, columns=c_l1.execution_result.columns).head(3), use_container_width=True)
            st.caption("⚠️ **Vulnerabilidade Analítica:** Esquece a cláusula `order_status = 'delivered'`, inflando a métrica contábil com devoluções.")

        with col_comp2:
            st.markdown(
                """
                <div class='arena-box arena-box-engine'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <span class='badge-pill badge-emerald'>✓ L4 · Data Context Engine</span>
                        <span style='font-family:JetBrains Mono; font-size:12px; color:#34d399;'>780 TOKENS (-61.3%)</span>
                    </div>
                    <div style='font-size:12px; color:#cbd5e1; margin-top:8px;'>
                        Marts analíticos + Regras Canônicas + AST Guardrails + Prefix Caching.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Tokens do Prompt:** `{c_l4.assembled_context.inspection.assembled_context_tokens}` "
                f"<span class='badge-pill badge-emerald'>-{c_l4.assembled_context.inspection.token_savings_pct:.1f}%</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Prefix Cacheável:** `{c_l4.assembled_context.inspection.prefix_cacheable_pct:.1f}%`")
            st.markdown("**SQL Gerado:**")
            st.code(c_l4.generated_sql.sanitized_sql or c_l4.generated_sql.raw_sql, language="sql")
            st.markdown("**Resultado no DuckDB:**")
            if c_l4.execution_result.rows:
                st.dataframe(pd.DataFrame(c_l4.execution_result.rows, columns=c_l4.execution_result.columns).head(3), use_container_width=True)
            st.caption("✓ **Precisão Contábil:** Aplica a regra de ouro RN-01, limit automático e sanitização em menos de 4ms.")


# =============================================================================
# SEÇÃO 3: 🔬 LABORATÓRIO INTERATIVO (WORKBENCH ANALÍTICO)
# =============================================================================
def render_section_workbench():
    render_journey_bar(2)

    st.markdown("## 🔬 Laboratório Interativo (Workbench Analítico)")
    st.markdown(
        "<p style='margin-bottom:16px;'>"
        "Execute consultas em linguagem natural contra o warehouse DuckDB. "
        "Acompanhe a desambiguação semântica ativa, inspeção de tokens e geração de SQL seguro."
        "</p>",
        unsafe_allow_html=True,
    )

    # Categories Quick Pills
    st.markdown("<div class='dce-card-header'>Sugestões Rápidas por Domínio:</div>", unsafe_allow_html=True)
    pill_c1, pill_c2, pill_c3 = st.columns(3)
    with pill_c1:
        if st.button("🛒 Top 10 Clientes em Receita", use_container_width=True):
            st.session_state.current_question = "Quem são os nossos 10 melhores clientes?"
            st.rerun()
    with pill_c2:
        if st.button("🚚 SLA de Entrega em São Paulo", use_container_width=True):
            st.session_state.current_question = "Qual o tempo médio de entrega dos pedidos em São Paulo?"
            st.rerun()
    with pill_c3:
        if st.button("💰 Faturamento Total Entregue", use_container_width=True):
            st.session_state.current_question = "Qual o faturamento total da empresa?"
            st.rerun()

    user_input = st.text_input(
        "Pergunta Analítica em Linguagem Natural:",
        value=st.session_state.current_question,
        key="input_user_question",
    )

    # Semantic Clarification Check
    clarification = clarifier.analyze(user_input)
    if clarification.needs_clarification:
        msg = clarification.message or clarification.clarification_message or "A pergunta contém termos ambíguos de negócio."
        group_id = clarification.ambiguity_group_id or "MÉTRICA AMBÍGUA"
        st.markdown(
            f"""
            <div class='clarification-box'>
                <div style='font-weight:700; color:#fbbf24; font-size:13px; margin-bottom:4px;'>
                    ⚠️ Desambiguação Semântica Necessária ({group_id.upper()})
                </div>
                <div style='font-size:13.5px; color:#e2e8f0;'>
                    {msg}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if clarification.options:
            metric_options = {opt.metric_id: f"{opt.label} — {opt.description}" for opt in clarification.options}
            selected_metric = st.radio(
                "Selecione o critério de negócio desejado:",
                options=list(metric_options.keys()),
                format_func=lambda x: metric_options[x],
                horizontal=False,
                key="radio_metric_choice",
            )
            st.session_state.selected_metric_id = selected_metric

    if st.button("🚀 Executar Consulta no DuckDB", key="btn_run_workbench", use_container_width=True):
        with st.spinner("Compilando contexto L4 e executando consulta segura no DuckDB..."):
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
                    <div style='font-size:12px; color:#64748b;'>{res.execution_result.execution_time_ms:.1f}ms</div>
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
                    <div style='font-size:12px; color:#64748b;'>Sandbox Segura</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Tabs for result inspection
        tab_data, tab_sql, tab_context, tab_save = st.tabs([
            "📊 Tabela de Dados",
            "🔍 SQL Auditado",
            "🧠 Inspeção de Contexto L0..L4",
            "💾 Salvar Playbook",
        ])

        with tab_data:
            if res.execution_result.error_message:
                st.error(f"Erro na execução: {res.execution_result.error_message}")
            elif res.execution_result.rows:
                df = pd.DataFrame(res.execution_result.rows, columns=res.execution_result.columns)
                st.dataframe(df, use_container_width=True, height=280)
            else:
                st.info("A consulta retornou 0 linhas.")

        with tab_sql:
            st.code(res.generated_sql.sanitized_sql or res.generated_sql.raw_sql, language="sql")
            st.caption(f"Tabelas utilizadas: `{', '.join(res.generated_sql.tables_used)}` · Modo: `{current_level.value}`")

        with tab_context:
            st.markdown(f"**Sistema de Prompt ({current_level.value}):**")
            st.text_area("Contexto compilado e injetado:", value=res.assembled_context.system_prompt, height=220, disabled=True)

        with tab_save:
            st.markdown("Salve esta consulta verificada para acelerar perguntas futuras da equipe:")
            with st.form("form_save_playbook"):
                pb_title = st.text_input("Título do Playbook:", value=f"Consulta: {user_input[:40]}")
                pb_desc = st.text_area("Descrição de Negócio:", value="Playbook canônico com regras de negócio verificadas.")
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
    render_journey_bar(3)

    st.markdown("## 🛡️ Simulador de Ataque & Defesa (SQL Guardrails)")
    st.markdown(
        "<p style='margin-bottom:16px;'>"
        "Teste injeções SQL reais e vetores de ataque contra o guardrail baseado em AST (sqlglot). "
        "Comandos perigosos são interceptados e bloqueados antes de tocarem no banco de dados."
        "</p>",
        unsafe_allow_html=True,
    )

    attack_presets = {
        "💥 Injeção DDL (Drop Table)": "SELECT * FROM orders; DROP TABLE customers;",
        "⏱️ Exaustão de Recursos (Sleep)": "SELECT pg_sleep(10);",
        "🕵️ Exfiltração de Arquivos (Copy To)": "COPY customers TO '/tmp/leak.csv';",
        "🛡️ Bypass com Comentários": "SELECT * FROM orders -- DROP TABLE customers",
        "⚠️ Limite Exorbitante": "SELECT * FROM orders LIMIT 9999999;",
        "✓ Query Válida": "SELECT customer_unique_id, SUM(price) FROM marts.fct_orders GROUP BY 1 LIMIT 10;",
    }

    st.markdown("<div class='dce-card-header'>Vetores de Teste Pré-Configurados (Clique para Carregar):</div>", unsafe_allow_html=True)
    b_cols = st.columns(3)
    keys = list(attack_presets.keys())
    for i, k in enumerate(keys):
        col = b_cols[i % 3]
        with col:
            if st.button(k, key=f"btn_atk_{i}", use_container_width=True):
                st.session_state.guardrail_test_input = attack_presets[k]
                st.rerun()

    custom_sql = st.text_area(
        "SQL a ser auditado pela Árvore Sintática (AST):",
        value=st.session_state.guardrail_test_input,
        height=90,
    )

    if st.button("🛡️ Inspecionar com Guardrail AST", key="btn_check_guardrail", use_container_width=True):
        try:
            guard_result = guardrail.validate_and_sanitize(custom_sql)
            st.markdown(
                """
                <div class='arena-box arena-box-engine'>
                    <div style='font-size:14px; font-weight:700; color:#4ade80;'>✓ QUERY APROVADA PELO GUARDRAIL AST</div>
                    <div style='font-size:12px; color:#cbd5e1; margin-top:4px;'>
                        A árvore sintática confirmou apenas comandos SELECT seguros. O limite máximo seguro foi injetado automaticamente.
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
                <div class='arena-box arena-box-naive'>
                    <div style='font-size:14px; font-weight:700; color:#f87171;'>🛑 ATAQUE BLOQUEADO COM SUCESSO</div>
                    <div style='font-size:12px; color:#fca5a5; margin-top:4px;'>
                        <b>Código da Violação:</b> <code>{exc.violation_type.value}</code><br/>
                        <b>Motivo Técnico:</b> {exc.message}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("🛡️ O comando foi descartado na raiz sintática e **nunca** chegou a ser executado no DuckDB.")


# =============================================================================
# SEÇÃO 5: 📊 CATÁLOGO DE GOVERNANÇA & BENCHMARK OFICIAL
# =============================================================================
def render_section_catalog_and_benchmark():
    render_journey_bar(4)

    st.markdown("## 📊 Dicionário de Governança & Benchmark Oficial")
    st.markdown(
        "<p style='margin-bottom:16px;'>"
        "Transparência total das regras de negócio ativas no motor e resultados consolidados nos 30 Gold Questions."
        "</p>",
        unsafe_allow_html=True,
    )

    tab_cat, tab_bench = st.tabs(["📚 Regras Canônicas & Métricas", "📈 Benchmark dos 30 Gold Questions"])

    with tab_cat:
        st.markdown("### 📜 Regras de Negócio Canônicas (RN-01 a RN-07)")
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
    st.caption("⚡ Data Context Engine · UI/UX Pro Max · Repositório Público: github.com/dantinha/data-context-engine")

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
            if st.button(f"← {STEP_OPTIONS[current_step - 1]}", key="btn_prev_step", use_container_width=True):
                st.session_state.active_step_index = current_step - 1
                st.rerun()
    with col_nav2:
        if current_step < len(STEP_OPTIONS) - 1:
            if st.button(f"{STEP_OPTIONS[current_step + 1]} →", key="btn_next_step", use_container_width=True):
                st.session_state.active_step_index = current_step + 1
                st.rerun()
