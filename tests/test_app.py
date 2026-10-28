from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.state import initialize_scenario


ROOT = Path(__file__).resolve().parents[1]


def test_switching_manager_version_resets_state_and_reset_keeps_version():
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception
    assert app.session_state["manager_version"] == "V0"

    journey = initialize_scenario("Fresh application")
    journey["accepted_values"] = {"consent": True}
    journey["pending_values"] = {"tenure_months": 12}
    journey["messages"] = [{"role": "user", "content": "synthetic old message"}]
    journey["tool_events"] = [{
        "tool": "submit_information", "fields": ["consent"], "outcomes": [],
        "success": True, "active_rule": "BR-02",
    }]
    app.session_state["journey"] = journey
    app.session_state["turn_error"] = "synthetic error"
    app.run()

    app.selectbox(key="manager_version_selector").set_value("V1").run()
    reset = app.session_state["journey"]
    assert app.session_state["manager_version"] == "V1"
    assert app.selectbox(key="manager_version_selector").value == "V1"
    assert reset["scenario"] == "Fresh application"
    assert reset["accepted_values"] == {}
    assert reset["pending_values"] == {}
    assert reset["messages"] == []
    assert reset["tool_events"] == []
    assert "turn_error" not in app.session_state
    assert any("Manager Version: **V1**" in item.value for item in app.caption)

    dirty = initialize_scenario("Fresh application")
    dirty["accepted_values"] = {"consent": True}
    dirty["messages"] = [{"role": "user", "content": "synthetic V1 message"}]
    app.session_state["journey"] = dirty
    app.run()
    app.button[0].click().run()
    assert app.session_state["manager_version"] == "V1"
    assert app.session_state["journey"]["accepted_values"] == {}
    assert app.session_state["journey"]["messages"] == []
