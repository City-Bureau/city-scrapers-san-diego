"""
This file dynamically creates spider classes for the spider factory
mixin that agencies use.

Total 3 agencies
"""

from city_scrapers.mixins.sandie_sandag import SandieSandagMixin

spider_configs = [
    {
        "class_name": "SandagBoardOfDirectorsCommitteesSpider",
        "name": "sandag_board_of_directors_committees",
        "agency": "SANDAG-Board of Directors Committees",
        "meeting_view_id": {
            1: "https://www.sandag.org/meetings-and-events/policy-advisory-committees/audit",  # noqa
            2: "https://www.sandag.org/meetings-and-events/board-of-directors",
            3: "https://www.sandag.org/meetings-and-events/policy-advisory-committees/borders",  # noqa
            4: "https://www.sandag.org/meetings-and-events/policy-advisory-committees/executive",  # noqa
            5: "https://www.sandag.org/meetings-and-events/policy-advisory-committees/public-safety",  # noqa
            6: "https://www.sandag.org/meetings-and-events/policy-advisory-committees/regional-planning",  # noqa
            7: "https://www.sandag.org/meetings-and-events/policy-advisory-committees/transportation",  # noqa
        },
    },
    {
        "class_name": "SandagTransNetIndependentTaxpayerOversightCommitteeSpider",
        "name": "sandag_transnet_independent_taxpayer_oversight_committee",
        "agency": "SANDAG-TransNet Independent Taxpayer Oversight Committee",
        "meeting_view_id": {
            15: "https://www.sandag.org/meetings-and-events/transnet-independent-taxpayer-oversight",  # noqa
        },
    },
    {
        "class_name": "SandagWorkingGroupsSpider",
        "name": "sandag_working_groups",
        "agency": "SANDAG-Working Groups",
        "meeting_view_id": {
            8: "https://www.sandag.org/meetings-and-events/working-groups/chiefs-sheriffs",  # noqa
            13: "https://www.sandag.org/meetings-and-events/working-groups/social-services-transportation",  # noqa
        },
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
                (SandieSandagMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
