"""
This file dynamically creates spider classes for the spider factory
mixin that agencies use.

Total 18 agencies
"""

from city_scrapers.mixins.sandie_citychula import ChulaVistaMixin

spider_configs = [
    {
        "class_name": "ChulaVistaBoardOfEthicsSpider",
        "name": "chula_vista_board_of_ethics",
        "agency": "City of Chula Vista - Board of Ethics",
        "meeting_view_id": 15,
        "time_notes": "Regular meetings are held on the third Wednesday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Board of Ethics"],
        "location": {
            "name": "City of Chula Vista - Civic Center Library - Community Room",
            "address": "365 F Street, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaBoardOfAppealsAdvisorsSpider",
        "name": "chula_vista_board_of_appeals_advisors",
        "agency": "City of Chula Vista - Board of Appeals & Advisors",
        "meeting_view_id": 14,
        "time_notes": "Regular meetings are held on the third Monday in July of each year. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Board of Appeals and Advisors"],
        "location": {
            "name": "City Hall, Public Services Building #A",
            "address": "276 Fourth Avenue, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaBoardOfLibraryTrusteesSpider",
        "name": "chula_vista_board_of_library_trustees",
        "agency": "City of Chula Vista - Board of Library Trustees",
        "meeting_view_id": 16,
        "time_notes": "Regular meetings are held on the third Wednesday of each month",
        "calendar_keywords": ["Board of Library Trustees"],
        "location": {
            "name": "Civic Center Library - Conference Room",
            "address": "365 F Street, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaCharterReviewCommissionSpider",
        "name": "chula_vista_charter_review_commission",
        "agency": "City of Chula Vista - Charter Review Commission",
        "meeting_view_id": 17,
        "time_notes": "The regular meetings are held on the second Wednesday in February, May, August, and November. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
    },
    {
        "class_name": "ChulaVistaCivilServiceCommissionSpider",
        "name": "chula_vista_civil_service_commission",
        "agency": "City of Chula Vista - Civil Service Commission",
        "meeting_view_id": 18,
        "time_notes": "The regular meetings are held on the first Thursday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Civil Service Commission"],
        "location": {
            "name": "City Hall, Bldg C, Conference Room B-129",
            "address": "276 Fourth Avenue Building C, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaCulturalArtsCommissionSpider",
        "name": "chula_vista_cultural_arts_commission",
        "agency": "City of Chula Vista - Cultural Arts Commission",
        "meeting_view_id": 20,
        "time_notes": "The regular meetings are held on the first Wednesday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Cultural Arts Commission"],
        "location": {
            "name": "Civic Center Library - Conference Room",
            "address": "365 F Street, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaHealthWellnessAgingCommissionSpider",
        "name": "chula_vista_health_wellness_aging_commission",
        "agency": "City of Chula Vista - Health Wellness and Aging Commission",
        "meeting_view_id": 22,
        "time_notes": "The regular meetings are held on the second Thursday in February, April, June, August, October, and December. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Health Wellness and Aging Commission"],
        "location": {
            "name": "Chula Vista City Hall, Executive Conf. Room 103",
            "address": "276 Fourth Avenue Building A, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaHousingHomelessnessAdvisoryCommissionSpider",
        "name": "chula_vista_housing_homelessness_advisory_commission",
        "agency": "City of Chula Vista - Housing and Homelessness Advisory Commission",
        "meeting_view_id": 23,
        "time_notes": "The regular meetings are held on the fourth Wednesday in January, April, July and October. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
    },
    {
        "class_name": "ChulaVistaHumanRelationsCommissionSpider",
        "name": "chula_vista_human_relations_commission",
        "agency": "City of Chula Vista - Human Relations Commission",
        "meeting_view_id": 24,
        "time_notes": "The regular meetings are held on the fourth Thursday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Human Relations Commission"],
        "location": {
            "name": "Council Chambers",
            "address": "276 Fourth Avenue, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaParksRecreationCommissionSpider",
        "name": "chula_vista_parks_recreation_commission",
        "agency": "City of Chula Vista - Parks and Recreation Commission",
        "meeting_view_id": 27,
        "time_notes": "The regular meetings are held on the third Thursday of every other month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Parks and Recreation Commission"],
        "location": {
            "name": "Norman Park Senior Center",
            "address": "270 F Street, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaPlanningCommissionSpider",
        "name": "chula_vista_planning_commission",
        "agency": "City of Chula Vista - Planning Commission",
        "meeting_view_id": 11,
        "time_notes": "The regular meetings are held on the second and Fourth Wednesday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Planning Commission"],
        "location": {
            "name": "Council Chambers",
            "address": "276 Fourth Avenue, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaPrivacyProtectionTechnologyAdvisoryCommissionSpider",
        "name": "chula_vista_privacy_protection_technology_advisory_commission",
        "agency": "City of Chula Vista - Privacy Protection and Technology Advisory Commission",  # noqa
        "meeting_view_id": 12,
        "time_notes": "The regular meetings are held on the fourth Monday in January, the Third Monday in April, July and October. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Privacy Protection and Technology"],
        "location": {
            "name": "Chula Vista City Hall, Executive Conf. Room 103",
            "address": "276 Fourth Avenue Building A, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaSustainabilityCommissionSpider",
        "name": "chula_vista_sustainability_commission",
        "agency": "City of Chula Vista - Sustainability Commission",
        "meeting_view_id": 30,
        "time_notes": "The regular meetings are held on the second Monday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Sustainability Commission"],
        "location": {
            "name": "City Hall Bldg. A, Executive Conference Room #103",
            "address": "276 Fourth Avenue, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaTrafficSafetyCommissionSpider",
        "name": "chula_vista_traffic_safety_commission",
        "agency": "City of Chula Vista - Traffic Safety Commission",
        "meeting_view_id": 29,
        "time_notes": "The regular meetings are held on the second Thursday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Traffic Safety Commission"],
        "location": {
            "name": "Council Chambers",
            "address": "276 Fourth Avenue Building A, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaVeteransAdvisoryCommissionSpider",
        "name": "chula_vista_veterans_advisory_commission",
        "agency": "City of Chula Vista - Veterans Advisory Commission",
        "meeting_view_id": 31,
        "time_notes": "The regular meetings are held on the third Wednesday of each month. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
    },
    {
        "class_name": "ChulaVistaMeasureACitizensOversightCommitteeSpider",
        "name": "chula_vista_measure_a_citizens_oversight_committee",
        "agency": "City of Chula Vista - Measure A Citizens' Oversight Committee",
        "meeting_view_id": 33,
        "time_notes": "The regular meetings are held on the second Thursday quarterly (January, April, July & October). Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Measure A Citizens Oversight Committee"],
        "location": {
            "name": "Chula Vista Police Department",
            "address": "315 Fourth Avenue, Chula Vista, CA 91910",
        },
    },
    {
        "class_name": "ChulaVistaMeasurePCitizensOversightCommitteeSpider",
        "name": "chula_vista_measure_p_citizens_oversight_committee",
        "agency": "City of Chula Vista - Measure P Citizens' Oversight Committee",
        "meeting_view_id": 85,
        "meeting_id_param": "MeetingtypeId",
        "time_notes": "The regular meetings are held on the fourth Thursday Quarterly in January, April, July, and October. Please refer to the meeting attachments for more accurate start and end times.",  # noqa
        "calendar_keywords": ["Measure P Citizens"],
        "location": {
            "name": "John Lippitt Public Works Center Lunchroom",
            "address": "1800 Maxwell Road, Chula Vista, CA 91911",
        },
    },
    {
        # Uses shared calendar meeting_view_id, filtered client-side
        "class_name": "ChulaVistaPoliceDepartmentCommunityAdvisoryCommitteeSpider",
        "name": "chula_vista_police_community_advisory_committee",
        "agency": "City of Chula Vista - Police Department Community Advisory Committee",  # noqa
        "meeting_view_id": 2,
        "time_notes": "Meetings may be cancelled and/or special meetings may be held. Please check agenda to confirm upcoming meeting details. The regular meetings are held on the first Thursday quarterly (January, April, July & October)",  # noqa
        "allowed_meeting_types": [
            "Police Department Community Advisory Committee - Regular Virtual",
            "Police Department Community Advisory Committee - Special Virtual",
            "Police Department Community Advisory Committee- Regular Meeting",
            "Police Department Community Advisory Committee Special Meeting",
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
                (ChulaVistaMixin,),
                attrs,
            )

            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
