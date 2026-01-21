"""
This file dynamically creates spider classes for the spider factory
mixin that agencies use.
"""

from city_scrapers.mixins.sandie_citychula import ChulaVistaMixin

spider_configs = [
    {
        "class_name": "ChulaVistaBoardOfEthicsSpider",
        "name": "chula_vista_board_of_ethics",
        "agency": "City of Chula Vista - Board of Ethics",
        "id": "chula_vista_board_of_ethics",
        "meeting_view_id": 15,
        "time_notes": "Regular meetings are held on the third Wednesday of each month",
    },
    {
        "class_name": "ChulaVistaBoardOfAppealsAdvisorsSpider",
        "name": "chula_vista_board_of_appeals_advisors",
        "agency": "City of Chula Vista - Board of Appeals & Advisors",
        "id": "chula_vista_board_of_appeals_advisors",
        "meeting_view_id": 14,
        "time_notes": "Regular meetings are held on the third Monday in July of each year",  # noqa
    },
    {
        "class_name": "ChulaVistaBoardOfLibraryTrusteesSpider",
        "name": "chula_vista_board_of_library_trustees",
        "agency": "City of Chula Vista - Board of Library Trustees",
        "id": "chula_vista_board_of_library_trustees",
        "meeting_view_id": 16,
        "time_notes": "Regular meetings are held on the third Wednesday of each month",
    },
    {
        "class_name": "ChulaVistaCharterReviewCommissionSpider",
        "name": "chula_vista_charter_review_commission",
        "agency": "City of Chula Vista - Charter Review Commission",
        "id": "chula_vista_charter_review_commission",
        "meeting_view_id": 17,
        "time_notes": "The regular meetings are held on the second Wednesday in February, May, August, and November",  # noqa
    },
    {
        "class_name": "ChulaVistaCivilServiceCommissionSpider",
        "name": "chula_vista_civil_service_commission",
        "agency": "City of Chula Vista - Civil Service Commission",
        "id": "chula_vista_civil_service_commission",
        "meeting_view_id": 18,
        "time_notes": "The regular meetings are held on the first Thursday of each month",  # noqa
    },
    {
        "class_name": "ChulaVistaCulturalArtsCommissionSpider",
        "name": "chula_vista_cultural_arts_commission",
        "agency": "City of Chula Vista - Cultural Arts Commission",
        "id": "chula_vista_cultural_arts_commission",
        "meeting_view_id": 20,
        "time_notes": "The regular meetings are held on the first Wednesday of each month",  # noqa
    },
    {
        "class_name": "ChulaVistaHealthWellnessAgingCommissionSpider",
        "name": "chula_vista_health_wellness_aging_commission",
        "agency": "City of Chula Vista - Health Wellness and Aging Commission",
        "id": "chula_vista_health_wellness_aging_commission",
        "meeting_view_id": 22,
        "time_notes": "The regular meetings are held on the second Thursday in February, April, June, August, October, and December",  # noqa
    },
    {
        "class_name": "ChulaVistaHousingHomelessnessAdvisoryCommissionSpider",
        "name": "chula_vista_housing_homelessness_advisory_commission",
        "agency": "City of Chula Vista - Housing and Homelessness Advisory Commission",
        "id": "chula_vista_housing_homelessness_advisory_commission",
        "meeting_view_id": 23,
        "time_notes": "The regular meetings are held on the fourth Wednesday in January, April, July and October",  # noqa
    },
    {
        "class_name": "ChulaVistaHumanRelationsCommissionSpider",
        "name": "chula_vista_human_relations_commission",
        "agency": "City of Chula Vista - Human Relations Commission",
        "id": "chula_vista_human_relations_commission",
        "meeting_view_id": 24,
        "time_notes": "The regular meetings are held on the fourth Thursday of each mont", # noqa
    },
    {
        "class_name": "ChulaVistaParksRecreationCommissionSpider",
        "name": "chula_vista_parks_recreation_commission",
        "agency": "City of Chula Vista - Parks and Recreation Commission",
        "id": "chula_vista_parks_recreation_commission",
        "meeting_view_id": 27,
        "time_notes": "The regular meetings are held on the third Thursday of every other month",  # noqa
    },
    {
        "class_name": "ChulaVistaPlanningCommissionSpider",
        "name": "chula_vista_planning_commission",
        "agency": "City of Chula Vista - Planning Commission",
        "id": "chula_vista_planning_commission",
        "meeting_view_id": 11,
        "time_notes": "The regular meetings are held on the second and Fourth Wednesday of each month",  # noqa
    },
    {
        "class_name": "ChulaVistaPrivacyProtectionTechnologyAdvisoryCommissionSpider",
        "name": "chula_vista_privacy_protection_technology_advisory_commission",
        "agency": "City of Chula Vista - Privacy Protection and Technology Advisory Commission",  # noqa
        "id": "chula_vista_privacy_protection_technology_advisory_commission",
        "meeting_view_id": 12,
        "time_notes": "The regular meetings are held on the fourth Monday in January, the Third Monday in April, July and October",  # noqa
    },
    {
        "class_name": "ChulaVistaSustainabilityCommissionSpider",
        "name": "chula_vista_sustainability_commission",
        "agency": "City of Chula Vista - Sustainability Commission",
        "id": "chula_vista_sustainability_commission",
        "meeting_view_id": 30,
        "time_notes": "The regular meetings are held on the second Monday of each month",  # noqa
    },
    {
        "class_name": "ChulaVistaTrafficSafetyCommissionSpider",
        "name": "chula_vista_traffic_safety_commission",
        "agency": "City of Chula Vista - Traffic Safety Commission",
        "id": "chula_vista_traffic_safety_commission",
        "meeting_view_id": 29,
        "time_notes": "The regular meetings are held on the second Thursday of each month",  # noqa
    },
    {
        "class_name": "ChulaVistaVeteransAdvisoryCommissionSpider",
        "name": "chula_vista_veterans_advisory_commission",
        "agency": "City of Chula Vista - Veterans Advisory Commission",
        "id": "chula_vista_veterans_advisory_commission",
        "meeting_view_id": 31,
        "time_notes": "The regular meetings are held on the third Wednesday of each month",  # noqa
    },
    {
        "class_name": "ChulaVistaMeasureACitizensOversightCommitteeSpider",
        "name": "chula_vista_measure_a_citizens_oversight_committee",
        "agency": "City of Chula Vista - Measure A Citizens' Oversight Committee",
        "id": "chula_vista_measure_a_citizens_oversight_committee",
        "meeting_view_id": 33,
        "time_notes": "The regular meetings are held on the second Thursday quarterly (January, April, July & October)",  # noqa
    },
    {
        "class_name": "ChulaVistaMeasurePCitizensOversightCommitteeSpider",
        "name": "chula_vista_measure_p_citizens_oversight_committee",
        "agency": "City of Chula Vista - Measure P Citizens' Oversight Committee",
        "id": "chula_vista_measure_p_citizens_oversight_committee",
        "meeting_view_id": 85,
        "time_notes": "The regular meetings are held on the fourth Thursday Quarterly in January, April, July, and October",  # noqa
    },
    {
        "class_name": "ChulaVistaPoliceCommunityAdvisoryCommitteeSpider",
        "name": "chula_vista_police_community_advisory_committee",
        "agency": "City of Chula Vista - Police Department’s Community Advisory Committee",  # noqa 
        "id": "chula_vista_police_community_advisory_committee",
        "meeting_view_id": 33,
        "time_notes": "Meetings may be cancelled and/or special meetings may be held. Please check agenda to confirm upcoming meeting details. The regular meetings are held on the first Thursday Quarterly (January, April, July & October)",  # noqa
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
