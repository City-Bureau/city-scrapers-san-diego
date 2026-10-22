from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
)

from city_scrapers.mixins.sandie_encinitas import SandieEncinitasMixin

CITY_HALL = {
    "name": "Encinitas City Hall",
    "address": "505 S. Vulcan Avenue, Encinitas, CA 92024",
}

spider_configs = [
    {
        "class_name": "SandieEncinitasCouncilCommitteesSpider",
        "name": "sandie_encinitas_council_committees",
        "agency": "City of Encinitas- City Council Committees",
        # e.g. "Regular Encinitas Public Financing Authority - 6:00 p.m.
        # (immediately following the City Council meeting)"
        "exclude_pattern": r"public financing authority",
        "bodies": [
            {
                # Regular, special, closed session and joint meetings
                "pattern": r"city\s+council",
                "panel": "City Council",
                "classification": CITY_COUNCIL,
            },
            {
                "pattern": r"cultural\s+tourism\s+committee",
                "panel": "Committees, Subcommittees, and Task Forces",
                "classification": COMMITTEE,
                "location": CITY_HALL,
            },
            {
                "pattern": r"school\s+district\s+liaison\s+committee",
                "panel": "Committees, Subcommittees, and Task Forces",
                "classification": COMMITTEE,
                "location": CITY_HALL,
            },
            {
                "pattern": r"skate\s+feature\s+committee",
                "panel": "Committees, Subcommittees, and Task Forces",
                "classification": COMMITTEE,
                "location": CITY_HALL,
            },
        ],
        "is_main": True,
    },
    {
        "class_name": "SandieEncinitasBoardsCommissionsSpider",
        "name": "sandie_encinitas_boards_commissions",
        "agency": "City of Encinitas- Boards & Commissions",
        # Joint meetings with the City Council are scraped by the council spider
        "exclude_pattern": r"city\s+council",
        "bodies": [
            {
                "pattern": r"planning\s+commission",
                "panel": "Planning Commission",
                "classification": COMMISSION,
            },
            {
                # Listed before the Environmental Commission so joint meetings
                # of the two are classified as an advisory committee
                "pattern": r"urban\s+forest\s+advisory\s+committee|\bufac\b",
                "panel": "Urban Forest Advisory Committee",
                "classification": ADVISORY_COMMITTEE,
            },
            {
                "pattern": r"environmental\s+commission",
                "panel": "Environmental Commission",
                "classification": COMMISSION,
            },
            {
                "pattern": r"youth\s+commission",
                "panel": "Youth Commission",
                "classification": COMMISSION,
            },
            {
                "pattern": r"commission\s+for\s+the\s+arts",
                "panel": "Commission for the Arts",
                "classification": COMMISSION,
            },
            {
                "pattern": r"public\s+health\s+(?:and|&)\s+safety\s+commission|\bphs\s+commission",  # noqa
                "panel": "Public Health and Safety Commission",
                "classification": COMMISSION,
            },
            {
                "pattern": r"parks\s+(?:and|&)\s+recreation\s+commission",
                "panel": "Parks and Recreation Commission",
                "classification": COMMISSION,
            },
            {
                "pattern": r"encinitas\s+ranch\s+golf\s+authority|\berga\b",
                "panel": "Encinitas Ranch Golf Authority",
                "classification": BOARD,
                "location": {
                    "name": "Encinitas Ranch Golf Course Clubhouse",
                    "address": "1275 Quail Gardens Drive, Encinitas, CA 92024",
                },
            },
            {
                "pattern": r"senior\s+(?:citizen\s+)?commission",
                "panel": "Senior Commission",
                "classification": COMMISSION,
            },
            {
                # Also matches "Mobility and Traffic Commission Special Meeting"
                "pattern": r"mobility\s+(?:and|&)\s+traffic\s+(?:safety\s+)?commission",
                "panel": "Mobility & Traffic Safety Commission",
                "classification": COMMISSION,
            },
            {
                "pattern": r"affordable\s+housing\s+task\s+force",
                "panel": "Committees, Subcommittees, and Task Forces",
                "classification": COMMITTEE,
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
                (SandieEncinitasMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
