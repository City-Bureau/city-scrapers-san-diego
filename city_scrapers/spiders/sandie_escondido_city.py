"""
This file dynamically creates spider classes for the spider factory
mixin that agencies use.

Total 8 agencies. Each one's `microsite_id` is its value in the
"field_microsite_tid" filter of https://escondido-ca.municodemeetings.com/

All agencies except the City Council, whose meetings are listed on the portal
a year ahead, also scrape upcoming meetings from the "City Meetings" calendar
of https://ca-escondido.civicplus.com/calendar.aspx whose titles match their
`calendar_pattern`.
"""

from city_scrapers_core.constants import BOARD, CITY_COUNCIL, COMMISSION, COMMITTEE

from city_scrapers.mixins.sandie_escondido_city import SandieEscondidoCityMixin

MITCHELL_ROOM = {
    "name": "Escondido City Hall, Mitchell Room",
    "address": "201 N. Broadway, Escondido, CA 92025",
}

spider_configs = [
    # 1
    {
        "class_name": "SandieEscondidoCityBuildingAdvisoryAndAppealsBoardSpider",
        "name": "sandie_escondido_building_advisory_and_appeals_board",
        "agency": "City of Escondido - Building Advisory and Appeals Board",
        "microsite_id": 1,
        "classification": BOARD,
        "location": MITCHELL_ROOM,
        "calendar_pattern": r"building\s+advisory",
    },
    # 2
    {
        "class_name": "SandieEscondidoCityCityCouncilSpider",
        "name": "sandie_escondido_city_council",
        "agency": "City of Escondido - City Council",
        "microsite_id": 2,
        "classification": CITY_COUNCIL,
    },
    # 3
    {
        "class_name": "SandieEscondidoCityHistoricPreservationCommissionSpider",
        "name": "sandie_escondido_historic_preservation_commission",
        "agency": "City of Escondido - Historic Preservation Commission",
        "microsite_id": 3,
        "classification": COMMISSION,
        "calendar_pattern": r"historic\s+preservation",
    },
    # 4
    {
        "class_name": "SandieEscondidoCityLibraryBoardOfTrusteesSpider",
        "name": "sandie_escondido_library_board_of_trustees",
        "agency": "City of Escondido - Library Board of Trustees",
        "microsite_id": 4,
        "classification": BOARD,
        "calendar_pattern": r"library\s+board",
    },
    # 5
    {
        "class_name": "SandieEscondidoCityPlanningCommissionSpider",
        "name": "sandie_escondido_planning_commission",
        "agency": "City of Escondido - Planning Commission",
        "microsite_id": 5,
        "classification": COMMISSION,
        "calendar_pattern": r"planning\s+commission",
    },
    # 6
    {
        "class_name": "SandieEscondidoCityPublicArtCommissionSpider",
        "name": "sandie_escondido_public_art_commission",
        "agency": "City of Escondido - Public Art Commission",
        "microsite_id": 6,
        "classification": COMMISSION,
        "calendar_pattern": r"public\s+art\s+commission",
        # Public Art Commission subcommittees are listed with the subcommittees
        "calendar_exclude_pattern": r"subcommittee",
    },
    # 7
    {
        "class_name": "SandieEscondidoCityTransportationCommissionSpider",
        "name": "sandie_escondido_transportation_commission",
        "agency": "City of Escondido - Transportation Commission",
        "microsite_id": 7,
        "classification": COMMISSION,
        # e.g. "Transportation and Community Safety Commission"
        "calendar_pattern": r"transportation\b.*\bcommission",
    },
    # 8
    {
        "class_name": "SandieEscondidoCitySubcommitteeSpider",
        "name": "sandie_escondido_subcommittees",
        "agency": "City of Escondido - Subcommittees",
        "microsite_id": 8,
        "classification": COMMITTEE,
        "location": MITCHELL_ROOM,
        "calendar_pattern": r"subcommittee",
        # Two subcommittees can meet at the same time
        "calendar_match_title": True,
    },
]


def create_spiders():
    """
    Dynamically create spider classes using the spider_configs list
    and register them in the global namespace.
    """
    for config in spider_configs:
        class_name = config["class_name"]

        if class_name not in globals():
            # Build attributes dict without class_name to avoid duplication.
            # We make sure that the class_name is not already in the global namespace
            # Because some scrapy CLI commands like `scrapy list` will inadvertently
            # declare the spider class more than once otherwise
            attrs = {k: v for k, v in config.items() if k != "class_name"}

            # Dynamically create the spider class
            spider_class = type(
                class_name,
                (SandieEscondidoCityMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
