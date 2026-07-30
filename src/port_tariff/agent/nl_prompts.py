"""
Natural-language query parsing prompt.

Turns free-text vessel queries into the structured fields the system already
handles. The LLM does language understanding only -- it extracts explicit
facts from the prose. It performs no calculation and invents no values.
"""

from __future__ import annotations

NL_QUERY_SCHEMA = """
Return a SINGLE JSON object with these fields:

{
  "port": string,               // the port named in the query
  "gross_tonnage": number,      // vessel gross tonnage (GT)
  "loa_meters": number,         // length overall in metres (0 if not stated)
  "chargeable_days": number,    // days alongside / in port (0 if not stated)
  "vessel_name": string|null,   // vessel name if stated, else null
  "tariffs": [string]|null      // specific tariffs requested, else null for ALL
                                //   use canonical names: light_dues, port_dues,
                                //   vts_dues, pilotage_dues, towage_dues,
                                //   running_lines
}
""".strip()

NL_QUERY_GUIDANCE = """
Rules:
- Extract ONLY values explicitly present in the query. If a value is not
  stated, use 0 (numbers) or null (vessel_name / tariffs). Never guess or
  invent tonnage, days, or a port.
- "GT", "gross tonnage", "gross tons" -> gross_tonnage.
- "LOA", "length", "length overall" -> loa_meters.
- "days alongside", "days in port", "berthed for N days" -> chargeable_days.
- If the query asks for "all dues"/"all tariffs"/"everything", set tariffs to
  null (meaning all).
- If it names specific charges, map them to the canonical names and list them.
- Do not perform any calculation. Only extract facts.
""".strip()


def build_nl_query_prompt(query_text: str) -> str:
    return f"""You are a maritime operations assistant. Extract the structured
vessel query from the natural-language request below.

{NL_QUERY_GUIDANCE}

{NL_QUERY_SCHEMA}

Respond with ONLY the JSON object, no markdown fences, no commentary.

--- QUERY START ---
{query_text}
--- QUERY END ---
""".strip()
