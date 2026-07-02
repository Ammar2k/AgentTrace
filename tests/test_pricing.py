import pytest

from agenttrace.server.pricing import MODEL_PRICES, TokenPrice, cost_of


def test_cost_of_known_model_uses_input_and_output_prices():
    assert cost_of("demo-model", tokens_in=100, tokens_out=50) == pytest.approx(0.0002)


def test_token_price_values_are_per_million_tokens(monkeypatch):
    monkeypatch.setitem(
        MODEL_PRICES,
        "cheap-model",
        TokenPrice(input_usd_per_million=0.2, output_usd_per_million=0.8),
    )

    assert cost_of("cheap-model", tokens_in=1_000_000, tokens_out=1_000_000) == pytest.approx(1.0)


def test_cost_of_unknown_model_returns_zero():
    assert cost_of("unknown-model", tokens_in=100, tokens_out=50) == 0.0


def test_cost_of_missing_model_returns_zero():
    assert cost_of(None, tokens_in=100, tokens_out=50) == 0.0
