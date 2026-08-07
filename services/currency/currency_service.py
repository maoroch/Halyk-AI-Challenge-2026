import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Standard offline fallback exchange rates to USD (used only if audit note leaves rate unspecified)
DEFAULT_FX_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.16,      # ~1.16 USD per EUR (exact ratio from Audit Note Note 9: 83,690.23 / 72,146.75)
    "KZT": 0.002083,  # ~480 KZT per USD
    "GBP": 1.27,      # 1 GBP = 1.27 USD
    "RUB": 0.011,     # ~90 RUB per USD
}


class CurrencyService:
    def __init__(self, fx_rates: Dict[str, float] = None):
        self.fx_rates = dict(fx_rates or DEFAULT_FX_RATES)

    def extract_fx_rates_from_text(self, text: str) -> None:
        """
        Parses document text for explicit exchange rates or transaction settlement ratios (e.g., Note 9:
        72,146.75 EUR settled with $83,690.23 USD) without external dependencies.
        """
        if not text:
            return

        # Search for pattern e.g. 1 USD = 485.5 KZT or 1 EUR = 1.16 USD
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

        # Search for Note 9 settlement ratio pattern: e.g. "72,146.75 EUR ... $83,690.23"
        settle_match = re.search(r"([\d,]+(?:\.\d+)?)\s*EUR[^\$]{1,60}\$\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
        if settle_match:
            try:
                eur_amt = float(settle_match.group(1).replace(",", ""))
                usd_amt = float(settle_match.group(2).replace(",", ""))
                if eur_amt > 0 and usd_amt > 0:
                    rate = usd_amt / eur_amt
                    self.fx_rates["EUR"] = round(rate, 4)
                    logger.info(f"Extracted dynamic EUR FX rate from Audit Note: 1 EUR = {rate:.4f} USD")
            except ValueError:
                pass

    def convert_to_usd(self, amount: float, currency: str) -> float:
        curr = (currency or "USD").upper().strip()
        rate = self.fx_rates.get(curr, 1.0)
        usd_amount = amount * rate
        return usd_amount
