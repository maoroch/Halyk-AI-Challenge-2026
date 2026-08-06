import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Standard offline fallback exchange rates to USD
DEFAULT_FX_RATES: Dict[str, float] = {
    "USD": 1.0,
    "KZT": 0.002083,  # ~480 KZT per USD
    "EUR": 1.08,      # 1 EUR = 1.08 USD
    "GBP": 1.27,      # 1 GBP = 1.27 USD
    "RUB": 0.011,     # ~90 RUB per USD
}


class CurrencyService:
    def __init__(self, fx_rates: Dict[str, float] = None):
        self.fx_rates = dict(fx_rates or DEFAULT_FX_RATES)

    def extract_fx_rates_from_text(self, text: str) -> None:
        """
        Parses document text for explicit exchange rates (e.g. 1 USD = 485 KZT)
        and updates local exchange rates without any external network dependency.
        """
        if not text:
            return

        # Search for pattern e.g. 1 USD = 485.5 KZT or 1 EUR = 1.09 USD
        matches = re.findall(r"1\s*([A-Z]{3})\s*=\s*(\d+(?:\.\d+)?)\s*([A-Z]{3})", text)
        for base_curr, rate_str, target_curr in matches:
            try:
                rate = float(rate_str)
                if base_curr == "USD" and rate > 0:
                    self.fx_rates[target_curr] = 1.0 / rate
                elif target_curr == "USD" and rate > 0:
                    self.fx_rates[base_curr] = rate
            except ValueError:
                pass

    def convert_to_usd(self, amount: float, currency: str) -> float:
        curr = (currency or "USD").upper().strip()
        rate = self.fx_rates.get(curr, 1.0)
        usd_amount = amount * rate
        return usd_amount
