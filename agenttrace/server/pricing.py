from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPrice:
    """USD price per 1 million input tokens and output tokens."""

    input_usd_per_million: float
    output_usd_per_million: float


# Prices are deliberately centralized here because model pricing changes over time.
# Unknown models cost 0.0 so tracing keeps working even when pricing is incomplete.
MODEL_PRICES: dict[str, TokenPrice] = {
    "demo-model": TokenPrice(input_usd_per_million=1.0, output_usd_per_million=2.0),
}


def cost_of(model: str | None, tokens_in: int = 0, tokens_out: int = 0) -> float:
    if model is None:
        return 0.0

    price = MODEL_PRICES.get(model)
    if price is None:
        return 0.0

    return (
        (tokens_in / 1_000_000) * price.input_usd_per_million
        + (tokens_out / 1_000_000) * price.output_usd_per_million
    )
