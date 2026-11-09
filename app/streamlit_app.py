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

from dce.context.assembler import ContextAssembler
from dce.context.clarifier import SemanticClarifier
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.execution.agent import SQLAgent
from dce.execution.executor import SafeSQLExecutor
from dce.execution.guardrails import SQLGuardrail, SQLSecurityViolationError
from dce.models import ContextLevel, MetadataCatalog
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
# Navigation Options & Session State Defaults
# -----------------------------------------------------------------------------
STEP_OPTIONS = [
    "01 · O Desafio dos Dados",
    "02 · O Duelo (L1 vs L4)",
    "03 · Laboratório Interativo",
    "04 · Defesa & Guardrails",
    "05 · Catálogo & Benchmark",
]

VIEW_MODE_OPTIONS = [
    "📱 Scroll Contínuo (Mobile / Página Única)",
    "💻 Passo a Passo Lateral (Desktop)",
]

if "current_question" not in st.session_state:
    st.session_state.current_question = "Quem são os nossos 10 melhores clientes?"
if "input_user_question" not in st.session_state:
    st.session_state.input_user_question = st.session_state.current_question
if "selected_metric_id" not in st.session_state:
    st.session_state.selected_metric_id = "customer_ltv"
if "last_executed_result" not in st.session_state:
    st.session_state.last_executed_result = None
if "active_step_index" not in st.session_state:
    st.session_state.active_step_index = 0
if "sidebar_step_radio" not in st.session_state:
    st.session_state.sidebar_step_radio = STEP_OPTIONS[st.session_state.active_step_index]
if "nav_view_mode" not in st.session_state:
    st.session_state.nav_view_mode = VIEW_MODE_OPTIONS[0]
if "guardrail_test_input" not in st.session_state:
    st.session_state.guardrail_test_input = "SELECT * FROM orders; DROP TABLE customers;"
if "guardrail_sql_area" not in st.session_state:
    st.session_state.guardrail_sql_area = st.session_state.guardrail_test_input
if "duel_last_question" not in st.session_state:
    st.session_state.duel_last_question = None


# -----------------------------------------------------------------------------
# State Synchronization Callbacks
# -----------------------------------------------------------------------------
def _on_sidebar_step_change() -> None:
    """Syncs active_step_index when user clicks the sidebar radio directly."""
    selected = st.session_state.get("sidebar_step_radio")
    if selected in STEP_OPTIONS:
        st.session_state.active_step_index = STEP_OPTIONS.index(selected)


def _navigate_to_step(step_idx: int, force_stepper: bool = False) -> None:
    """Programmatically navigates to a step and keeps sidebar radio in sync."""
    clamped_idx = max(0, min(len(STEP_OPTIONS) - 1, step_idx))
    st.session_state.active_step_index = clamped_idx
    st.session_state.sidebar_step_radio = STEP_OPTIONS[clamped_idx]
    if force_stepper:
        st.session_state.nav_view_mode = VIEW_MODE_OPTIONS[1]


def _set_quick_question(question_text: str, metric_id: str | None = None) -> None:
    """Callback for Workbench quick suggestion pills."""
    st.session_state.current_question = question_text
    st.session_state.input_user_question = question_text
    st.session_state.selected_metric_id = metric_id
    st.session_state.last_executed_result = None


def _use_saved_playbook(question_text: str, metric_id: str | None = None) -> None:
    """Callback for sidebar saved playbook 'Usar' button."""
    st.session_state.current_question = question_text
    st.session_state.input_user_question = question_text
    st.session_state.selected_metric_id = metric_id
    st.session_state.last_executed_result = None
    _navigate_to_step(2, force_stepper=False)


def _set_guardrail_preset(sql_preset: str) -> None:
    """Callback for Guardrail preset buttons."""
    st.session_state.guardrail_test_input = sql_preset
    st.session_state.guardrail_sql_area = sql_preset


# -----------------------------------------------------------------------------
# Sidebar Navigation & Settings
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚡ DATA CONTEXT ENGINE")
    st.markdown(
        "<span class='badge-pill badge-indigo'>v0.1.2 · DuckDB Sandbox</span> "
        "<span class='badge-pill badge-emerald'>Read-Only</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Experience Format
    st.markdown("<div class='dce-card-header'>Formato de Visualização</div>", unsafe_allow_html=True)
    view_mode = st.radio(
        "Modo de Navegação",
        options=VIEW_MODE_OPTIONS,
        key="nav_view_mode",
        label_visibility="collapsed",
    )
    is_scroll_mode = view_mode.startswith("📱")

    if not is_scroll_mode:
        st.markdown(
            "<div class='dce-card-header' style='margin-top:14px;'>Trilha de Aprendizado</div>",
            unsafe_allow_html=True,
        )
        # Keep radio synchronized with active_step_index
        expected_label = STEP_OPTIONS[st.session_state.active_step_index]
        if st.session_state.get("sidebar_step_radio") != expected_label:
            st.session_state.sidebar_step_radio = expected_label

        st.radio(
            "Selecione a Etapa:",
            options=STEP_OPTIONS,
            key="sidebar_step_radio",
            on_change=_on_sidebar_step_change,
            label_visibility="collapsed",
        )

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
            col_pb1, col_pb2 = st.columns([0.70, 0.30])
            with col_pb1:
                st.markdown(f"**{pb.title}**")
                st.caption(f"`{pb.resolved_metric_id or 'geral'}`")
            with col_pb2:
                st.button(
                    "Usar",
                    key=f"btn_pb_{pb.id}",
                    on_click=_use_saved_playbook,
                    args=(pb.question, pb.resolved_metric_id),
                )

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
# TOP JOURNEY PROGRESS BAR & INTERACTIVE STEPPER
# =============================================================================
def render_journey_bar(active_index: int) -> None:
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
def render_section_challenge(section_key_prefix: str = "s1") -> None:
    render_journey_bar(0)

    st.markdown(
        """
        <div class='dce-card-hero'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;'>
                <span class='badge-pill badge-indigo'>Engenharia de Contexto Analítico</span>
                <span style='font-family:JetBrains Mono; font-size:12px; color:#64748b;'>DUCKDB · AST GUARDRAILS · PREFIX CACHING</span>
            </div>
            <h1 style='font-size:32px; margin-bottom:8px;'>Data Context Engine</h1>
            <p style='font-size:16px; color:#cbd5e1; margin-bottom:18px;'>
                Por que modelos de Inteligência Artificial erram <b>60% das consultas de dados</b> quando recebem apenas o schema bruto — e como uma camada de contexto semântico e guardrails AST resolve isso com precisão auditável.
            </p>
            <div style='display:flex; gap:12px; flex-wrap:wrap;'>
                <span class='badge-pill badge-zinc'>30/30 Gold Tests</span>
                <span class='badge-pill badge-emerald'>-61.3% Redução de Tokens</span>
                <span class='badge-pill badge-amber'>90.0% Acurácia c/ Autocorreção</span>
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
                LLMs modernos dominam a sintaxe do SQL. Porém, quando conectados a bancos de dados reais (como este warehouse do e-commerce brasileiro Olist), eles caem em armadilhas silenciosas de negócio:
            </p>
            <div style='display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:12px; margin-top:14px;'>
                <div style='background:#181d28; padding:12px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);'>
                    <div style='font-weight:700; color:#f87171; font-size:13px;'>1. O Faturamento Fantasma (RN-02)</div>
                    <div style='font-size:12px; color:#94a3b8; margin-top:4px;'>
                        A IA soma pedidos cancelados e indisponíveis, inflando a receita contábil da empresa em mais de R$ 47 mil.
                    </div>
                </div>
                <div style='background:#181d28; padding:12px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);'>
                    <div style='font-weight:700; color:#fbbf24; font-size:13px;'>2. A Armadilha do Cliente (RN-01)</div>
                    <div style='font-size:12px; color:#94a3b8; margin-top:4px;'>
                        Agrupa por <code>customer_id</code> (chave efêmera por pedido) em vez de <code>customer_unique_id</code>, destruindo a análise de LTV e recompra.
                    </div>
                </div>
                <div style='background:#181d28; padding:12px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.05);'>
                    <div style='font-weight:700; color:#38bdf8; font-size:13px;'>3. Fan-Out de Frete e Pagamentos (RN-03)</div>
                    <div style='font-size:12px; color:#94a3b8; margin-top:4px;'>
                        Faz JOIN direto entre itens e pagamentos sem pré-agregar, multiplicando valores em pedidos com múltiplos itens.
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🪜 A Escala de Evolução de Contexto (`L0` a `L4`)")
    st.markdown(
        "Para eliminar alucinações e reduzir o consumo de tokens, o motor estrutura o contexto em 5 níveis progressivos testados no Benchmark Oficial:"
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-zinc'>L0 · Sem Contexto</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Zero-Shot Guessing</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Apenas a pergunta em linguagem natural (~42 tokens). A I.A chuta nomes de tabelas inexistentes.<br/>
                    <b style='color:#f87171;'>Acurácia Final: 20.0% (6/30)</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-rose'>L1 · Naive Schema Dump</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Despejo Bruto de DDLs</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Despeja todas as tabelas brutas (~2.094 tokens, 0% cacheável). A I.A se perde em joins e ignora regras.<br/>
                    <b style='color:#fbbf24;'>Acurácia Final: 40.0% (12/30)</b>
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
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Marts Curados + Pruning</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Seleciona apenas fatos e dimensões relevantes (~592 tokens) com descrições semânticas.<br/>
                    <b style='color:#fcd34d;'>Acurácia Final: 60.0% (18/30)</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class='dce-card'>
                <span class='badge-pill badge-indigo'>L3 · Roteamento Semântico</span>
                <div style='font-size:14px; font-weight:700; margin-top:8px;'>Métricas + Grafo de Joins</div>
                <div style='font-size:12px; color:#94a3b8; margin-top:6px;'>
                    Injeta métricas YAML, regras de negócio RN-01..RN-07 e caminhos de JOIN seguros (~735 tokens).<br/>
                    <b style='color:#a5b4fc;'>Acurácia Final: 76.7% (23/30)</b>
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
                <div style='font-size:14px; font-weight:700; color:#f8fafc; margin-top:8px;'>Engenharia de Contexto Completa</div>
                <div style='font-size:12px; color:#cbd5e1; margin-top:6px; line-height:1.55;'>
                    • <b>Prefix Caching (62.8%):</b> Economia de <b>61.3%</b> dos tokens vs L1.<br/>
                    • <b>Few-Shot Dinâmico + Playbooks:</b> Exemplos verificados.<br/>
                    • <b>Clarifier + AST Guardrail:</b> Desambiguação e defesa SQL.<br/>
                    <b style='color:#34d399;'>Acurácia Final: 90.0% (27/30)</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.button(
        "👉 Ver a I.A falhando no L1 e acertando no L4 (Ir para O Duelo)",
        key=f"{section_key_prefix}_btn_goto_duel",
        on_click=_navigate_to_step,
        args=(1, True),
    )


# =============================================================================
# SEÇÃO 2: ⚖️ O DUELO L1 VS L4 (PROVA IMEDIATA)
# =============================================================================
def render_section_duel(section_key_prefix: str = "s2") -> None:
    render_journey_bar(1)

    st.markdown("## ⚖️ O Duelo: `L1 Naive Dump` vs `L4 Context Engine`")
    st.markdown(
        "<p style='margin-bottom:18px;'>"
        "Compare em tempo real no DuckDB como o despejo bruto de tabelas (<b>L1</b>) consome mais tokens e erra a regra de negócio, "
        "enquanto o <b>L4 Data Context Engine</b> aplica a métrica canônica com <b>61% menos tokens</b>."
        "</p>",
        unsafe_allow_html=True,
    )

    duel_cases = {
        "Qual o faturamento total da empresa?": {
            "trap": "Armadilha RN-02: Pedidos cancelados/indisponíveis não devem compor receita líquida.",
            "metric_id": "net_revenue",
            "l1_flaw": "Soma a tabela bruta `raw.olist_order_payments_dataset` inteira (R$ 364.484,72), incluindo pedidos cancelados e boletos não liquidados.",
            "l4_win": "Filtra estritamente `order_status = 'delivered'` em `marts.fct_orders` (R$ 317.470,99), evitando R$ 47.013,73 de faturamento fantasma.",
        },
        "Quem são os nossos 10 melhores clientes?": {
            "trap": "Armadilha RN-01: Agrupamento por chave transacional efêmera (`customer_id`) vs cliente único (`customer_unique_id`).",
            "metric_id": "customer_ltv",
            "l1_flaw": "Agrupa por `customer_id` na tabela bruta, onde cada pedido gera um ID novo — todos os clientes aparecem com apenas 1 pedido.",
            "l4_win": "Agrupa por `customer_unique_id` em `marts.dim_customers` com `delivered_orders > 0`, identificando clientes fiéis com até 3 compras e LTV real.",
        },
        "Quantos clientes únicos realizaram compras em 2017?": {
            "trap": "Armadilha RN-01 + RN-02: Contagem de clientes sem `DISTINCT customer_unique_id` e sem filtrar entregas.",
            "metric_id": None,
            "l1_flaw": "Usa `COUNT(customer_id)` sem `DISTINCT` e sem filtrar cancelados na tabela `raw.olist_orders_dataset`.",
            "l4_win": "Executa `COUNT(DISTINCT customer_unique_id)` apenas em pedidos entregues (`order_status = 'delivered'`) no ano de 2017.",
        },
        "Qual o valor médio do frete por estado?": {
            "trap": "Armadilha RN-04: Cálculo de frete no nível de item sem consolidar por pedido entregue.",
            "metric_id": None,
            "l1_flaw": "Faz JOIN direto entre tabelas brutas de itens, pedidos e clientes sem filtrar `order_status = 'delivered'`.",
            "l4_win": "Calcula a média de `total_freight_value` consolidada por pedido entregue em `marts.fct_orders` cruzada com `marts.dim_customers`.",
        },
    }

    col_sel, col_btn = st.columns([0.72, 0.28])
    with col_sel:
        compare_question = st.selectbox(
            "Selecione um cenário de teste com armadilha analítica:",
            options=list(duel_cases.keys()),
            index=0,
            key=f"{section_key_prefix}_duel_question_selector",
        )
        case_meta = duel_cases[compare_question]
        st.caption(f"🎯 **Cenário:** {case_meta['trap']}")

    with col_btn:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        run_duel = st.button("⚡ Executar Duelo Agora", key=f"{section_key_prefix}_btn_run_duel")

    # Auto-execute on first load or when scenario changes or button clicked
    if (
        run_duel
        or st.session_state.get("duel_last_question") != compare_question
        or "compare_l1" not in st.session_state
        or "compare_l4" not in st.session_state
    ):
        res_l1 = agent.run_turn(compare_question, level=ContextLevel.L1, replay_only=True)
        res_l4 = agent.run_turn(
            compare_question,
            level=ContextLevel.L4,
            selected_metric_id=case_meta["metric_id"],
            replay_only=True,
        )
        st.session_state.compare_l1 = res_l1
        st.session_state.compare_l4 = res_l4
        st.session_state.duel_last_question = compare_question

    c_l1 = st.session_state.compare_l1
    c_l4 = st.session_state.compare_l4

    col_comp1, col_comp2 = st.columns(2, gap="medium")

    with col_comp1:
        l1_tokens = c_l1.assembled_context.inspection.assembled_context_tokens
        st.markdown(
            f"""
            <div class='arena-box arena-box-naive'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span class='badge-pill badge-rose'>❌ L1 · Naive Schema Dump</span>
                    <span style='font-family:JetBrains Mono; font-size:12px; color:#f87171;'>{l1_tokens} TOKENS</span>
                </div>
                <div style='font-size:12px; color:#cbd5e1; margin-top:8px;'>
                    Despeja todas as tabelas brutas sem semântica. A I.A ignora regras de negócio.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"**Tokens do Prompt:** `{l1_tokens}` (0% economia)")
        st.markdown("**Prefix Cacheável:** `0.0%`")
        st.markdown("**SQL Gerado (L1):**")
        st.code(c_l1.generated_sql.sanitized_sql or c_l1.generated_sql.raw_sql, language="sql")
        st.markdown("**Resultado no DuckDB (L1):**")
        if c_l1.execution_result.rows:
            st.dataframe(
                pd.DataFrame(c_l1.execution_result.rows, columns=c_l1.execution_result.columns).head(5),
                hide_index=True,
            )
        st.caption(f"⚠️ **Erro Analítico Detectado:** {case_meta['l1_flaw']}")

    with col_comp2:
        l4_tokens = c_l4.assembled_context.inspection.assembled_context_tokens
        savings_pct = c_l4.assembled_context.inspection.token_savings_pct
        cache_pct = c_l4.assembled_context.inspection.prefix_cacheable_pct
        st.markdown(
            f"""
            <div class='arena-box arena-box-engine'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <span class='badge-pill badge-emerald'>✓ L4 · Data Context Engine</span>
                    <span style='font-family:JetBrains Mono; font-size:12px; color:#34d399;'>{l4_tokens} TOKENS (-{savings_pct:.1f}%)</span>
                </div>
                <div style='font-size:12px; color:#cbd5e1; margin-top:8px;'>
                    Marts analíticos + Regras Canônicas + AST Guardrails + Prefix Caching.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**Tokens do Prompt:** `{l4_tokens}` "
            f"<span class='badge-pill badge-emerald'>-{savings_pct:.1f}% vs L1</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Prefix Cacheável:** `{cache_pct:.1f}%`")
        st.markdown("**SQL Gerado (L4):**")
        st.code(c_l4.generated_sql.sanitized_sql or c_l4.generated_sql.raw_sql, language="sql")
        st.markdown("**Resultado no DuckDB (L4):**")
        if c_l4.execution_result.rows:
            st.dataframe(
                pd.DataFrame(c_l4.execution_result.rows, columns=c_l4.execution_result.columns).head(5),
                hide_index=True,
            )
        st.caption(f"✓ **Precisão Contábil Garantida:** {case_meta['l4_win']}")


# =============================================================================
# SEÇÃO 3: 🔬 LABORATÓRIO INTERATIVO (WORKBENCH ANALÍTICO)
# =============================================================================
def render_section_workbench(section_key_prefix: str = "s3") -> None:
    render_journey_bar(2)

    st.markdown("## 🔬 Laboratório Interativo (Workbench Analítico)")
    st.markdown(
        "<p style='margin-bottom:16px;'>"
        "Execute consultas em linguagem natural contra o warehouse DuckDB. "
        "Teste o <b>Semantic Clarifier</b> (que detecta perguntas ambíguas antes de gerar SQL), inspecione o prompt compilado e salve Playbooks verificados."
        "</p>",
        unsafe_allow_html=True,
    )

    # Categories Quick Pills
    st.markdown("<div class='dce-card-header'>Sugestões Rápidas por Domínio (Clique para Carregar e Executar):</div>", unsafe_allow_html=True)
    pill_c1, pill_c2, pill_c3, pill_c4 = st.columns(4)
    with pill_c1:
        st.button(
            "🛒 Top 10 Clientes (LTV)",
            key=f"{section_key_prefix}_pill_clients",
            on_click=_set_quick_question,
            args=("Quem são os nossos 10 melhores clientes?", "customer_ltv"),
        )
    with pill_c2:
        st.button(
            "💰 Faturamento Líquido",
            key=f"{section_key_prefix}_pill_rev",
            on_click=_set_quick_question,
            args=("Qual o faturamento total da empresa?", "net_revenue"),
        )
    with pill_c3:
        st.button(
            "🚚 SLA de Entrega em SP",
            key=f"{section_key_prefix}_pill_sla",
            on_click=_set_quick_question,
            args=("Qual o tempo médio de entrega dos pedidos em São Paulo?", "delivery_delay_rate"),
        )
    with pill_c4:
        st.button(
            "🏆 Melhores Vendedores",
            key=f"{section_key_prefix}_pill_sellers",
            on_click=_set_quick_question,
            args=("Quem são os nossos melhores vendedores?", "seller_revenue"),
        )

    user_input = st.text_input(
        "Pergunta Analítica em Linguagem Natural:",
        key="input_user_question",
    )
    st.session_state.current_question = user_input

    # Semantic Clarification Check
    clarification = clarifier.analyze(user_input)
    if clarification.needs_clarification:
        msg = (
            clarification.message
            or clarification.clarification_message
            or "A pergunta contém termos ambíguos de negócio."
        )
        group_id = clarification.ambiguity_group_id or "MÉTRICA AMBÍGUA"
        st.markdown(
            f"""
            <div class='clarification-box'>
                <div style='font-weight:700; color:#fbbf24; font-size:13px; margin-bottom:4px;'>
                    ⚠️ Desambiguação Semântica Ativa ({group_id.upper()})
                </div>
                <div style='font-size:13.5px; color:#e2e8f0;'>
                    {msg}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if clarification.options:
            metric_options = {
                opt.metric_id: f"{opt.label} ({opt.metric_id}) — {opt.description}"
                for opt in clarification.options
            }
            option_keys = list(metric_options.keys())
            default_idx = (
                option_keys.index(st.session_state.selected_metric_id)
                if st.session_state.selected_metric_id in option_keys
                else 0
            )
            selected_metric = st.radio(
                "Selecione a definição canônica desejada para compilar o SQL:",
                options=option_keys,
                index=default_idx,
                format_func=lambda x: metric_options[x],
                horizontal=False,
                key=f"{section_key_prefix}_radio_metric_choice",
            )
            st.session_state.selected_metric_id = selected_metric
    else:
        st.session_state.selected_metric_id = clarification.resolved_metric_id

    run_wb = st.button("🚀 Executar Consulta no DuckDB", key=f"{section_key_prefix}_btn_run_workbench")

    # Auto-execute if no result cached yet or if user clicked execute or changed parameters
    current_sig = f"{user_input}|{current_level.value}|{st.session_state.selected_metric_id}|{replay_only}"
    if run_wb or st.session_state.last_executed_result is None or st.session_state.get("wb_last_sig") != current_sig:
        result = agent.run_turn(
            user_input,
            level=current_level,
            selected_metric_id=st.session_state.selected_metric_id,
            replay_only=replay_only,
        )
        st.session_state.last_executed_result = result
        st.session_state.wb_last_sig = current_sig

    # Display Execution Results
    if st.session_state.last_executed_result:
        res = st.session_state.last_executed_result

        # Metrics Bar
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"""
                <div class='dce-card'>
                    <div class='dce-card-header'>Tokens do Contexto ({res.context_level.value})</div>
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
                    <div style='font-size:12px; color:#64748b;'>{res.execution_result.execution_time_ms:.1f}ms no DuckDB</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m4:
            status_txt = "Aprovado" if res.execution_result.success else "Bloqueado/Erro"
            status_color = "#34d399" if res.execution_result.success else "#f87171"
            st.markdown(
                f"""
                <div class='dce-card'>
                    <div class='dce-card-header'>Guardrail AST</div>
                    <div class='dce-metric-value' style='color:{status_color};'>{status_txt}</div>
                    <div style='font-size:12px; color:#64748b;'>Tentativas de Correção: {res.correction_attempts}</div>
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
                st.error(f"Erro na execução ({res.context_level.value}): {res.execution_result.error_message}")
            elif res.execution_result.rows:
                df = pd.DataFrame(res.execution_result.rows, columns=res.execution_result.columns)
                st.dataframe(df, height=280, hide_index=True)
            else:
                st.info("A consulta executou com sucesso, mas retornou 0 linhas.")

        with tab_sql:
            st.code(res.generated_sql.sanitized_sql or res.generated_sql.raw_sql, language="sql")
            tables_list = res.execution_result.tables_referenced or res.generated_sql.tables_used or ["N/A"]
            st.caption(
                f"**Tabelas referenciadas:** `{', '.join(tables_list)}` · "
                f"**Limite de Segurança:** `{res.execution_result.limit_applied or 1000}` · "
                f"**Raciocínio:** {res.generated_sql.reasoning}"
            )
            if res.execution_result.governance_warnings:
                for w in res.execution_result.governance_warnings:
                    st.warning(f"⚠️ Governança: {w}")

        with tab_context:
            insp = res.assembled_context.inspection
            st.markdown(
                f"**Nível Compilado:** `{res.context_level.value}` · "
                f"**Prefixo Estático:** `{insp.static_prefix_tokens} tokens` · "
                f"**Sufixo Dinâmico:** `{insp.dynamic_suffix_tokens} tokens` · "
                f"**Regras Injetadas:** `{', '.join(insp.selected_rules) or 'Nenhuma'}`"
            )
            st.text_area(
                "Prompt Completo Enviado ao Agente (Prefixo Estático + Sufixo Dinâmico):",
                value=res.assembled_context.full_prompt,
                height=240,
                disabled=True,
                key=f"{section_key_prefix}_ctx_prompt_view",
            )

        with tab_save:
            st.markdown("Salve esta consulta auditada no `PlaybookStore` para reutilização imediata pela equipe:")
            with st.form(f"{section_key_prefix}_form_save_playbook"):
                pb_title = st.text_input("Título do Playbook:", value=f"Análise: {user_input[:45]}")
                pb_tags = st.text_input("Tags (separadas por vírgula):", value="workbench, verificado")
                submitted = st.form_submit_button("💾 Salvar no PlaybookStore")
                if submitted:
                    try:
                        tag_list = [t.strip() for t in pb_tags.split(",") if t.strip()]
                        saved_pb = store.save_playbook(
                            title=pb_title,
                            question=user_input,
                            sql_query=res.generated_sql.sanitized_sql or res.generated_sql.raw_sql,
                            resolved_metric_id=st.session_state.selected_metric_id,
                            tags=tag_list,
                        )
                        st.success(f"✓ Playbook '{saved_pb.title}' (`{saved_pb.id}`) salvo e indexado com sucesso!")
                    except (ValueError, SQLSecurityViolationError) as err:
                        st.error(f"Não foi possível salvar o playbook: {err}")


# =============================================================================
# SEÇÃO 4: 🛡️ SIMULADOR DE ATAQUE & DEFESA (GUARDRAILS)
# =============================================================================
def render_section_guardrails(section_key_prefix: str = "s4") -> None:
    render_journey_bar(3)

    st.markdown("## 🛡️ Simulador de Ataque & Defesa (SQL Guardrails AST)")
    st.markdown(
        "<p style='margin-bottom:16px;'>"
        "Teste injeções SQL reais e vetores de ataque contra o guardrail baseado em Árvore Sintática Abstrata (<code>sqlglot</code>). "
        "Clique em qualquer vetor abaixo ou digite seu próprio comando SQL para inspecionar a defesa."
        "</p>",
        unsafe_allow_html=True,
    )

    attack_presets = {
        "💥 Injeção Multi-Statement (SEC-01)": "SELECT * FROM marts.fct_orders; DROP TABLE marts.dim_customers;",
        "🛑 Mutação DDL/DML (SEC-02)": "DELETE FROM marts.fct_orders WHERE order_status = 'canceled';",
        "🕵️ Exfiltração de Arquivo (SEC-03)": "SELECT * FROM read_csv_auto('/etc/passwd');",
        "⏱️ Função Proibida / DoS (SEC-03)": "SELECT pg_sleep(10);",
        "⚠️ Limite Exorbitante + Raw Schema (SEC-04/05)": "SELECT * FROM raw.olist_orders_dataset LIMIT 9999999;",
        "✓ Query Analítica Segura (Marts)": "SELECT customer_unique_id, SUM(total_payment_value) AS total_spent FROM marts.fct_orders WHERE order_status = 'delivered' GROUP BY 1 LIMIT 10;",
    }

    st.markdown(
        "<div class='dce-card-header'>Vetores de Teste Pré-Configurados (Clique para Testar Instantaneamente):</div>",
        unsafe_allow_html=True,
    )
    b_cols = st.columns(3)
    keys = list(attack_presets.keys())
    for i, k in enumerate(keys):
        col = b_cols[i % 3]
        with col:
            st.button(
                k,
                key=f"{section_key_prefix}_btn_atk_{i}",
                on_click=_set_guardrail_preset,
                args=(attack_presets[k],),
            )

    custom_sql = st.text_area(
        "SQL a ser auditado pela Árvore Sintática (AST):",
        key="guardrail_sql_area",
        height=95,
    )
    st.session_state.guardrail_test_input = custom_sql

    st.button("🛡️ Inspecionar com Guardrail AST", key=f"{section_key_prefix}_btn_check_guardrail")

    # Always inspect and show live verdict so user gets immediate feedback
    try:
        guard_result = guardrail.validate_and_rewrite(custom_sql)
        st.markdown(
            """
            <div class='arena-box arena-box-engine'>
                <div style='font-size:14px; font-weight:700; color:#4ade80;'>✓ QUERY APROVADA PELO GUARDRAIL AST</div>
                <div style='font-size:12px; color:#cbd5e1; margin-top:4px;'>
                    A árvore sintática confirmou statement único de leitura (SELECT), sem funções de I/O externas e com LIMIT seguro aplicado.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("**SQL Sanitizado e Reescrito para o DuckDB:**")
        st.code(guard_result.sanitized_sql, language="sql")
        st.caption(
            f"**Tabelas referenciadas:** `{', '.join(guard_result.tables_referenced) or 'Nenhuma'}` · "
            f"**CTEs isoladas:** `{', '.join(guard_result.cte_names) or 'Nenhuma'}` · "
            f"**Limite máximo aplicado (SEC-05):** `{guard_result.limit_applied}`"
        )
        if guard_result.governance_warnings:
            for warning_msg in guard_result.governance_warnings:
                st.warning(f"⚠️ **Alerta de Governança (SEC-04):** {warning_msg}")
    except SQLSecurityViolationError as exc:
        st.markdown(
            f"""
            <div class='arena-box arena-box-naive'>
                <div style='font-size:14px; font-weight:700; color:#f87171;'>🛑 ATAQUE BLOQUEADO NA ÁRVORE SINTÁTICA (AST)</div>
                <div style='font-size:12.5px; color:#fca5a5; margin-top:6px; line-height:1.5;'>
                    <b>Regra Acionada:</b> <code>{exc.code}</code><br/>
                    <b>Diagnóstico Técnico:</b> {exc.message}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("🛡️ O comando malicioso foi interceptado pelo parser `sqlglot` antes de tocar na conexão DuckDB.")


# =============================================================================
# SEÇÃO 5: 📊 CATÁLOGO DE GOVERNANÇA & BENCHMARK OFICIAL
# =============================================================================
def render_section_catalog_and_benchmark(section_key_prefix: str = "s5") -> None:
    render_journey_bar(4)

    st.markdown("## 📊 Dicionário de Governança & Benchmark Oficial")
    st.markdown(
        "<p style='margin-bottom:16px;'>"
        "Transparência total das regras de negócio ativas no catálogo YAML e resultados auditáveis nos 30 Gold Questions."
        "</p>",
        unsafe_allow_html=True,
    )

    tab_cat, tab_bench = st.tabs(["📚 Regras Canônicas & Métricas", "📈 Benchmark dos 30 Gold Questions"])

    with tab_cat:
        st.markdown("### 📜 Regras de Negócio Canônicas (`RN-01` a `RN-07`)")
        rules_data = [
            {
                "ID": r.id,
                "Regra": r.name,
                "Descrição de Negócio": r.description,
                "Condição SQL Canônica": r.rule_sql_condition or "",
            }
            for r in catalog.business_rules
        ]
        st.dataframe(pd.DataFrame(rules_data), hide_index=True)

        st.markdown("### 📐 Métricas Semânticas Certificadas")
        metrics_data = [
            {
                "ID": m.id,
                "Métrica": m.name,
                "Expressão SQL Canônica": m.canonical_sql,
                "Tabela Base": m.base_table,
                "Filtros Obrigatórios": ", ".join(m.filters_required) if m.filters_required else "Embutido na tabela",
            }
            for m in catalog.metrics
        ]
        st.dataframe(pd.DataFrame(metrics_data), hide_index=True)

    with tab_bench:
        st.markdown("### 🏆 Evolução de Acurácia nos 30 Gold Questions (`L0` → `L4`)")
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
                    "Economia vs L1": f"{item.get('token_savings_pct', 0.0):.1f}%",
                    "Prefix Cacheável": f"{item.get('prefix_cacheable_pct', 0.0):.1f}%",
                    "Acertos Finais": f"{item['correct_with_correction']}/30",
                })

            df_summary = pd.DataFrame(summary_rows)
            st.dataframe(df_summary, hide_index=True)

            chart_df = pd.DataFrame({
                "Nível": [r["Nível"] for r in summary_rows],
                "Acurácia (%)": [float(r["Acurácia c/ Autocorreção"].replace("%", "")) for r in summary_rows],
            }).set_index("Nível")
            st.bar_chart(chart_df, color="#6366f1")
            st.caption("✓ O Context Engine (L4) atinge 90.0% de acurácia final (27/30) reduzindo o consumo de tokens em 61.3% em relação ao L1.")
        else:
            st.info("Arquivo de resultados do benchmark não encontrado em results/benchmark_summary.json.")


# -----------------------------------------------------------------------------
# Main Application Router (Scroll Contínuo vs Passo a Passo Lateral)
# -----------------------------------------------------------------------------
if is_scroll_mode:
    # 📱 Experiência de Scrollagem Vertical Direta (Mobile-First)
    render_section_challenge("scroll_s1")

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_duel("scroll_s2")

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_workbench("scroll_s3")

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_guardrails("scroll_s4")

    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    render_section_catalog_and_benchmark("scroll_s5")

    st.markdown("---")
    st.caption("⚡ Data Context Engine · UI/UX Pro Max · Repositório Público: github.com/dantinha/data-context-engine")

else:
    # 💻 Experiência Lateral Passo a Passo (Desktop Stepper)
    current_step = st.session_state.active_step_index

    # Interactive Quick Stepper Bar at Top of Desktop View
    step_cols = st.columns(len(STEP_OPTIONS))
    for idx, step_label in enumerate(STEP_OPTIONS):
        with step_cols[idx]:
            btn_label = f"● {step_label}" if idx == current_step else step_label
            st.button(
                btn_label,
                key=f"top_step_btn_{idx}",
                on_click=_navigate_to_step,
                args=(idx, False),
            )

    # Render Active Section
    if current_step == 0:
        render_section_challenge("step_s1")
    elif current_step == 1:
        render_section_duel("step_s2")
    elif current_step == 2:
        render_section_workbench("step_s3")
    elif current_step == 3:
        render_section_guardrails("step_s4")
    elif current_step == 4:
        render_section_catalog_and_benchmark("step_s5")

    # Step Stepper Navigation Footer
    st.markdown("<div class='step-banner'></div>", unsafe_allow_html=True)
    col_nav1, col_nav2 = st.columns([0.5, 0.5])
    with col_nav1:
        if current_step > 0:
            st.button(
                f"← Passo Anterior: {STEP_OPTIONS[current_step - 1]}",
                key="btn_prev_step",
                on_click=_navigate_to_step,
                args=(current_step - 1, False),
            )
    with col_nav2:
        if current_step < len(STEP_OPTIONS) - 1:
            st.button(
                f"Próximo Passo: {STEP_OPTIONS[current_step + 1]} →",
                key="btn_next_step",
                on_click=_navigate_to_step,
                args=(current_step + 1, False),
            )

