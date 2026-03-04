from datetime import time

from city_scrapers.mixins.sandie_planeboards import SandiePlanboardsMixin

"""
40 agencies
"""

spider_configs = [
    {
        "class_name": "SandieBarrioLoganSpider",
        "name": "sandie_barrio_logan",
        "agency": "Barrio Logan Community Planning Group",
        "group_param": "planning/community-plans/barrio-logan/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Chicano Park Museum and Cultural Center",
            "address": "1960 National Avenue, San Diego, CA 92113",
        },
    },
    {
        "class_name": "CarmelMountainRanchSpider",
        "name": "sandie_carmel_mountain_ranch",
        "agency": "Carmel Mountain Ranch Community Planning Group",
        "group_param": "planning/community-plans/carmel-mountain-ranch/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Carmel Mountain Ranch Recreation Center",
            "address": "10152 Rancho Carmel Dr, San Diego, CA 92128",
        },
    },
    {
        "class_name": "CarmelValleySpider",
        "name": "sandie_carmel_valley",
        "agency": "Carmel Valley Community Planning Group",
        "group_param": "planning/community-plans/carmel-valley/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {
            "name": "Carmel Valley Library",
            "address": "3919 Townsgate Dr, San Diego, CA 92130",
        },
    },
    {
        "class_name": "ChollasValleySpider",
        "name": "sandie_chollas_valley",
        "agency": "Chollas Valley Community Planning Group (formerly Encanto)",
        "group_param": "planning/community-plans/encanto/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "KIPP Adelante Preparatory Academy",
            "address": "426 Euclid Ave, San Diego, CA 92114",
        },
    },
    {
        "class_name": "CityHeightsSpider",
        "name": "sandie_city_heights",
        "agency": "City Heights Community Planning Group",
        "group_param": "planning/community-plans/city-heights/planning-group",
        "meeting_time": time(18, 15),
        "meeting_location": {
            "name": "City Heights/Weingart Branch Library",
            "address": "3795 Fairmount Ave, San Diego, CA 92105",
        },
    },
    {
        "class_name": "ClairemontMesaSpider",
        "name": "sandie_clairemont_mesa",
        "agency": "Clairemont Mesa Community Planning Group",
        "group_param": "planning/community-plans/clairemont-mesa/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Cathy Hopper Clairemont Friendship Center",
            "address": "4425 Bannock Ave, San Diego, CA 92117",
        },
    },
    {
        "class_name": "CollegeAreaSpider",
        "name": "sandie_college_area",
        "agency": "College Area Community Planning Group",
        "group_param": "planning/community-plans/college-area/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "College-Rolando Library (Community Room)",
            "address": "6600 Montezuma Rd, San Diego, CA 92115",
        },
    },
    {
        "class_name": "DelMarMesaSpider",
        "name": "sandie_del_mar_mesa",
        "agency": "Del Mar Mesa Community Planning Group",
        "group_param": "planning/community-plans/del-mar-mesa/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Ocean Air Recreation Center",
            "address": "4770 Fairport Way, San Diego, CA 92130",
        },
    },
    {
        "class_name": "DowntownSpider",
        "name": "sandie_downtown",
        "agency": "Downtown Community Planning Council",
        "group_param": "planning/community-plans/downtown/planning-group",
        "meeting_time": time(17, 30),
        "meeting_location": {
            "name": "City Administration Building",
            "address": "202 C Street, 12th Floor, San Diego, CA 92101",
        },
    },
    {
        "class_name": "EasternAreaCommunitySpider",
        "name": "sandie_eastern_area_community",
        "agency": "Eastern Area Community Planning Group",
        "group_param": "planning/community-plans/eastern-area/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {
            "name": "Teen Challenge International",
            "address": "5450 Lea Street, San Diego, CA 92105",
        },
    },
    {
        "class_name": "GreaterGoldenHillSpider",
        "name": "sandie_greater_golden_hill",
        "agency": "Greater Golden Hill Community Planning Group",
        "group_param": "planning/community-plans/greater-golden-hill/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Community Meeting Room",
            "address": "2646 Russ Blvd, San Diego, CA 92102",
        },
    },
    {
        "class_name": "KearnyMesaSpider",
        "name": "sandie_kearny_mesa",
        "agency": "Kearny Mesa Community Planning Group",
        "group_param": "planning/community-plans/kearny-mesa/planning-group",
        "meeting_time": time(11, 30),
        "meeting_location": {
            "name": "Virtual Meetings",
            "address": "",
        },
    },
    {
        "class_name": "KensingtonTalmadgeSpider",
        "name": "sandie_kensington_talmadge",
        "agency": "Kensington-Talmadge Community Planning Group",
        "group_param": "planning/community-plans/kensington-talmadge/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Kensington Community Church",
            "address": "4773 Marlborough Drive, San Diego, CA 92116",
        },
    },
    {
        "class_name": "LaJollaSpider",
        "name": "sandie_la_jolla",
        "agency": "La Jolla Community Planning Group",
        "group_param": "planning/community-plans/la-jolla/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "La Jolla Recreation Center",
            "address": "615 Prospect Street, La Jolla, CA 92037",
        },
    },
    {
        "class_name": "LindaVistaSpider",
        "name": "sandie_linda_vista",
        "agency": "Linda Vista Community Planning Group",
        "group_param": "planning/community-plans/linda-vista/planning-group",
        "meeting_time": time(18, 15),
        "meeting_location": {
            "name": "American Legion Post 731",
            "address": "7245 Linda Vista Road, San Diego, CA 92111",
        },
    },
    {
        "class_name": "MidwayPacificHighwaySpider",
        "name": "sandie_midway_pacific_highway",
        "agency": "Midway-Pacific Highway Community Planning Group",
        "group_param": "planning/community-plans/midway-pacific-highway/planning-group",
        "meeting_time": time(15, 0),
        "meeting_location": {
            "name": "Goodwill Education Center, Bldg B",
            "address": "2911 Sports Arena Blvd, Suite A, San Diego, CA 92110",
        },
    },
    {
        "class_name": "MiraMesaSpider",
        "name": "sandie_mira_mesa",
        "agency": "Mira Mesa Community Planning Group",
        "group_param": "planning/community-plans/mira-mesa/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {
            "name": "Mira Mesa Branch Library",
            "address": "8405 New Salem St, San Diego, CA 92126",
        },
    },
    {
        "class_name": "MissionBeachSpider",
        "name": "sandie_mission_beach",
        "agency": "Mission Beach Community Planning Group",
        "group_param": "planning/community-plans/mission-beach/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Belmont Park Meeting Room",
            "address": "3146 Mission Blvd, 2nd Floor, San Diego, CA 92109",
        },
    },
    {
        "class_name": "MissionValleySpider",
        "name": "sandie_mission_valley",
        "agency": "Mission Valley Community Planning Group",
        "group_param": "planning/community-plans/mission-valley/planning-group",
        "meeting_time": time(12, 0),
        "meeting_location": {
            "name": "Mission Valley Branch Library",
            "address": "2123 Fenton Pkwy, San Diego, CA 92108",
        },
    },
    {
        "class_name": "NavajoSpider",
        "name": "sandie_navajo",
        "agency": "Navajo Community Planning Group",
        "group_param": "planning/community-plans/navajo/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "",
            "address": "4772 Alvarado Canyon Rd, San Diego, CA 92120",
        },
    },
    {
        "class_name": "NormalHeightsSpider",
        "name": "sandie_normal_heights",
        "agency": "Normal Heights Community Planning Group",
        "group_param": "planning/community-plans/normal-heights/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Normal Heights Community Center",
            "address": "4649 Hawley Blvd, San Diego, CA 92116",
        },
    },
    {
        "class_name": "NorthParkSpider",
        "name": "sandie_north_park",
        "agency": "North Park Community Planning Group",
        "group_param": "planning/community-plans/north-park/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Christian Fellowship Church",
            "address": "2901 North Park Way, 2nd Floor, San Diego, CA 92104",
        },
    },
    {
        "class_name": "OceanBeachSpider",
        "name": "sandie_ocean_beach",
        "agency": "Ocean Beach Community Planning Group",
        "group_param": "planning/community-plans/ocean-beach/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Ocean Beach Recreation Center",
            "address": "4726 Santa Monica Avenue, San Diego, CA 92107",
        },
    },
    {
        "class_name": "OldTownSpider",
        "name": "sandie_old_town",
        "agency": "Old Town San Diego Community Planning Group",
        "group_param": "planning/community-plans/old-town/planning-group",
        "meeting_time": time(15, 0),
        "meeting_location": {
            "name": "Whaley House Courtroom",
            "address": "2482 San Diego Ave, San Diego, CA 92110",
        },
    },
    {
        "class_name": "OtayMesaSpider",
        "name": "sandie_otay_mesa",
        "agency": "Otay Mesa Community Planning Group",
        "group_param": "planning/community-plans/otay-mesa/planning-group",
        "meeting_time": time(15, 0),
        "meeting_location": {
            "name": "Virtual Meetings",
            "address": "",
        },
    },
    {
        "class_name": "OtayMesaNestorSpider",
        "name": "sandie_otay_mesa_nestor",
        "agency": "Otay Mesa-Nestor Community Planning Group",
        "group_param": "planning/community-plans/otay-mesa-nestor/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "St. Charles Catholic School",
            "address": "929 18th Street, San Diego, CA 92154",
        },
    },
    {
        "class_name": "PacificBeachSpider",
        "name": "sandie_pacific_beach",
        "agency": "Pacific Beach Planning Group",
        "group_param": "staging/pacific-beach-planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Earl Birdie Taylor Library",
            "address": "4275 Cass Street, San Diego, CA 92109",
        },
    },
    {
        "class_name": "RanchoBernardoSpider",
        "name": "sandie_rancho_bernardo",
        "agency": "Rancho Bernardo Community Planning Group",
        "group_param": "planning/community-plans/rancho-bernardo/planning-group",
        "meeting_time": time(18, 30),
        "meeting_location": {
            "name": "Seven Oaks Community Center",
            "address": "16789 Bernardo Oaks Dr, San Diego, CA 92128",
        },
    },
    {
        "class_name": "RanchoPenasquitosSpider",
        "name": "sandie_rancho_penasquitos",
        "agency": "Rancho Peñasquitos Community Planning Group",
        "group_param": "planning/community-plans/rancho-penasquitos/planning-group",
        "meeting_time": time(19, 30),
        "meeting_location": {
            "name": "Rancho Peñasquitos and Black Mountain Ranch: Rancho Family YMCA",
            "address": "9440 Fairgrove Ln, San Diego, CA 92129",
        },
    },
    {
        "class_name": "SandieSanPasqualValleySpider",
        "name": "sandie_san_pasqual_valley",
        "agency": "San Pasqual Valley Community Planning Group",
        "group_param": "planning/community-plans/san-pasqual-valley/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {
            "name": "San Diego Safari Park (Conference Room)",
            "address": "15500 San Pasqual Valley Rd, San Diego, CA 92027",
        },
    },
    {
        "class_name": "SandieSanYsidroSpider",
        "name": "sandie_san_ysidro",
        "agency": "San Ysidro Community Planning Group",
        "group_param": "planning/community-plans/san-ysidro/planning-group",
        "meeting_time": time(17, 30),
        "meeting_location": {
            "name": "San Ysidro School District Education Center, Board Room",
            "address": "4350 Otay Mesa Road, San Diego, CA 92154",
        },
    },
    {
        "class_name": "ScrippsRanchSpider",
        "name": "sandie_scripps_ranch",
        "agency": "Scripps Ranch Community Planning Group",
        "group_param": "planning/community-plans/scripps-miramar-ranch/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {
            "name": "SRCA Community Center",
            "address": "11885 Cypress Canyon Rd, San Diego, CA 92131",
        },
    },
    {
        "class_name": "SerraMesaSpider",
        "name": "sandie_serra_mesa",
        "agency": "Serra Mesa Community Planning Group",
        "group_param": "planning/community-plans/serra-mesa/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {
            "name": "Serra Mesa-Kearny Mesa Library",
            "address": "9005 Aero Drive, San Diego, CA 92123",
        },
    },
    {
        "class_name": "SkylineParadiseHillsSpider",
        "name": "sandie_skyline_paradise_hills",
        "agency": "Skyline/Paradise Hills Community Planning Group",
        "group_param": "planning/community-plans/skyline-paradise-hills/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Skyline Hills Public Library",
            "address": "7900 Paradise Valley Rd, San Diego, CA 92114",
        },
    },
    {
        "class_name": "SoutheasternSanDiegoSpider",
        "name": "sandie_southeastern_san_diego",
        "agency": "Southeastern San Diego Community Planning Group",
        "group_param": "planning/community-plans/southeastern-san-diego/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Mountain View Community Center",
            "address": "641 South Boundary Street, San Diego, CA 92113",
        },
    },
    {
        "class_name": "TierrasantaSpider",
        "name": "sandie_tierrasanta",
        "agency": "Tierrasanta Community Planning Group",
        "group_param": "planning/community-plans/tierrasanta/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Tierrasanta Recreation Center",
            "address": "11220 Clairemont Mesa Blvd, San Diego, CA 92124",
        },
    },
    {
        "class_name": "TorreyHillsSpider",
        "name": "sandie_torrey_hills",
        "agency": "Torrey Hills Community Planning Group",
        "group_param": "planning/community-plans/torrey-hills/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {"name": "Virtual Meetings", "address": ""},
    },
    {
        "class_name": "SandieTorreyPinesSpider",
        "name": "sandie_torrey_pines",
        "agency": "Torrey Pines Community Planning Group",
        "group_param": "planning/community-plans/torrey-pines/planning-group",
        "meeting_time": time(19, 0),
        "meeting_location": {"name": "Virtual Meetings", "address": ""},
    },
    {
        "class_name": "UniversityCommunitySpider",
        "name": "sandie_university_community",
        "agency": "University Community Planning Group",
        "group_param": "planning/community-plans/university/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {
            "name": "Terra Nova Room",
            "address": "9880 Campus Point Dr, San Diego, CA 92121",
        },
    },
    {
        "class_name": "SandieUptownSpider",
        "name": "sandie_uptown",
        "agency": "Uptown Community Planning Group",
        "group_param": "planning/community-plans/uptown/planning-group",
        "meeting_time": time(18, 0),
        "meeting_location": {"name": "", "address": ""},
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
                (SandiePlanboardsMixin,),
                attrs,
            )

            # Register the class in the global namespace using its class_name
            globals()[class_name] = spider_class


# Create all spider classes at module load
create_spiders()
