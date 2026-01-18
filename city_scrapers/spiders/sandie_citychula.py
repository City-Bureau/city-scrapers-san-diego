"""
This file dynamically creates spider classes for the spider factory
mixin that agencies use.
"""

from city_scrapers.mixins.sandie_citychula import ChulaVistaMixin

"""
# San Diego City of Chula Vista: 
"""

spider_configs = [
    {
        "class_name": "ChulaVistaBoardOfEthicsSpider",
        "name": "chula_vista_board_of_ethics",
        "agency": "City of Chula Vista - Board of Ethics",
        "id": "chula_vista_board_of_ethics",
        "meeting_view_id": 15,
    },
    {
        "class_name": "ChulaVistaBoardOfAppealsAdvisorsSpider",
        "name": "chula_vista_board_of_appeals_advisors",
        "agency": "City of Chula Vista - Board of Appeals & Advisors",
        "id": "chula_vista_board_of_appeals_advisors",
        "meeting_view_id": 14,
    },
    {
        "class_name": "ChulaVistaBoardOfLibraryTrusteesSpider",
        "name": "chula_vista_board_of_library_trustees",
        "agency": "City of Chula Vista - Board of Library Trustees",
        "id": "chula_vista_board_of_library_trustees",
        "meeting_view_id": 16,
    },
    {
        "class_name": "ChulaVistaCharterReviewCommissionSpider",
        "name": "chula_vista_charter_review_commission",
        "agency": "City of Chula Vista - Charter Review Commission",
        "id": "chula_vista_charter_review_commission",
        "meeting_view_id": 17,
    },
    {
        "class_name": "ChulaVistaCivilServiceCommissionSpider",
        "name": "chula_vista_civil_service_commission",
        "agency": "City of Chula Vista - Civil Service Commission",
        "id": "chula_vista_civil_service_commission",
        "meeting_view_id": 18,
    },
    {
        "class_name": "ChulaVistaCulturalArtsCommissionSpider",
        "name": "chula_vista_cultural_arts_commission",
        "agency": "City of Chula Vista - Cultural Arts Commission",
        "id": "chula_vista_cultural_arts_commission",
        "meeting_view_id": 20,
    },
    {
        "class_name": "ChulaVistaHealthWellnessAgingCommissionSpider",
        "name": "chula_vista_health_wellness_aging_commission",
        "agency": "City of Chula Vista - Health Wellness and Aging Commission",
        "id": "chula_vista_health_wellness_aging_commission",
        "meeting_view_id": 22,
    },
    {
        "class_name": "ChulaVistaHousingHomelessnessAdvisoryCommissionSpider",
        "name": "chula_vista_housing_homelessness_advisory_commission",
        "agency": "City of Chula Vista - Housing and Homelessness Advisory Commission",
        "id": "chula_vista_housing_homelessness_advisory_commission",
        "meeting_view_id": 23,
    },
    {
        "class_name": "ChulaVistaHumanRelationsCommissionSpider",
        "name": "chula_vista_human_relations_commission",
        "agency": "City of Chula Vista - Human Relations Commission",
        "id": "chula_vista_human_relations_commission",
        "meeting_view_id": 24,
    },
    {
        "class_name": "ChulaVistaParksRecreationCommissionSpider",
        "name": "chula_vista_parks_recreation_commission",
        "agency": "City of Chula Vista - Parks and Recreation Commission",
        "id": "chula_vista_parks_recreation_commission",
        "meeting_view_id": 27,
    },
    {
        "class_name": "ChulaVistaPlanningCommissionSpider",
        "name": "chula_vista_planning_commission",
        "agency": "City of Chula Vista - Planning Commission",
        "id": "chula_vista_planning_commission",
        "meeting_view_id": 11,
    },
    {
        "class_name": "ChulaVistaPrivacyProtectionTechnologyAdvisoryCommissionSpider",
        "name": "chula_vista_privacy_protection_technology_advisory_commission",
        "agency": "City of Chula Vista - Privacy Protection and Technology Advisory Commission", # noqa
        "id": "chula_vista_privacy_protection_technology_advisory_commission",
        "meeting_view_id": 12,
    },
    {
        "class_name": "ChulaVistaSustainabilityCommissionSpider",
        "name": "chula_vista_sustainability_commission",
        "agency": "City of Chula Vista - Sustainability Commission",
        "id": "chula_vista_sustainability_commission",
        "meeting_view_id": 30,
    },
    {
        "class_name": "ChulaVistaTrafficSafetyCommissionSpider",
        "name": "chula_vista_traffic_safety_commission",
        "agency": "City of Chula Vista - Traffic Safety Commission",
        "id": "chula_vista_traffic_safety_commission",
        "meeting_view_id": 29,
    },
    {
        "class_name": "ChulaVistaVeteransAdvisoryCommissionSpider",
        "name": "chula_vista_veterans_advisory_commission",
        "agency": "City of Chula Vista - Veterans Advisory Commission",
        "id": "chula_vista_veterans_advisory_commission",
        "meeting_view_id": 31,
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
                (ChulaVistaMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
