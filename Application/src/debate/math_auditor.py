from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Numerical word mapping
NUMBER_WORDS: Dict[str, float] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1_000, "grand": 1_000, "k": 1_000,
    "million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "b": 1_000_000_000,
}


@dataclass
class NumericClaim:
    category: str  # "revenue", "customers", "acv", "cash", "burn", "runway", "headcount"
    raw_snippet: str
    value: float
    unit: str
    round_number: int
    transcript: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MathDiscrepancyItem:
    rule_type: str  # "revenue_volume_price", "runway_cash_burn", "historical_drift", "percentage_overflow", "headcount_overflow"
    description: str
    claimed_values: Dict[str, Any]
    expected_value: float
    stated_value: float
    discrepancy_gap: float
    lethal_salvo: str
    round_number: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MathAuditResult:
    has_contradiction: bool
    discrepancy: Optional[MathDiscrepancyItem] = None
    immediate_rectification_salvo: Optional[str] = None
    tracked_claims_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_contradiction": self.has_contradiction,
            "discrepancy": self.discrepancy.to_dict() if self.discrepancy else None,
            "immediate_rectification_salvo": self.immediate_rectification_salvo,
            "tracked_claims_count": self.tracked_claims_count,
        }


def _parse_currency_or_number(text: str) -> Optional[float]:
    """Parse a number string like '$1M', '1.5 million', '500k', '10 grand', '50' into a float."""
    lowered = text.lower().strip().replace("$", "").replace(",", "")

    # Multiplier heuristics
    multiplier = 1.0
    if "billion" in lowered or lowered.endswith("b"):
        multiplier = 1_000_000_000.0
        lowered = re.sub(r"[bB]|billion", "", lowered).strip()
    elif "million" in lowered or lowered.endswith("m"):
        multiplier = 1_000_000.0
        lowered = re.sub(r"[mM]|million", "", lowered).strip()
    elif "thousand" in lowered or "grand" in lowered or lowered.endswith("k"):
        multiplier = 1_000.0
        lowered = re.sub(r"[kK]|thousand|grand", "", lowered).strip()

    digits = re.findall(r"[0-9]+(?:\.[0-9]+)?", lowered)
    if digits:
        try:
            return float(digits[0]) * multiplier
        except ValueError:
            pass

    # Spoken number words
    words = lowered.split()
    if words and words[0] in NUMBER_WORDS:
        base = NUMBER_WORDS[words[0]]
        mul = 1.0
        if len(words) > 1 and words[1] in NUMBER_WORDS:
            mul = NUMBER_WORDS[words[1]]
        return base * mul * multiplier

    return None


class MathAuditor:
    """Async background validator tracking quantitative claims across all debate rounds.
    
    Detects impossible arithmetic, false unit economics, and shifting factual claims.
    """

    def __init__(self):
        self.claims_history: List[NumericClaim] = []
        self.discrepancy_history: List[MathDiscrepancyItem] = []
        # Current state ledger of latest user metrics
        self.ledger: Dict[str, NumericClaim] = {}

    def extract_claims_from_turn(self, transcript: str, round_number: int) -> List[NumericClaim]:
        """Extract explicit numerical claims from user speech."""
        claims: List[NumericClaim] = []
        lowered = transcript.lower()

        # 1. Revenue / ARR / Sales (e.g., "$1M in revenue", "revenue is 1.5 million", "doing 500k ARR")
        rev_patterns = [
            r"(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:million|thousand|grand|m|k))\s+(?:in\s+)?(?:revenue|arr|mrr|sales|annual\s+revenue)",
            r"(?:revenue|arr|mrr|annual\s+sales|annual\s+revenue)\s+(?:is|at|of|reached|around)?\s*(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:million|thousand|grand|m|k))",
            r"(?:did|made|hit)\s+(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:million|thousand|grand|m|k))\s+(?:in\s+)?(?:revenue|arr|sales)?",
        ]
        for pat in rev_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and val > 1000:
                    # If MRR, annualize to ARR
                    if "mrr" in m.group(0):
                        val *= 12
                    c = NumericClaim("revenue", raw, val, "USD", round_number, transcript)
                    claims.append(c)
                    break

        # 2. Customers / Clients / Accounts (e.g., "50 customers", "have 100 clients", "20 enterprise logos")
        cust_patterns = [
            r"(\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|[0-9]+))\s+(?:active\s+)?(?:paying\s+)?(?:customers|clients|accounts|logos|users|subscribers)",
            r"(?:have|signed|servicing)\s+(\d+)\s+(?:customers|clients|accounts)",
        ]
        for pat in cust_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and 0 < val <= 500_000:
                    c = NumericClaim("customers", raw, val, "count", round_number, transcript)
                    claims.append(c)
                    break

        # 3. ACV / Contract Value / Pricing (e.g., "paying $10k a year", "10k per customer", "average ACV is $25,000")
        acv_patterns = [
            r"(?:paying|pay\s+us|charged|average\s+deal|acv\s+is|price\s+is)\s*(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:thousand|grand|k|dollars))(?:\s*(?:a\s+year|per\s+year|annually|per\s+customer|contract))?",
            r"(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:thousand|grand|k|dollars))\s+(?:a\s+year|per\s+year|annually|acv|per\s+customer)",
        ]
        for pat in acv_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and val >= 100:
                    c = NumericClaim("acv", raw, val, "USD", round_number, transcript)
                    claims.append(c)
                    break

        # 4. Cash on Hand (e.g., "$2M in the bank", "raised $3M", "$1.5M in cash")
        cash_patterns = [
            r"(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:million|thousand|grand|m|k))\s+(?:in\s+(?:the\s+)?bank|in\s+cash|remaining|cash\s+on\s+hand)",
            r"(?:have|got|hold)\s+(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:million|thousand|grand|m|k))\s+(?:in\s+cash|in\s+the\s+bank)?",
        ]
        for pat in cash_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and val >= 10_000:
                    c = NumericClaim("cash", raw, val, "USD", round_number, transcript)
                    claims.append(c)
                    break

        # 5. Burn Rate (e.g., "burning $200k a month", "monthly burn of $50k")
        burn_patterns = [
            r"(?:burning|burn\s+is|burn\s+rate\s+is|spending)\s*(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:thousand|grand|k|m|million))(?:\s*(?:a\s+month|per\s+month|monthly))?",
            r"(\$[\s0-9\.]+[kKmMbB]?|\d+(?:\.\d+)?\s*(?:thousand|grand|k|m|million))\s+(?:a\s+month|per\s+month|monthly)\s+burn",
        ]
        for pat in burn_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and val >= 1_000:
                    c = NumericClaim("burn", raw, val, "USD/month", round_number, transcript)
                    claims.append(c)
                    break

        # 6. Runway (e.g., "18 months of runway", "runway is 12 months")
        runway_patterns = [
            r"(\d+)\s+months\s+(?:of\s+)?runway",
            r"runway\s+(?:is|at|of)\s+(\d+)\s+months",
        ]
        for pat in runway_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and 0 < val <= 60:
                    c = NumericClaim("runway", raw, val, "months", round_number, transcript)
                    claims.append(c)
                    break

        # 7. Headcount / Team Size (e.g., "team of 12", "15 employees", "have 8 people")
        headcount_patterns = [
            r"(?:team\s+of|headcount\s+of|we\s+are)\s+(\d+)(?:\s+(?:people|employees|engineers))?",
            r"(\d+)\s+(?:full-time\s+)?(?:employees|people|engineers|team\s+members)",
        ]
        for pat in headcount_patterns:
            for m in re.finditer(pat, lowered):
                raw = m.group(1)
                val = _parse_currency_or_number(raw)
                if val and 0 < val <= 50_000:
                    c = NumericClaim("headcount", raw, val, "people", round_number, transcript)
                    claims.append(c)
                    break

        return claims

    def audit_user_turn(self, transcript: str, round_number: int) -> MathAuditResult:
        """Process user utterance, update chronological ledger, and evaluate mathematical consistency."""
        new_claims = self.extract_claims_from_turn(transcript, round_number)
        for claim in new_claims:
            self.claims_history.append(claim)

        # 1. Check for Rule 1: Revenue vs Volume * Price (Customers * ACV)
        cust_claim = next((c for c in reversed(new_claims) if c.category == "customers"), self.ledger.get("customers"))
        acv_claim = next((c for c in reversed(new_claims) if c.category == "acv"), self.ledger.get("acv"))
        rev_claim = next((c for c in reversed(new_claims) if c.category == "revenue"), self.ledger.get("revenue"))

        # Trigger if either a new customer, acv, or revenue was stated this turn
        has_new_pricing = any(c.category in ("customers", "acv", "revenue") for c in new_claims)
        if has_new_pricing and cust_claim and acv_claim and rev_claim:
            calculated_rev = cust_claim.value * acv_claim.value
            stated_rev = rev_claim.value
            diff_ratio = abs(calculated_rev - stated_rev) / max(stated_rev, calculated_rev)

            # If discrepancy is > 20%
            if diff_ratio > 0.20:
                cust_int = int(cust_claim.value)
                acv_str = f"${int(acv_claim.value):,}" if acv_claim.value >= 1000 else f"${acv_claim.value}"
                calc_str = f"${int(calculated_rev):,}" if calculated_rev >= 1000 else f"${calculated_rev}"
                stated_str = f"${int(stated_rev):,}" if stated_rev >= 1000 else f"${stated_rev}"

                salvo = (
                    f"Wait. Stop right there. {cust_int} customers at {acv_str} is {calc_str}, not {stated_str}. "
                    f"Where did the other difference come from?"
                )

                item = MathDiscrepancyItem(
                    rule_type="revenue_volume_price",
                    description=f"Math Contradiction: {cust_int} customers @ {acv_str} = {calc_str}, but user claimed {stated_str} revenue.",
                    claimed_values={
                        "customers": cust_claim.raw_snippet,
                        "acv": acv_claim.raw_snippet,
                        "stated_revenue": rev_claim.raw_snippet,
                    },
                    expected_value=calculated_rev,
                    stated_value=stated_rev,
                    discrepancy_gap=abs(stated_rev - calculated_rev),
                    lethal_salvo=salvo,
                    round_number=round_number,
                )
                self.discrepancy_history.append(item)
                self._update_ledger(new_claims)
                return MathAuditResult(
                    has_contradiction=True,
                    discrepancy=item,
                    immediate_rectification_salvo=salvo,
                    tracked_claims_count=len(self.claims_history),
                )

        # 2. Check for Rule 2: Runway vs Cash / Monthly Burn
        cash_claim = next((c for c in reversed(new_claims) if c.category == "cash"), self.ledger.get("cash"))
        burn_claim = next((c for c in reversed(new_claims) if c.category == "burn"), self.ledger.get("burn"))
        runway_claim = next((c for c in reversed(new_claims) if c.category == "runway"), self.ledger.get("runway"))

        has_new_capital = any(c.category in ("cash", "burn", "runway") for c in new_claims)
        if has_new_capital and cash_claim and burn_claim and runway_claim and burn_claim.value > 0:
            calc_runway = cash_claim.value / burn_claim.value
            stated_runway = runway_claim.value
            diff_months = abs(calc_runway - stated_runway)

            # If discrepancy > 3 months
            if diff_months >= 3.0:
                cash_str = f"${int(cash_claim.value / 1000)}k" if cash_claim.value < 1_000_000 else f"${cash_claim.value / 1_000_000:.1f}M"
                burn_str = f"${int(burn_claim.value / 1000)}k/mo"
                calc_runway_int = round(calc_runway, 1)

                salvo = (
                    f"Hold on. {cash_str} in cash with {burn_str} burn is {calc_runway_int} months of runway, "
                    f"not {int(stated_runway)}. You run out of money months earlier than you claim!"
                )

                item = MathDiscrepancyItem(
                    rule_type="runway_cash_burn",
                    description=f"Runway Math Contradiction: {cash_str} cash / {burn_str} burn = {calc_runway_int} mos, but user claimed {int(stated_runway)} mos.",
                    claimed_values={
                        "cash": cash_claim.raw_snippet,
                        "burn": burn_claim.raw_snippet,
                        "stated_runway": runway_claim.raw_snippet,
                    },
                    expected_value=calc_runway,
                    stated_value=stated_runway,
                    discrepancy_gap=diff_months,
                    lethal_salvo=salvo,
                    round_number=round_number,
                )
                self.discrepancy_history.append(item)
                self._update_ledger(new_claims)
                return MathAuditResult(
                    has_contradiction=True,
                    discrepancy=item,
                    immediate_rectification_salvo=salvo,
                    tracked_claims_count=len(self.claims_history),
                )

        # 3. Check for Rule 3: Historical Intra-Session Number Drift (shifting numbers between rounds)
        for claim in new_claims:
            prev_claim = self.ledger.get(claim.category)
            if prev_claim and prev_claim.round_number != round_number:
                # If metric changed by > 40% without explanation
                drift = abs(claim.value - prev_claim.value) / max(claim.value, prev_claim.value)
                if drift > 0.40 and claim.category in ("revenue", "customers", "cash"):
                    salvo = (
                        f"Wait a second. In round {prev_claim.round_number} you claimed {prev_claim.raw_snippet} for {claim.category}, "
                        f"now you claim {claim.raw_snippet}. Why are your numbers changing?"
                    )
                    item = MathDiscrepancyItem(
                        rule_type="historical_drift",
                        description=f"Intra-Session Drift: {claim.category.capitalize()} changed from {prev_claim.raw_snippet} (Rd {prev_claim.round_number}) to {claim.raw_snippet} (Rd {round_number}).",
                        claimed_values={
                            "previous": prev_claim.raw_snippet,
                            "current": claim.raw_snippet,
                        },
                        expected_value=prev_claim.value,
                        stated_value=claim.value,
                        discrepancy_gap=abs(claim.value - prev_claim.value),
                        lethal_salvo=salvo,
                        round_number=round_number,
                    )
                    self.discrepancy_history.append(item)
                    self._update_ledger(new_claims)
                    return MathAuditResult(
                        has_contradiction=True,
                        discrepancy=item,
                        immediate_rectification_salvo=salvo,
                        tracked_claims_count=len(self.claims_history),
                    )

        self._update_ledger(new_claims)
        return MathAuditResult(has_contradiction=False, tracked_claims_count=len(self.claims_history))

    def _update_ledger(self, claims: List[NumericClaim]):
        for c in claims:
            self.ledger[c.category] = c

    def get_summary(self) -> Dict[str, Any]:
        """Summary of math and contradiction audits for post-debate debrief."""
        return {
            "total_claims_tracked": len(self.claims_history),
            "math_contradictions_count": len(self.discrepancy_history),
            "ledger": {k: v.to_dict() for k, v in self.ledger.items()},
            "discrepancies": [d.to_dict() for d in self.discrepancy_history],
        }
