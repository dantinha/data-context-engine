"""End-to-end usability and contract audit tests for app/streamlit_app.py using Streamlit AppTest."""

from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def test_scroll_mode_initial_render_all_sections_no_exceptions() -> None:
    """Verifies that Continuous Scroll mode renders all 5 sections cleanly without any exception."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception, f"Unexpected exception on initial load: {at.exception}"
    assert at.session_state["nav_view_mode"].startswith("📱")
    # Check that dataframes from Duel, Workbench, and Catalog/Benchmark rendered
    assert len(at.dataframe) >= 4
    # Check that SQL code blocks rendered
    assert len(at.code) >= 3


def test_cta_button_switches_to_duel_step_in_stepper_mode() -> None:
    """Verifies clicking the Hero CTA button switches to Step 2 (O Duelo) in Stepper mode."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    cta_btn = at.button(key="scroll_s1_btn_goto_duel")
    cta_btn.click().run()

    assert not at.exception, f"Exception after clicking CTA button: {at.exception}"
    assert at.session_state["active_step_index"] == 1
    assert at.session_state["sidebar_step_radio"] == "02 · O Duelo (L1 vs L4)"
    assert at.session_state["nav_view_mode"].startswith("💻")


def test_desktop_stepper_forward_and_backward_navigation() -> None:
    """Verifies step-by-step navigation forward (0 -> 4) and backward (4 -> 0) works seamlessly."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Switch to Desktop Stepper mode via sidebar radio
    view_radio = at.sidebar.radio(key="nav_view_mode")
    view_radio.set_value("💻 Passo a Passo Lateral (Desktop)").run()
    assert not at.exception
    assert at.session_state["active_step_index"] == 0

    # Advance through all 5 steps (0 -> 1 -> 2 -> 3 -> 4) using "Próximo Passo" button
    for expected_next_idx in range(1, 5):
        next_btn = at.button(key="btn_next_step")
        next_btn.click().run()
        assert not at.exception, f"Exception advancing to step {expected_next_idx}: {at.exception}"
        assert at.session_state["active_step_index"] == expected_next_idx

    # Navigate backward (4 -> 3 -> 2) using "Passo Anterior" button
    for expected_prev_idx in (3, 2):
        prev_btn = at.button(key="btn_prev_step")
        prev_btn.click().run()
        assert not at.exception, f"Exception going back to step {expected_prev_idx}: {at.exception}"
        assert at.session_state["active_step_index"] == expected_prev_idx

    # Jump directly to Step 4 (Guardrails, index 3) via top stepper bar button
    at.button(key="top_step_btn_3").click().run()
    assert not at.exception
    assert at.session_state["active_step_index"] == 3
    assert at.session_state["sidebar_step_radio"] == "04 · Defesa & Guardrails"


def test_duel_all_four_analytical_trap_scenarios() -> None:
    """Verifies all 4 Duel scenarios execute in L1 and L4 and produce valid results."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Navigate to Step 1 (O Duelo) in Stepper mode
    at.button(key="scroll_s1_btn_goto_duel").click().run()
    assert not at.exception

    duel_select = at.selectbox(key="step_s2_duel_question_selector")
    scenarios = [
        "Qual o faturamento total da empresa?",
        "Quem são os nossos 10 melhores clientes?",
        "Quantos clientes únicos realizaram compras em 2017?",
        "Qual o valor médio do frete por estado?",
    ]
    for scenario in scenarios:
        duel_select.set_value(scenario).run()
        assert not at.exception, f"Exception on Duel scenario '{scenario}': {at.exception}"
        c_l1 = at.session_state["compare_l1"]
        c_l4 = at.session_state["compare_l4"]
        assert c_l1.execution_result.success
        assert c_l4.execution_result.success
        assert c_l4.assembled_context.inspection.assembled_context_tokens < c_l1.assembled_context.inspection.assembled_context_tokens


def test_workbench_quick_pills_clarifier_and_execution() -> None:
    """Verifies Workbench quick suggestion pills update input, trigger Clarifier, and run SQL."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Switch to Stepper Step 2 (Workbench)
    at.sidebar.radio(key="nav_view_mode").set_value("💻 Passo a Passo Lateral (Desktop)").run()
    at.button(key="top_step_btn_2").click().run()
    assert not at.exception

    # Click each of the 4 quick pills and verify input synchronization + execution
    pills = [
        ("step_s3_pill_rev", "Qual o faturamento total da empresa?", "net_revenue"),
        ("step_s3_pill_sla", "Qual o tempo médio de entrega dos pedidos em São Paulo?", "delivery_delay_rate"),
        ("step_s3_pill_sellers", "Quem são os nossos melhores vendedores?", "seller_revenue"),
        ("step_s3_pill_clients", "Quem são os nossos 10 melhores clientes?", "customer_ltv"),
    ]
    for btn_key, expected_q, expected_metric in pills:
        at.button(key=btn_key).click().run()
        assert not at.exception, f"Exception clicking workbench pill {btn_key}: {at.exception}"
        assert at.session_state["input_user_question"] == expected_q
        assert at.session_state["selected_metric_id"] == expected_metric
        res = at.session_state["last_executed_result"]
        assert res is not None
        assert res.execution_result.success
        assert res.execution_result.row_count >= 1

    # Switch metric option in Semantic Clarifier radio (e.g. customer_avg_ticket)
    metric_radio = at.radio(key="step_s3_radio_metric_choice")
    metric_radio.set_value("customer_avg_ticket").run()
    assert not at.exception
    assert at.session_state["selected_metric_id"] == "customer_avg_ticket"
    assert "avg_ticket" in at.session_state["last_executed_result"].generated_sql.sanitized_sql


def test_guardrails_all_six_attack_and_safe_presets() -> None:
    """Verifies all 6 Guardrail AST preset buttons update the SQL box and render AST verdicts."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    # Switch to Stepper Step 3 (Defesa & Guardrails)
    at.sidebar.radio(key="nav_view_mode").set_value("💻 Passo a Passo Lateral (Desktop)").run()
    at.button(key="top_step_btn_3").click().run()
    assert not at.exception

    # Click all 6 presets (0..3 are blocked attacks, 4 is raw schema warning + limit clamp, 5 is clean mart query)
    for idx in range(6):
        at.button(key=f"step_s4_btn_atk_{idx}").click().run()
        assert not at.exception, f"Exception on guardrail preset {idx}: {at.exception}"

    # Preset 5 (last clicked) is a valid query on marts.fct_orders; verify code block rendered
    assert len(at.code) >= 1
    assert "LIMIT 10" in at.code[0].value

    # Click Preset 4 (Raw schema with LIMIT 9999999) and verify governance warning + LIMIT 1000 clamping
    at.button(key="step_s4_btn_atk_4").click().run()
    assert not at.exception
    assert len(at.warning) >= 1
    assert "LIMIT 1000" in at.code[0].value
