from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agents.debater import DebaterAgent
from main import app

FAKE_AGENT_RESPONSE = {
    "message": (
        "As the representative for this country, we acknowledge the previous statement "
        "and affirm our commitment to the agreed international framework on climate action. "
        "Our policy positions are grounded in both our domestic targets and our obligations "
        "under existing multilateral agreements."
    ),
    "stance": "supportive",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_returns_200(self, client):
        res = client.get("/health")
        assert res.status_code == 200

    def test_response_body(self, client):
        res = client.get("/health")
        assert res.json() == {"status": "ok"}


class TestPolicyEndpoints:
    def test_get_usa_policy(self, client):
        res = client.get("/policies/usa")
        assert res.status_code == 200
        data = res.json()
        assert data["country"] == "USA"
        assert "key_positions" in data
        assert "red_lines" in data
        assert len(data["key_positions"]) > 0

    def test_get_eu_policy(self, client):
        res = client.get("/policies/eu")
        assert res.status_code == 200
        data = res.json()
        assert data["country"] == "EU"
        assert "key_positions" in data
        assert "red_lines" in data

    def test_get_china_policy(self, client):
        res = client.get("/policies/china")
        assert res.status_code == 200
        data = res.json()
        assert data["country"] == "China"
        assert "key_positions" in data
        assert "red_lines" in data

    def test_invalid_country_returns_404(self, client):
        res = client.get("/policies/australia")
        assert res.status_code == 404

    def test_case_insensitive_lookup(self, client):
        res = client.get("/policies/USA")
        assert res.status_code == 200
        assert res.json()["country"] == "USA"


class TestFrontendEndpoint:
    def test_root_returns_200(self, client):
        res = client.get("/")
        assert res.status_code == 200

    def test_root_content_type_is_html(self, client):
        res = client.get("/")
        assert "text/html" in res.headers["content-type"]


class TestDebateEndpoint:
    def test_two_rounds_produces_six_messages(self, client):
        with patch.object(
            DebaterAgent, "generate", new_callable=AsyncMock, return_value=FAKE_AGENT_RESPONSE
        ):
            res = client.post("/debate/start", json={"topic": "Carbon taxes", "rounds": 2})
        assert res.status_code == 200
        assert len(res.json()["messages"]) == 6

    def test_three_rounds_produces_nine_messages(self, client):
        with patch.object(
            DebaterAgent, "generate", new_callable=AsyncMock, return_value=FAKE_AGENT_RESPONSE
        ):
            res = client.post("/debate/start", json={"topic": "Renewable energy", "rounds": 3})
        assert res.status_code == 200
        assert len(res.json()["messages"]) == 9

    def test_one_round_produces_three_messages(self, client):
        with patch.object(
            DebaterAgent, "generate", new_callable=AsyncMock, return_value=FAKE_AGENT_RESPONSE
        ):
            res = client.post("/debate/start", json={"topic": "Net zero targets", "rounds": 1})
        assert res.status_code == 200
        assert len(res.json()["messages"]) == 3

    def test_agent_turn_order_is_usa_eu_china(self, client):
        with patch.object(
            DebaterAgent, "generate", new_callable=AsyncMock, return_value=FAKE_AGENT_RESPONSE
        ):
            res = client.post("/debate/start", json={"topic": "Climate finance", "rounds": 3})
        expected = ["USA", "EU", "China"] * 3
        actual = [m["agent"] for m in res.json()["messages"]]
        assert actual == expected

    def test_message_schema_is_complete(self, client):
        with patch.object(
            DebaterAgent, "generate", new_callable=AsyncMock, return_value=FAKE_AGENT_RESPONSE
        ):
            res = client.post("/debate/start", json={"topic": "Emissions trading", "rounds": 1})
        messages = res.json()["messages"]
        for msg in messages:
            assert "round" in msg
            assert "agent" in msg
            assert "message" in msg
            assert "stance" in msg
            assert "timestamp" in msg
            assert isinstance(msg["round"], int)
            assert isinstance(msg["agent"], str)
            assert isinstance(msg["message"], str)
            assert isinstance(msg["timestamp"], str)
            assert msg["stance"] in {"supportive", "opposed", "neutral"}

    def test_round_numbers_are_correct(self, client):
        with patch.object(
            DebaterAgent, "generate", new_callable=AsyncMock, return_value=FAKE_AGENT_RESPONSE
        ):
            res = client.post("/debate/start", json={"topic": "Test", "rounds": 2})
        messages = res.json()["messages"]
        assert messages[0]["round"] == 1
        assert messages[1]["round"] == 1
        assert messages[2]["round"] == 1
        assert messages[3]["round"] == 2
        assert messages[4]["round"] == 2
        assert messages[5]["round"] == 2

    def test_rounds_zero_is_rejected(self, client):
        res = client.post("/debate/start", json={"topic": "Test", "rounds": 0})
        assert res.status_code == 422

    def test_rounds_above_five_is_rejected(self, client):
        res = client.post("/debate/start", json={"topic": "Test", "rounds": 6})
        assert res.status_code == 422

    def test_empty_topic_is_rejected(self, client):
        res = client.post("/debate/start", json={"topic": "", "rounds": 1})
        assert res.status_code == 422
