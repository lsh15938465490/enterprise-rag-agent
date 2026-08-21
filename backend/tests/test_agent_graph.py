"""Agent 计划 JSON 解析：模型胡写时要能落到安全的 retrieve。"""

from app.services.agent_graph import _parse_plan, route_supervisor


def test_parse_plan_json():
    plan = _parse_plan('{"thought":"查库","action":"retrieve","action_input":{"query":"年假"}}')
    assert plan["action"] == "retrieve"
    assert plan["action_input"]["query"] == "年假"


def test_parse_plan_invalid_falls_back_to_retrieve():
    plan = _parse_plan("not-json")
    assert plan["action"] == "retrieve"


def test_route_finish():
    assert route_supervisor({"action": "finish"}) == "finish"
    assert route_supervisor({"action": "execute"}) == "execute"
