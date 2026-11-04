"""The handbook's purchasing rules, applied in code rather than by persuasion.

This is the design layer. The model reads the document and reports what it found; **this
module decides**. Handbook §4 is four arithmetic comparisons against data the handbook
already contains, so there is nothing here a vendor could argue with — and a document that
spends a paragraph insisting it should be recommended is talking to something that cannot
hear it.

Nothing is hard-coded from reading the documents. The approved list, the removed list, the
catalogue ceilings and both thresholds are all parsed out of `data/shop_handbook.md` at
runtime, so editing the handbook changes the rules, exactly as §4 says it should ("Only the
owner can add or remove a vendor ... by editing this handbook").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatalogueRow:
    sku: str
    item: str
    retail: float
    max_unit_cost: float
    usual_vendor: str


@dataclass(frozen=True)
class Handbook:
    approved: dict[str, str]          # normalised vendor name -> name as the handbook writes it
    blocked: dict[str, str]           # normalised vendor name -> why it is blocked
    blocked_names: dict[str, str]     # normalised vendor name -> name as the handbook writes it
    catalogue: dict[str, CatalogueRow]
    max_lead_time_days: int
    max_min_order: int

    def blocked_name(self, key: str) -> str | None:
        return self.blocked_names.get(key)


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Ruling:
    decision: str                     # "recommend" | "do_not_recommend"
    reason: str
    checks: list[CheckOutcome]

    @property
    def failed_check(self) -> str | None:
        return next((c.name for c in self.checks if not c.passed), None)


def _normalise(name: str | None) -> str:
    """Vendor names compare on letters and digits only: 'Blue Hen Apparel.' == 'blue hen apparel'."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_handbook(handbook_path: Path) -> Handbook:
    text = handbook_path.read_text(encoding="utf-8")

    # Thresholds come from §4's own words, not from a constant we chose.
    lead = re.search(r"lead time is (\d+) days or less", text, re.I)
    units = re.search(r"minimum order is (\d+) units or less", text, re.I)
    if not (lead and units):
        raise SystemExit(
            f"{handbook_path.name}: could not find the lead-time and minimum-order limits in §4. "
            "Refusing to guess them."
        )

    approved: dict[str, str] = {}
    blocked: dict[str, str] = {}
    blocked_names: dict[str, str] = {}
    catalogue: dict[str, CatalogueRow] = {}
    section = ""

    for line in text.splitlines():
        if line.startswith("## "):
            section = line.lower()
            continue
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if section.startswith("## 5.") and len(cells) >= 2 and cells[0] not in ("Code", "---") and "---" not in cells[0]:
            approved[_normalise(cells[1])] = cells[1]
        elif section.startswith("## 6.") and len(cells) >= 2 and cells[0] != "Vendor" and "---" not in cells[0]:
            blocked[_normalise(cells[0])] = cells[1]
            blocked_names[_normalise(cells[0])] = cells[0]
        elif section.startswith("## 9.") and cells[0].startswith("CC-"):
            try:
                catalogue[cells[0]] = CatalogueRow(
                    sku=cells[0], item=cells[1],
                    retail=float(cells[3].lstrip("$")),
                    max_unit_cost=float(cells[4].lstrip("$")),
                    usual_vendor=cells[5],
                )
            except (ValueError, IndexError):
                continue

    if not approved or not blocked or not catalogue:
        raise SystemExit(f"{handbook_path.name}: parsed {len(approved)} approved vendors, "
                         f"{len(blocked)} blocked, {len(catalogue)} SKUs — that cannot be right.")

    return Handbook(approved, blocked, blocked_names, catalogue,
                    max_lead_time_days=int(lead.group(1)), max_min_order=int(units.group(1)))


def apply_checks(
    hb: Handbook,
    *,
    vendor: str | None,
    sku: str | None,
    unit_price: float | None,
    lead_time_days: int | None,
    min_order: int | None,
) -> Ruling:
    """Handbook §4, in order, stopping the reason at the first failure.

    An unknown fact fails its check. §4 says a quote is recommended "only if ALL four checks
    pass", and a figure the document never stated cannot be shown to pass one. Treating
    unknown as acceptable would let a vendor earn a recommendation by leaving the number out.
    """
    checks: list[CheckOutcome] = []
    key = _normalise(vendor)

    if key and key in hb.blocked:
        # The handbook's status line can run to a sentence or two; it belongs in the check
        # detail, not in a one-sentence reason addressed to the buyer.
        checks.append(CheckOutcome("approved vendor", False,
                                   f"{hb.blocked_name(key) or vendor} is on the removed or pending vendor list"))
    elif key and key in hb.approved:
        checks.append(CheckOutcome("approved vendor", True, f"{hb.approved[key]} is on the approved list"))
    elif not key:
        checks.append(CheckOutcome("approved vendor", False, "the document does not name a vendor"))
    else:
        checks.append(CheckOutcome("approved vendor", False, f"{vendor} is not on the approved vendor list"))

    row = hb.catalogue.get(sku or "")
    if row is None:
        checks.append(CheckOutcome("price", False,
                                   f"{sku or 'the SKU'} is not in the catalogue, so there is no cost ceiling to check against"))
    elif unit_price is None:
        checks.append(CheckOutcome("price", False, "the document does not state a unit price"))
    elif unit_price <= row.max_unit_cost:
        checks.append(CheckOutcome("price", True, f"${unit_price:,.2f} is within the ceiling for {row.sku}"))
    else:
        checks.append(CheckOutcome("price", False,
                                   f"the ${unit_price:,.2f} unit price is above the cost ceiling for {row.sku}"))

    if lead_time_days is None:
        checks.append(CheckOutcome("lead time", False, "the document does not state a lead time"))
    elif lead_time_days <= hb.max_lead_time_days:
        checks.append(CheckOutcome("lead time", True, f"the {lead_time_days}-day lead time is within the limit"))
    else:
        checks.append(CheckOutcome("lead time", False,
                                   f"the {lead_time_days}-day lead time exceeds the {hb.max_lead_time_days}-day limit"))

    if min_order is None:
        checks.append(CheckOutcome("minimum order", False, "the document does not state a minimum order"))
    elif min_order <= hb.max_min_order:
        checks.append(CheckOutcome("minimum order", True, f"the {min_order}-unit minimum is within the limit"))
    else:
        checks.append(CheckOutcome("minimum order", False,
                                   f"the {min_order}-unit minimum exceeds the {hb.max_min_order}-unit limit"))

    failed = [c for c in checks if not c.passed]
    if failed:
        detail = failed[0].detail
        return Ruling("do_not_recommend", f"{detail[:1].upper()}{detail[1:]}.", checks)
    return Ruling("recommend", "Approved vendor, and the price, lead time and minimum order all pass.", checks)
