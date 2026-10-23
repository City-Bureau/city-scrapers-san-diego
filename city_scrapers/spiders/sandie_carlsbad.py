"""
This file dynamically creates spider classes for the spider factory
mixin that City of Carlsbad agencies use.

City of Carlsbad calendar (department "City Hall"):
https://www.carlsbadca.gov/departments/calendar
Attachments: https://www.carlsbadca.gov/city-hall/meetings-agendas and the
Laserfiche records portal (https://records.carlsbadca.gov/WebLink)
Videos: https://carlsbadca.new.swagit.com/views/295
"""

from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CITY_COUNCIL,
    COMMISSION,
)

from city_scrapers.mixins.sandie_carlsbad import SandieCarlsbadMixin

"""
City of Carlsbad- Boards & Commissions:

- Agricultural Conversion Mitigation Fee Citizens Advisory Committee
- Arts Commission
- Community-Police Engagement Commission
- Environmental Sustainability Commission
- Historic Preservation Commission
- Housing Commission
- Investment Review Board
- Library Board of Trustees
- Parks & Recreation Commission
- Planning Commission
- Senior Commission
- Traffic Safety & Mobility Commission

City of Carlsbad- City Council Committees:

- City Council

Keywords are matched against calendar titles with "&" read as "and" and
hyphens as spaces. laserfiche_packets_id is the board's folder under Meeting
Packets in the Laserfiche portal; laserfiche_agendas_id is its "Past
materials" folder. The Investment Review Board page links to the Agricultural
committee's folder by mistake, so its own folder id is used instead.
swagit_tab is the tab of the Swagit video archive
(https://carlsbadca.new.swagit.com/views/295) that has the board's videos.
"""

spider_configs = [
    {
        "class_name": "SandieCarlsbadBoardsCommissionsSpider",
        "name": "sandie_carlsbad_boards_commissions",
        "agency": "City of Carlsbad- Boards & Commissions",
        # The ticket's is_main agency; read by the Airtable slug sync workflow
        "is_main": True,
        # Joint meetings with the City Council are scraped by the council spider
        "exclude_keywords": ["subcommittee", "city council"],
        "boards": [
            {
                "title": "Agricultural Conversion Mitigation Fee Citizens Advisory Committee",  # noqa
                "keywords": ["agricultural conversion mitigation"],
                "classification": ADVISORY_COMMITTEE,
                "page": "boards-commissions/agricultural-conversion-mitigation-fee-committee",  # noqa
                "laserfiche_packets_id": 9032259,
                "laserfiche_agendas_id": 4486079,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Arts Commission",
                "keywords": ["arts commission"],
                "classification": COMMISSION,
                "page": "boards-commissions/arts-commission",
                "laserfiche_packets_id": 9025976,
                "laserfiche_agendas_id": 4486083,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Community-Police Engagement Commission",
                "keywords": ["community police engagement"],
                "classification": COMMISSION,
                "page": "boards-commissions/community-police-engagement-commission",
                "laserfiche_packets_id": 9105025,
                "laserfiche_agendas_id": 6439528,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Environmental Sustainability Commission",
                "keywords": ["environmental sustainability"],
                "classification": COMMISSION,
                "page": "boards-commissions/environmental-sustainability-commission",
                "laserfiche_packets_id": 10525990,
                "laserfiche_agendas_id": 10509314,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Historic Preservation Commission",
                "keywords": ["historic preservation"],
                "classification": COMMISSION,
                "page": "boards-commissions/historic-preservation",
                "laserfiche_packets_id": 9025953,
                "laserfiche_agendas_id": 4486713,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Housing Commission",
                "keywords": ["housing commission"],
                "classification": COMMISSION,
                "page": "boards-commissions/housing-commission",
                "laserfiche_packets_id": 9040172,
                "laserfiche_agendas_id": 4486738,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Investment Review Board",
                "keywords": ["investment review board"],
                "classification": BOARD,
                "page": "boards-commissions/investment-review-board",
                "laserfiche_packets_id": 10437377,
                "laserfiche_agendas_id": 10589669,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Library Board of Trustees",
                "keywords": ["library board"],
                "classification": BOARD,
                "page": "boards-commissions/library-board-of-trustees",
                "laserfiche_packets_id": 9018616,
                "laserfiche_agendas_id": 4486793,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Parks & Recreation Commission",
                "keywords": ["parks and recreation"],
                "classification": COMMISSION,
                "page": "boards-commissions/parks-recreation",
                "laserfiche_packets_id": 9017117,
                "laserfiche_agendas_id": 4486856,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Planning Commission",
                "keywords": ["planning commission"],
                "classification": COMMISSION,
                "page": "boards-commissions/planning-commission",
                "laserfiche_packets_id": 9016857,
                "laserfiche_agendas_id": 4486888,
                "swagit_tab": "planning-commission",
            },
            {
                "title": "Senior Commission",
                "keywords": ["senior commission"],
                "classification": COMMISSION,
                "page": "boards-commissions/senior-commission",
                "laserfiche_packets_id": 9025949,
                "laserfiche_agendas_id": 4487023,
                "swagit_tab": "all-boards-commissions",
            },
            {
                "title": "Traffic Safety & Mobility Commission",
                "keywords": ["traffic safety and mobility", "traffic and mobility"],
                "classification": COMMISSION,
                "page": "boards-commissions/traffic-mobility-commission",
                "laserfiche_packets_id": 9108623,
                "laserfiche_agendas_id": 7094634,
                "swagit_tab": "traffic-mobility",
            },
        ],
    },
    {
        "class_name": "SandieCarlsbadCouncilCommitteesSpider",
        "name": "sandie_carlsbad_council_committees",
        "agency": "City of Carlsbad- City Council Committees",
        "boards": [
            {
                "title": "City Council",
                "keywords": ["city council"],
                # Subcommittees and the City/Schools Committee aren't in this
                # agency's ticket scope
                "exclude": ["committee"],
                "classification": CITY_COUNCIL,
                "page": "",
                "laserfiche_packets_id": 9016814,
                "laserfiche_agendas_id": 4486195,
                "swagit_tab": "city-council",
            },
        ],
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
                (SandieCarlsbadMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
