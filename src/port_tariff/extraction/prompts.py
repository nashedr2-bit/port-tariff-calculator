"""
Rule-extraction prompt design.

The prompt is the heart of the automation criterion: it instructs the LLM to
READ a tariff document section and emit a structured TariffRule as JSON. The
LLM finds and interprets the rule; it never calculates.

Design choices baked into the prompt:
  * Output MUST be a single JSON object matching our schema -> parseable,
    validatable, no free-form prose to scrape.
  * The LLM is told the vessel context (port, tariff type) so it selects the
    correct port column and the correct rate basis.
  * It is explicitly instructed NOT to do arithmetic -- only to extract the
    rule's structure and rates. Calculation is Python's job.
  * It must report the source section/page for traceability.
  * It is warned about the known interpretation traps (per-100t vs per-metre,
    the x2 service multiplier for movement services) in GENERAL terms, so the
    guidance generalises to other ports rather than hardcoding Durban answers.
"""

from __future__ import annotations

SCHEMA_DESCRIPTION = """
Return a SINGLE JSON object with these fields:

{
  "tariff_type": string,        // e.g. "light_dues", "port_dues", "pilotage_dues"
  "port": string,               // the port this rule applies to
  "currency": string,           // e.g. "ZAR"
  "basis": string,              // one of:
                                //   "per_gt_raw"        (rate x raw gross tonnage)
                                //   "per_100t_ceiling"  (rate x ceil(GT/100))
                                //   "per_metre_loa"     (rate x ceil(length))
                                //   "flat"              (a fixed fee)
  "basic_fee": number,          // fixed base fee (0 if none)
  "rate_per_unit": number,      // rate per unit of the basis (0 if none)
  "time_rate_per_unit": number, // per-unit-per-day rate on top (0 if none;
                                //   used by port dues: per 100t per 24h)
  "services": integer,          // 1 normally; 2 for movement services that are
                                //   charged both entering AND leaving
                                //   (pilotage, towage, berthing/running lines)
  "minimum_fee": number|null,   // floor, or null
  "tiers": [                    // ONLY for tiered charges (e.g. towage). Else []
    {
      "floor": number,          // lower tonnage bound (inclusive)
      "ceiling": number|null,   // upper bound (exclusive); null = open-ended
      "base_fee": number,       // fixed fee for vessels in this band
      "increment_per_100t": number  // added per 100t above this band's floor
    }
  ],
  "source_section": string,     // e.g. "3.3"
  "source_page": string,        // e.g. "p13"
  "notes": string               // any interpretation note
}
""".strip()

EXTRACTION_GUIDANCE = """
Critical interpretation rules (apply generally, to ANY port/document):

1. "per 100 tons or part thereof" -> basis "per_100t_ceiling".
   "per GT" / "per gross ton" (no 100-ton blocking) -> basis "per_gt_raw".
   "per metre / per metre of length overall" -> basis "per_metre_loa".

2. Many tables have one COLUMN PER PORT. Select the column for the requested
   port. If the requested port has no dedicated column but an "Other Ports"
   (or similar) column exists, use that.

3. SERVICES MULTIPLIER: marine movement services are charged for BOTH the
   inward and outward movement. If the tariff is pilotage, towage/tug
   assistance, or berthing/running of lines, set "services" to 2 unless the
   document clearly states otherwise. Stationary/period charges (light dues,
   port dues, VTS) use "services": 1.

4. TIERED tables (rate depends on which tonnage band the vessel falls in):
   populate "tiers" with every band. Each band's "increment_per_100t" applies
   per 100 tons ABOVE that band's floor.

5. DO NOT perform any arithmetic or compute a final amount. Only extract the
   rule's structure and rates. A separate deterministic engine does the maths.

6. If a value is genuinely absent, use 0 (or null for minimum_fee), and say so
   in "notes". Never invent a rate.

7. NAMING vs STRUCTURE (resolve by service, not by title). A requested charge
   may map to a section whose TITLE differs from the charge name, and a document
   may contain a similarly-named section that is a different, narrower service.
   Do NOT select a section on title match alone. Apply this ordered test:
     (a) Identify every section that could plausibly cover the requested
         charge, including sections whose title is not an exact match.
     (b) For each candidate, look at the physical SERVICE it describes and its
         charge STRUCTURE.
     (c) A charge that scales with vessel size (a "basic fee + per-100-ton
         rate", or any tonnage-scaled structure) reflects a size-dependent
         operation on the vessel. A single flat per-service line reflects a
         minor fixed task. Marine handling of a large vessel alongside
         (securing/mooring/lines) is a size-dependent operation and is normally
         billed by the tonnage-scaled structure.
     (d) Therefore, when one candidate is tonnage-scaled and another is a flat
         per-service fee, SELECT THE TONNAGE-SCALED ONE, even if the flat
         section's title is a closer match to the requested charge name. The
         tonnage-scaled structure is the stronger signal of the correct charge.
     (e) Record in "notes" every candidate you considered and why you chose the
         one you did.
   This is a general rule about resolving title-vs-structure conflicts in any
   tariff document; it is not specific to any one port or charge.
""".strip()


def build_extraction_prompt(
    tariff_type: str,
    port: str,
    document_excerpt: str,
) -> str:
    """Construct the full extraction prompt for one tariff at one port."""
    return f"""You are a maritime port-tariff analyst. Read the tariff document
excerpt below and extract the calculation rule for the following charge.

TARIFF TYPE: {tariff_type}
PORT: {port}

{EXTRACTION_GUIDANCE}

{SCHEMA_DESCRIPTION}

Respond with ONLY the JSON object, no markdown fences, no commentary.

--- DOCUMENT EXCERPT START ---
{document_excerpt}
--- DOCUMENT EXCERPT END ---
""".strip()
