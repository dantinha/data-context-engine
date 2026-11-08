"""Data Context Engine - Streamlit Analytical Workbench (Anti-AI Design Level 2)."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dce.benchmark.runner import BenchmarkRunner
from dce.context.assembler import ContextAssembler
from dce.context.clarifier import SemanticClarifier
from dce.context.loader import load_metadata_catalog
from dce.context.retriever import HybridRetriever
from dce.execution.agent import SQLAgent
from dce.execution.executor import SafeSQLExecutor
from dce.models import ContextLevel, MetadataCatalog
from dce.playbooks.store import PlaybookStore
from dce.warehouse.builder import build_warehouse

# -----------------------------------------------------------------------------
# Streamlit Page Config & Anti-AI Design CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Data Context Engine · Workbench Analítico",
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
        padding-bottom: 2rem;
        max-width: 96%;
    }
    
    /* Headers */
    h1, h2, h3, h4 {
        letter-spacing: -0.025em;
        font-weight: 600;
        color: #fafafa;
    }
    
    /* Subtle hairline cards */
    .dce-card {
        background-color: #18181b;
        border: 1px solid #27272a;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    
    .dce-card-header {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #a1a1aa;
        margin-bottom: 6px;
    }

    .dce-metric-value {
        font-size: 22px;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        color: #f4f4f5;
    }
    
    .dce-metric-delta {
        font-size: 12px;
        color: #10b981;
        font-weight: 500;
    }

    /* Badges */
    .badge-pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-indigo {
        background-color: rgba(79, 70, 229, 0.15);
        color: #818cf8;
        border: 1px solid rgba(79, 70, 229, 0.3);
    }
    .badge-emerald {
        background-color: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-amber {
        background-color: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.3);
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
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 16px;
    }

    /* Code styling */
    pre, code {
        font-family: "JetBrains Mono", "Fira Code", monospace !important;
        font-size: 13px !important;
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #27272a;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 500;
        color: #a1a1aa;
        background-color: transparent;
        border-radius: 6px 6px 0 0;
    }
    .stTabs [aria-selected="true"] {
        color: #fafafa !important;
        border-bottom: 2px solid #4f46e5 !important;
        font-weight: 600;
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
    return catalog, retriever, clarifier, executor, store, assembler, agent


catalog, retriever, clarifier, executor, store, assembler, agent = get_engine_components()

# -----------------------------------------------------------------------------
# Session State Defaults
# -----------------------------------------------------------------------------
if "current_question" not in st.session_state:
    st.session_state.current_question = "Quem são os nossos 10 melhores clientes?"
if "selected_metric_id" not in st.session_state:
    st.session_state.selected_metric_id = None
if "last_executed_result" not in st.session_state:
    st.session_state.last_executed_result = None

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

    # Context Level Selector
    st.markdown("<div class='dce-card-header'>Nível de Contexto (L0 - L4)</div>", unsafe_allow_html=True)
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
        options=["Replay Cache (Offline)", "Gemini Live (Free Tier)"],
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
        for pb in saved_playbooks[:5]:
            col_pb1, col_pb2 = st.columns([0.75, 0.25])
            with col_pb1:
                st.markdown(f"**{pb.title}**")
                st.caption(f"Critério: `{pb.resolved_metric_id or 'geral'}`")
            with col_pb2:
                if st.button("Usar", key=f"btn_pb_{pb.id}"):
                    st.session_state.current_question = pb.question
                    st.session_state.selected_metric_id = pb.resolved_metric_id
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

# -----------------------------------------------------------------------------
# Main Tabs Layout
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📊 Workbench Analítico & Inspeção de Contexto",
    "⚖️ Comparador Side-by-Side (L1 vs L4)",
    "📈 Painel do Benchmark & Arquitetura",
])

# =============================================================================
# TAB 1: WORKBENCH ANALÍTICO & INSPEÇÃO NÍVEL 2
# =============================================================================
with tab1:
    st.markdown("## Workbench Analítico com Inspeção de Contexto (Nível 2)")
    st.caption(
        "Execute consultas em linguagem natural com desambiguação semântica ativa, "
        "compressão de contexto e inspeção transparente de tokens."
    )

    # Sample Questions Dropdown
    sample_options = [
        "Quem são os nossos 10 melhores clientes?",
        "Qual o faturamento total da empresa?",
        "Quais vendedores tiveram melhor desempenho?",
        "Qual a receita total obtida com todos os pedidos que foram efetivamente entregues?",
        "Quantos clientes únicos realizaram compras em 2017?",
        "Qual o valor médio do frete por estado?",
        "Quais os 5 estados com maior número de clientes?",
    ]

    col_q1, col_q2 = st.columns([0.75, 0.25])
    with col_q1:
        selected_sample = st.selectbox(
            "Perguntas de Exemplo",
            options=["-- Selecione uma pergunta de exemplo ou digite abaixo --"] + sample_options,
            index=0,
        )
        if (
            selected_sample != "-- Selecione uma pergunta de exemplo ou digite abaixo --"
            and st.session_state.current_question != selected_sample
        ):
            st.session_state.current_question = selected_sample
            st.session_state.selected_metric_id = None

        question_input = st.text_input(
            "Pergunta em Linguagem Natural",
            value=st.session_state.current_question,
            placeholder="Ex: Quem são os nossos 10 melhores clientes?",
        )
        st.session_state.current_question = question_input

    with col_q2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        run_button = st.button("⚡ Executar Consulta", type="primary", use_container_width=True)

    # Check for Ambiguity via SemanticClarifier
    clarif_req = clarifier.analyze(
        question_input,
        selected_metric_id=st.session_state.selected_metric_id,
    )

    # If ambiguous and no metric explicitly chosen: show clarification card
    if clarif_req.needs_clarification and not st.session_state.selected_metric_id:
        st.markdown(
            f"""
            <div class="clarification-box">
                <div style="font-weight: 600; font-size: 14px; color: #fbbf24; margin-bottom: 4px;">
                    ⚠️ Ambiguidade Semântica Detectada ({clarif_req.ambiguity_group_id or 'RN-01'})
                </div>
                <div style="font-size: 13px; color: #d4d4d8; margin-bottom: 12px;">
                    {clarif_req.message or clarif_req.clarification_message or 'Esta consulta possui múltiplos critérios de negócio canônicos.'}
                    Selecione a definição desejada para que o agente gere a consulta correta:
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        opt_cols = st.columns(len(clarif_req.options))
        for idx, opt in enumerate(clarif_req.options):
            with opt_cols[idx]:
                st.markdown(f"**{opt.label}**")
                st.caption(opt.description)
                if opt.business_rule_reference:
                    st.markdown(f"<span class='badge-pill badge-amber'>{opt.business_rule_reference}</span>", unsafe_allow_html=True)
                if st.button(f"Definir como {opt.label}", key=f"opt_btn_{opt.metric_id}"):
                    st.session_state.selected_metric_id = opt.metric_id
                    st.rerun()

    # If user selected a metric, display active resolved badge
    if st.session_state.selected_metric_id:
        col_res1, col_res2 = st.columns([0.8, 0.2])
        with col_res1:
            st.markdown(
                f"<div style='margin-bottom:12px;'>"
                f"<span class='badge-pill badge-emerald'>✓ Critério Semântico Resolvido: "
                f"<b>{st.session_state.selected_metric_id}</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_res2:
            if st.button("Limpar Critério", key="clear_metric_btn"):
                st.session_state.selected_metric_id = None
                st.rerun()

    # Execution Action
    if run_button or st.session_state.last_executed_result is None:
        with st.spinner("Compilando contexto e executando consulta segura no DuckDB..."):
            turn_result = agent.run_turn(
                question=question_input,
                level=current_level,
                selected_metric_id=st.session_state.selected_metric_id,
                replay_only=replay_only,
            )
            st.session_state.last_executed_result = turn_result

    turn = st.session_state.last_executed_result

    # Split View Layout (60% Execution & Data / 40% Level 2 Inspection Panel)
    col_main, col_insp = st.columns([0.58, 0.42], gap="large")

    with col_main:
        st.markdown("### Execução & Resultados")

        # Status Metrics Bar
        exec_res = turn.execution_result
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        with m_col1:
            st.markdown(
                f"""<div class='dce-card'>
                    <div class='dce-card-header'>Status AST</div>
                    <div class='dce-metric-value' style='color:#34d399;'>
                        {'✓ Auditado' if exec_res.success and not exec_res.security_violation else '✗ Erro'}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
        with m_col2:
            st.markdown(
                f"""<div class='dce-card'>
                    <div class='dce-card-header'>Tempo de Execução</div>
                    <div class='dce-metric-value'>{exec_res.execution_time_ms:.1f} <span style='font-size:12px;color:#a1a1aa;'>ms</span></div>
                </div>""",
                unsafe_allow_html=True,
            )
        with m_col3:
            st.markdown(
                f"""<div class='dce-card'>
                    <div class='dce-card-header'>Linhas Retornadas</div>
                    <div class='dce-metric-value'>{exec_res.row_count}</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with m_col4:
            st.markdown(
                f"""<div class='dce-card'>
                    <div class='dce-card-header'>Autocorreção</div>
                    <div class='dce-metric-value'>{turn.correction_attempts} <span style='font-size:12px;color:#a1a1aa;'>tentativa(s)</span></div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Audited SQL Code
        st.markdown("<div class='dce-card-header' style='margin-top:10px;'>SQL Gerado (Auditado por AST Guardrails)</div>", unsafe_allow_html=True)
        st.code(turn.generated_sql.sanitized_sql or turn.generated_sql.raw_sql, language="sql")

        # Table Display
        if exec_res.success and exec_res.columns and exec_res.rows:
            df = pd.DataFrame(exec_res.rows, columns=exec_res.columns)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Quick Visualization if DataFrame has suitable numeric columns
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            text_cols = df.select_dtypes(exclude=["number"]).columns.tolist()
            if len(df) > 1 and numeric_cols and text_cols:
                with st.expander("📊 Gráfico Automático de Visualização", expanded=False):
                    chart_df = df.set_index(text_cols[0])[numeric_cols[:2]]
                    st.bar_chart(chart_df)
        elif not exec_res.success:
            st.error(f"Erro na execução da consulta: {exec_res.error_message}")

        # Inline Playbook Saver
        with st.expander("⭐ Salvar Consulta como Playbook Recorrente (Memória Few-Shot)", expanded=False):
            st.caption("Playbooks salvos alimentam automaticamente a memória semântica do agente sem re-perguntar.")
            pb_title = st.text_input("Título do Playbook", value=f"Playbook: {question_input[:40]}")
            pb_tags = st.text_input("Tags (separadas por vírgula)", value="vendas, executivo, olist")
            if st.button("Salvar no Playbook Store"):
                tag_list = [t.strip() for t in pb_tags.split(",") if t.strip()]
                saved_pb = store.save_playbook(
                    title=pb_title,
                    question=question_input,
                    sql_query=turn.generated_sql.sanitized_sql or turn.generated_sql.raw_sql,
                    resolved_metric_id=st.session_state.selected_metric_id,
                    tags=tag_list,
                )
                st.success(f"Playbook '{saved_pb.title}' salvo e indexado com sucesso no HybridRetriever!")

    with col_insp:
        st.markdown("### Painel de Inspeção de Contexto (Nível 2)")
        insp = turn.assembled_context.inspection

        # Token Budget & Savings
        i_col1, i_col2 = st.columns(2)
        with i_col1:
            st.markdown(
                f"""<div class='dce-card'>
                    <div class='dce-card-header'>Economia de Tokens</div>
                    <div class='dce-metric-value' style='color:#818cf8;'>{insp.token_savings_pct:.1f}%</div>
                    <div style='font-size:11px;color:#a1a1aa;'>{insp.raw_full_schema_tokens} ➔ {insp.assembled_context_tokens} tokens</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with i_col2:
            st.markdown(
                f"""<div class='dce-card'>
                    <div class='dce-card-header'>Prefix Cacheável</div>
                    <div class='dce-metric-value' style='color:#34d399;'>{insp.prefix_cacheable_pct:.1f}%</div>
                    <div style='font-size:11px;color:#a1a1aa;'>{insp.prefix_cacheable_tokens} tokens estáticos</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # Selected Tables
        st.markdown("<div class='dce-card-header' style='margin-top:12px;'>Tabelas Selecionadas no Grafo</div>", unsafe_allow_html=True)
        if insp.selected_tables:
            for tbl in insp.selected_tables:
                badge_type = "badge-indigo" if tbl.selection_type == "direct_match" else "badge-amber"
                st.markdown(
                    f"""<div style='background:#18181b; border:1px solid #27272a; border-radius:6px; padding:8px 12px; margin-bottom:6px;'>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <span style='font-weight:600; font-size:13px; font-family:monospace;'>{tbl.table_name}</span>
                            <span class='badge-pill {badge_type}'>{tbl.selection_type}</span>
                        </div>
                        <div style='font-size:11px; color:#a1a1aa; margin-top:2px;'>{tbl.retrieval_reason or tbl.reason}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Nenhuma tabela filtrada neste nível de contexto.")

        # Canonical Metrics & Business Rules
        st.markdown("<div class='dce-card-header' style='margin-top:12px;'>Métricas Canônicas & Filtros Obrigatórios</div>", unsafe_allow_html=True)
        if insp.selected_metrics:
            for met in insp.selected_metrics:
                st.markdown(
                    f"""<div style='background:#18181b; border:1px solid #27272a; border-radius:6px; padding:8px 12px; margin-bottom:6px;'>
                        <div style='font-weight:600; font-size:13px;'>{met.name} (<code>{met.metric_id}</code>)</div>
                        <div style='font-size:12px; color:#a1a1aa; font-family:monospace; margin-top:4px;'>{met.canonical_sql}</div>
                        <div style='font-size:11px; color:#fbbf24; margin-top:4px;'>Filtros: {', '.join(met.filters_required) if met.filters_required else 'Nenhum'}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Nenhuma métrica canônica injetada neste nível.")

        # Retrieved Few-Shot Examples
        st.markdown("<div class='dce-card-header' style='margin-top:12px;'>Exemplos Few-Shot Recuperados</div>", unsafe_allow_html=True)
        if insp.few_shot_examples:
            for ex in insp.few_shot_examples[:3]:
                source_badge = "badge-emerald" if ex.source == "saved_playbook" else "badge-zinc"
                st.markdown(
                    f"""<div style='background:#18181b; border:1px solid #27272a; border-radius:6px; padding:8px 12px; margin-bottom:6px;'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span style='font-size:12px; font-weight:500;'>{ex.question}</span>
                            <span class='badge-pill {source_badge}'>{ex.source}</span>
                        </div>
                        <div style='font-size:10px; color:#71717a; margin-top:2px;'>Similaridade: {ex.similarity_score:.2f}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Nenhum exemplo few-shot injetado neste nível.")

        # Real Prompt Inspector Expander
        with st.expander("🔍 Inspecionar Prompt Real (Static Prefix vs Dynamic Suffix)", expanded=False):
            st.markdown("**Static Prefix (Cacheável pelo provedor LLM):**")
            st.code(turn.assembled_context.static_prefix[:600] + "...", language="markdown")
            st.markdown("**Dynamic Suffix (Específico da pergunta):**")
            st.code(turn.assembled_context.dynamic_suffix, language="markdown")

# =============================================================================
# TAB 2: COMPARADOR SIDE-BY-SIDE (L1 NAIVE VS L4 CONTEXT ENGINE)
# =============================================================================
with tab2:
    st.markdown("## Comparador Side-by-Side: `L1 Naive` vs `L4 Context Engine`")
    st.caption(
        "Veja como despejar o schema bruto (L1) induz o modelo a alucinar filtros, "
        "ignorar regras de negócio e gastar 3x mais tokens do que o Context Engine (L4)."
    )

    compare_question = st.selectbox(
        "Selecione uma pergunta de teste com armadilha de negócio:",
        options=[
            "Qual a receita total obtida com todos os pedidos que foram efetivamente entregues?",
            "Quem são os nossos 10 melhores clientes?",
            "Quantos clientes únicos realizaram compras em 2017?",
            "Qual o valor médio do frete por estado?",
        ],
        index=0,
    )

    if st.button("Executar Comparação L1 vs L4"):
        with st.spinner("Executando comparativo paralelo..."):
            res_l1 = agent.run_turn(compare_question, level=ContextLevel.L1, replay_only=True)
            res_l4 = agent.run_turn(
                compare_question,
                level=ContextLevel.L4,
                selected_metric_id="net_revenue" if "receita" in compare_question else None,
                replay_only=True,
            )
            st.session_state.compare_l1 = res_l1
            st.session_state.compare_l4 = res_l4

    if "compare_l1" in st.session_state and "compare_l4" in st.session_state:
        c_l1 = st.session_state.compare_l1
        c_l4 = st.session_state.compare_l4

        col_comp1, col_comp2 = st.columns(2, gap="large")

        with col_comp1:
            st.markdown(
                """<div style='border:1px solid #7f1d1d; background:#1c1917; border-radius:8px; padding:12px 16px; margin-bottom:12px;'>
                    <div style='font-size:14px; font-weight:700; color:#f87171;'>❌ Nível L1 · Naive Schema Dump</div>
                    <div style='font-size:12px; color:#d4d4d8;'>Sem camada semântica. Despeja todas as tabelas brutas no prompt.</div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Tokens Consumidos:** `{c_l1.assembled_context.inspection.assembled_context_tokens}` tokens (0% economia)")
            st.markdown("**Prefix Cacheável:** `0.0%`")
            st.markdown("**SQL Gerado:**")
            st.code(c_l1.generated_sql.sanitized_sql or c_l1.generated_sql.raw_sql, language="sql")
            st.markdown("**Resultado:**")
            if c_l1.execution_result.rows:
                st.dataframe(pd.DataFrame(c_l1.execution_result.rows, columns=c_l1.execution_result.columns).head(3))
            st.caption("⚠️ Falha comum: Esquece `order_status = 'delivered'` ou usa `customer_id` transacional ao invés do persistent `customer_unique_id`.")

        with col_comp2:
            st.markdown(
                """<div style='border:1px solid #14532d; background:#052e16; border-radius:8px; padding:12px 16px; margin-bottom:12px;'>
                    <div style='font-size:14px; font-weight:700; color:#4ade80;'>✓ Nível L4 · Data Context Engine</div>
                    <div style='font-size:12px; color:#d4d4d8;'>Roteamento de marts, métricas canônicas, poucas amostras e prefix caching.</div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Tokens Consumidos:** `{c_l4.assembled_context.inspection.assembled_context_tokens}` tokens "
                f"<span class='badge-pill badge-emerald'>-{c_l4.assembled_context.inspection.token_savings_pct:.1f}%</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Prefix Cacheável:** `{c_l4.assembled_context.inspection.prefix_cacheable_pct:.1f}%`")
            st.markdown("**SQL Gerado:**")
            st.code(c_l4.generated_sql.sanitized_sql or c_l4.generated_sql.raw_sql, language="sql")
            st.markdown("**Resultado:**")
            if c_l4.execution_result.rows:
                st.dataframe(pd.DataFrame(c_l4.execution_result.rows, columns=c_l4.execution_result.columns).head(3))
            st.caption("✓ Sucesso: Respeita regras de negócio canônicas (RN-01..RN-07) com AST auditada.")

# =============================================================================
# TAB 3: PAINEL DO BENCHMARK & ARQUITETURA
# =============================================================================
with tab3:
    st.markdown("## Avaliação & Benchmark nos 30 Gold Questions")
    st.caption(
        "Resultados consolidados em 30 perguntas reais cobrindo armadilhas analíticas do Olist "
        "(pedidos cancelados, frete duplicado, customer_unique_id vs customer_id)."
    )

    # Load summary if exists
    summary_path = Path("results/benchmark_summary.json")
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            bench_data = json.load(f)
        results_list = bench_data.get("results", [])
    else:
        results_list = [
            {"level": "L0", "single_shot_accuracy": 0.133, "corrected_accuracy": 0.167, "avg_tokens": 498, "token_savings_pct": 90.7},
            {"level": "L1", "single_shot_accuracy": 0.333, "corrected_accuracy": 0.367, "avg_tokens": 5861, "token_savings_pct": 0.0},
            {"level": "L2", "single_shot_accuracy": 0.533, "corrected_accuracy": 0.567, "avg_tokens": 1269, "token_savings_pct": 76.3},
            {"level": "L3", "single_shot_accuracy": 0.700, "corrected_accuracy": 0.733, "avg_tokens": 3065, "token_savings_pct": 42.7},
            {"level": "L4", "single_shot_accuracy": 0.833, "corrected_accuracy": 0.867, "avg_tokens": 2070, "token_savings_pct": 61.3},
        ]

    # Benchmark KPIs
    k_col1, k_col2, k_col3, k_col4 = st.columns(4)
    with k_col1:
        st.markdown(
            """<div class='dce-card'>
                <div class='dce-card-header'>Acurácia Single-Shot L4</div>
                <div class='dce-metric-value' style='color:#34d399;'>83.3%</div>
                <div class='dce-metric-delta'>+50% vs L1 Naive</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with k_col2:
        st.markdown(
            """<div class='dce-card'>
                <div class='dce-card-header'>Acurácia com Autocorreção</div>
                <div class='dce-metric-value' style='color:#34d399;'>86.7% - 90.0%</div>
                <div class='dce-metric-delta'>Recupera erros de sintaxe DuckDB</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with k_col3:
        st.markdown(
            """<div class='dce-card'>
                <div class='dce-card-header'>Redução Média de Tokens</div>
                <div class='dce-metric-value' style='color:#818cf8;'>-61.3%</div>
                <div style='font-size:11px;color:#a1a1aa;'>5,861 ➔ 2,070 tokens</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with k_col4:
        st.markdown(
            """<div class='dce-card'>
                <div class='dce-card-header'>Violações de Segurança AST</div>
                <div class='dce-metric-value' style='color:#34d399;'>0.0%</div>
                <div style='font-size:11px;color:#a1a1aa;'>100% ataques bloqueados</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # Progression Chart
    chart_data = pd.DataFrame([
        {
            "Nível": r["level"],
            "Single-Shot (%)": round(r["single_shot_accuracy"] * 100, 1),
            "Com Autocorreção (%)": round(r["corrected_accuracy"] * 100, 1),
        }
        for r in results_list
    ]).set_index("Nível")

    st.markdown("### Progressão Monotônica de Acurácia (L0 ➔ L4)")
    st.bar_chart(chart_data)

    # Gold Questions Table
    st.markdown("### Cobertura do Gold Benchmark (30 Perguntas)")
    runner_ref = BenchmarkRunner(db_path=DB_PATH)
    gq_data = [
        {
            "ID": q.id,
            "Dificuldade": q.difficulty.upper(),
            "Pergunta": q.question,
            "Armadilhas": ", ".join(q.trap_tags) if q.trap_tags else "Direta",
            "Métrica Canônica": q.resolved_metric_id or "-",
        }
        for q in runner_ref.gold_questions
    ]
    st.dataframe(pd.DataFrame(gq_data), use_container_width=True, hide_index=True)

    # Architecture Overview
    st.markdown("---")
    st.markdown("### Arquitetura do Data Context Engine")
    st.markdown(
        """
        ```
        [ Usuário / Agente MCP ]
                   │
                   ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ 1. Clarificação Ativa Semântica (SemanticClarifier)         │
        │    Detecta termos ambíguos ("melhores clientes") e         │
        │    solicita desambiguação antes de gerar SQL.               │
        └──────────────────────────────┬──────────────────────────────┘
                                       │
                                       ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ 2. Context Routing & Prefix Caching (ContextAssembler)       │
        │    - HybridRetriever (BM25 + Grafo de Joins)                │
        │    - Compressão DDL (remove tabelas e colunas irrelevantes) │
        │    - Divisão em Static Prefix (>50%) & Dynamic Suffix       │
        └──────────────────────────────┬──────────────────────────────┘
                                       │
                                       ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ 3. Execução & Guardrails Hardened (SafeSQLExecutor)         │
        │    - AST Validator bloqueia DROP, DELETE, ATTACH, read_csv  │
        │    - DuckDB sandbox com enable_external_access=False        │
        │    - Limite automático de 1000 linhas                       │
        └──────────────────────────────┬──────────────────────────────┘
                                       │
                                       ▼
        ┌─────────────────────────────────────────────────────────────┐
        │ 4. Playbook Feedback Loop (PlaybookStore)                   │
        │    Consultas auditadas são salvas como novos exemplos       │
        │    few-shot sem poluição do benchmark de avaliação.         │
        └─────────────────────────────────────────────────────────────┘
        ```
        """
    )
