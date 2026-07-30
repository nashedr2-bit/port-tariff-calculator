"""
Durban tariff rules as hand-written fixtures.

IMPORTANT FRAMING:
In the production system, these TariffRule objects are produced at RUNTIME by
the LLM extraction layer reading the Transnet PDF. They are written by hand
HERE, in the test suite, for one reason only: to validate that the
deterministic calculation engine is correct, independently of the LLM.

In other words, these fixtures are the "ground-truth rules" -- the correct
answer the extraction layer must reproduce. The engine is tested against them;
the extraction layer is later tested by comparing its output to them.

Every value below is traced to its Transnet Tariff Book source section/page.
"""

from port_tariff.rules.schema import ChargeBasis, TariffRule, Tier

# 1. LIGHT DUES -- section 1.1.1, printed p09
#    Visiting vessel: 117.08 per 100 tons or part thereof, charged once.
LIGHT_DUES_DURBAN = TariffRule(
    tariff_type="light_dues",
    port="Durban",
    basis=ChargeBasis.PER_100T_CEILING,
    rate_per_unit=117.08,
    services=1,
    source_section="1.1.1",
    source_page="p09",
    notes="Visiting vessel uses per-100t rate (117.08), not the per-metre "
    "registered-port rate (24.64).",
)

# 2. PORT DUES -- section 4.1.1, printed p21
#    192.73 per 100t basic + 57.79 per 100t per 24h (pro rata).
PORT_DUES_DURBAN = TariffRule(
    tariff_type="port_dues",
    port="Durban",
    basis=ChargeBasis.PER_100T_CEILING,
    rate_per_unit=192.73,
    time_rate_per_unit=57.79,
    services=1,
    source_section="4.1.1",
    source_page="p21",
    notes="Time component uses chargeable_days (entrance-to-entrance basis).",
)

# 3. VTS DUES -- section 2.1.1, printed p11
#    0.65 per GT for Durban/Saldanha; minimum fee 235.52.
VTS_DUES_DURBAN = TariffRule(
    tariff_type="vts_dues",
    port="Durban",
    basis=ChargeBasis.PER_GT_RAW,
    rate_per_unit=0.65,
    services=1,
    minimum_fee=235.52,
    source_section="2.1.1",
    source_page="p11",
)

# 4. PILOTAGE DUES -- section 3.3, printed p13
#    Durban: basic 18,608.61 + 9.72 per 100t; x2 services (in + out).
PILOTAGE_DUES_DURBAN = TariffRule(
    tariff_type="pilotage_dues",
    port="Durban",
    basis=ChargeBasis.PER_100T_CEILING,
    basic_fee=18608.61,
    rate_per_unit=9.72,
    services=2,
    source_section="3.3",
    source_page="p13",
    notes="Charged per movement: entry + departure = 2 services.",
)

# 5. TOWAGE DUES -- section 3.6, printed p15
#    Durban tiered bands; x2 services (in + out).
TOWAGE_DUES_DURBAN = TariffRule(
    tariff_type="towage_dues",
    port="Durban",
    basis=ChargeBasis.PER_100T_CEILING,
    services=2,
    tiers=[
        Tier(floor=0, ceiling=2000, base_fee=8140.00, increment_per_100t=0.0),
        Tier(floor=2000, ceiling=10000, base_fee=12633.99, increment_per_100t=268.99),
        Tier(floor=10000, ceiling=50000, base_fee=38494.51, increment_per_100t=84.95),
        Tier(floor=50000, ceiling=100000, base_fee=73118.07, increment_per_100t=32.24),
        Tier(floor=100000, ceiling=None, base_fee=93548.13, increment_per_100t=23.65),
    ],
    source_section="3.6",
    source_page="p15",
    notes="Increment applies per 100t above the matched tier's floor.",
)

# 6. RUNNING LINES -- reconciles to BERTHING section 3.8, printed p17
#    Durban uses 'Other Ports' column: basic 2,801.91 + 13.68 per 100t;
#    x2 services (berth + unberth).
RUNNING_LINES_DURBAN = TariffRule(
    tariff_type="running_lines",
    port="Durban",
    basis=ChargeBasis.PER_100T_CEILING,
    basic_fee=2801.91,
    rate_per_unit=13.68,
    services=2,
    source_section="3.8",
    source_page="p17",
    notes="Ground-truth 'Running Lines' reconciles to the BERTHING formula "
    "(3.8), not the Running-of-Lines table (3.9). Durban uses 'Other Ports' "
    "column.",
)

ALL_DURBAN_RULES = {
    "light_dues": LIGHT_DUES_DURBAN,
    "port_dues": PORT_DUES_DURBAN,
    "vts_dues": VTS_DUES_DURBAN,
    "pilotage_dues": PILOTAGE_DUES_DURBAN,
    "towage_dues": TOWAGE_DUES_DURBAN,
    "running_lines": RUNNING_LINES_DURBAN,
}
