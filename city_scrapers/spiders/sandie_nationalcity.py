"""
This file dynamically creates spider classes for the spider factory
mixin that National City agencies use.

National City Boards & Commissions and City Council Committees
https://www.nationalcityca.gov/government/boards-commissions-committees
"""

from city_scrapers.mixins.sandie_nationalcity import SandieNationalCityMixin

"""
National City Boards & Commissions and City Council Committees:

City of National City

- City council

Boards & Commissions:

- Board of Library Trustees
- Civil Service Commission
- Community and Police Relations Commission
- Planning Commission
- Port Commission
- Parks, Recreation and Senior Citizen’s Advisory Committee
- Public Arts Committee
- Housing Advisory Committee
- Sweetwater Authority
- Traffic Safety Committee
"""

spider_configs = [
    {
        "class_name": "SandieCityCouncilSpider",
        "name": "sandie_citycouncil",
        "agency": "Sandie City Council",
        "event_type": "City Council",
    },
    {
        "class_name": "SandieBoardsCommissionsSpider",
        "name": "sandie_boards_commissions",
        "agency": "Sandie Boards and Commissions",
        "event_type": [
            "Board of Library Trustees",
            "Library Board",
            "Civil Service Commission",
            "Community and Police Relations",
            "Planning Commission",
            "Port Commission",
            "Recreation",
            "Public Arts",
            "Public Art",
            "Housing Advisory",
            "Sweetwater Authority",
            "Traffic Safety",
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
                (SandieNationalCityMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
