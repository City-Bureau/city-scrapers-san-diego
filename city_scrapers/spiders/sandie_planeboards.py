from datetime import time

from city_scrapers.mixins.sandie_planeboards import SandiePlanboardsMixin

"""
41 agencies
"""

spider_configs = [
    {
        "class_name": "SandieBarrioLoganSpider",
        "name": "sandie_barrio_logan",
        "agency": "Barrio Logan Community Planning Group",
        "group_param": "planning/community-plans/barrio-logan/planning-group",
    },
    {
        "class_name": "CarmelMountainRanchSpider",
        "name": "sandie_carmel_mountain_ranch",
        "agency": "Carmel Mountain Ranch Community Planning Group",
        "group_param": "planning/community-plans/carmel-mountain-ranch/planning-group",
    },
    {
        "class_name": "CarmelValleySpider",
        "name": "sandie_carmel_valley",
        "agency": "Carmel Valley Community Planning Group",
        "group_param": "planning/community-plans/carmel-valley/planning-group",
    },
    {
        "class_name": "ChollasValleySpider",
        "name": "sandie_chollas_valley",
        "agency": "Chollas Valley Community Planning Group (formerly Encanto)",
        "group_param": "planning/community-plans/encanto/planning-group",
    },
    {
        "class_name": "CityHeightsSpider",
        "name": "sandie_city_heights",
        "agency": "City Heights Community Planning Group",
        "group_param": "planning/community-plans/city-heights/planning-group",
    },
    {
        "class_name": "ClairemontMesaSpider",
        "name": "sandie_clairemont_mesa",
        "agency": "Clairemont Mesa Community Planning Group",
        "group_param": "planning/community-plans/clairemont-mesa/planning-group",
    },
    {
        "class_name": "CollegeAreaSpider",
        "name": "sandie_college_area",
        "agency": "College Area Community Planning Group",
        "group_param": "planning/community-plans/college-area/planning-group",
    },
    {
        "class_name": "DelMarMesaSpider",
        "name": "sandie_del_mar_mesa",
        "agency": "Del Mar Mesa Community Planning Group",
        "group_param": "planning/community-plans/del-mar-mesa/planning-group",
    },
    {
        "class_name": "DowntownSpider",
        "name": "sandie_downtown",
        "agency": "Downtown Community Planning Council",
        "group_param": "planning/community-plans/downtown/planning-group",
    },
    {
        "class_name": "EasternAreaCommunitySpider",
        "name": "sandie_eastern_area_community",
        "agency": "Eastern Area Community Planning Group",
        "group_param": "planning/community-plans/eastern-area/planning-group",
    },
    {
        "class_name": "GreaterGoldenHillSpider",
        "name": "sandie_greater_golden_hill",
        "agency": "Greater Golden Hill Community Planning Group",
        "group_param": "planning/community-plans/greater-golden-hill/planning-group",
    },
    {
        "class_name": "KearnyMesaSpider",
        "name": "sandie_kearny_mesa",
        "agency": "Kearny Mesa Community Planning Group",
        "group_param": "planning/community-plans/kearny-mesa/planning-group",
    },
    {
        "class_name": "KensingtonTalmadgeSpider",
        "name": "sandie_kensington_talmadge",
        "agency": "Kensington-Talmadge Community Planning Group",
        "group_param": "planning/community-plans/kensington-talmadge/planning-group",
    },
    {
        "class_name": "LaJollaSpider",
        "name": "sandie_la_jolla",
        "agency": "La Jolla Community Planning Group",
        "group_param": "planning/community-plans/la-jolla/planning-group",
    },
    {
        "class_name": "LindaVistaSpider",
        "name": "sandie_linda_vista",
        "agency": "Linda Vista Community Planning Group",
        "group_param": "planning/community-plans/linda-vista/planning-group",
    },
    {
        "class_name": "MidwayPacificHighwaySpider",
        "name": "sandie_midway_pacific_highway",
        "agency": "Midway-Pacific Highway Community Planning Group",
        "group_param": "planning/community-plans/midway-pacific-highway/planning-group",
    },
    {
        "class_name": "MiraMesaSpider",
        "name": "sandie_mira_mesa",
        "agency": "Mira Mesa Community Planning Group",
        "group_param": "planning/community-plans/mira-mesa/planning-group",
    },
    {
        "class_name": "MissionBeachSpider",
        "name": "sandie_mission_beach",
        "agency": "Mission Beach Community Planning Group",
        "group_param": "planning/community-plans/mission-beach/planning-group",
    },
    {
        "class_name": "MissionValleySpider",
        "name": "sandie_mission_valley",
        "agency": "Mission Valley Community Planning Group",
        "group_param": "planning/community-plans/mission-valley/planning-group",
    },
    {
        "class_name": "NavajoSpider",
        "name": "sandie_navajo",
        "agency": "Navajo Community Planning Group",
        "group_param": "planning/community-plans/navajo/planning-group",
        "default_time": time(18, 30),
    },
    {
        "class_name": "NormalHeightsSpider",
        "name": "sandie_normal_heights",
        "agency": "Normal Heights Community Planning Group",
        "group_param": "planning/community-plans/normal-heights/planning-group",
    },
    {
        "class_name": "NorthParkSpider",
        "name": "sandie_north_park",
        "agency": "North Park Community Planning Group",
        "group_param": "planning/community-plans/north-park/planning-group",
    },
    {
        "class_name": "OceanBeachSpider",
        "name": "sandie_ocean_beach",
        "agency": "Ocean Beach Community Planning Group",
        "group_param": "planning/community-plans/ocean-beach/planning-group",
    },
    {
        "class_name": "OldTownSpider",
        "name": "sandie_old_town",
        "agency": "Old Town San Diego Community Planning Group",
        "group_param": "planning/community-plans/old-town/planning-group",
    },
    {
        "class_name": "OtayMesaSpider",
        "name": "sandie_otay_mesa",
        "agency": "Otay Mesa Community Planning Group",
        "group_param": "planning/community-plans/otay-mesa/planning-group",
    },
    {
        "class_name": "OtayMesaNestorSpider",
        "name": "sandie_otay_mesa_nestor",
        "agency": "Otay Mesa-Nestor Community Planning Group",
        "group_param": "planning/community-plans/otay-mesa-nestor/planning-group",
        "default_location_mesa_nestor": {
            "name": "St. Charles Catholic School",
            "address": "929 18th Street, San Diego, CA 92154",
        },
    },
    {
        "class_name": "PacificBeachSpider",
        "name": "sandie_pacific_beach",
        "agency": "Pacific Beach Planning Group",
        "group_param": "staging/pacific-beach-planning-group",
    },
    {
        "class_name": "RanchoBernardoSpider",
        "name": "sandie_rancho_bernardo",
        "agency": "Rancho Bernardo Community Planning Group",
        "group_param": "planning/community-plans/rancho-bernardo/planning-group",
    },
    {
        "class_name": "RanchoPenasquitosSpider",
        "name": "sandie_rancho_penasquitos",
        "agency": "Rancho Peñasquitos Community Planning Group",
        "group_param": "planning/community-plans/rancho-penasquitos/planning-group",
    },
    {
        "class_name": "SandieSanPasqualValleySpider",
        "name": "sandie_san_pasqual_valley",
        "agency": "San Pasqual Valley Community Planning Group",
        "group_param": "planning/community-plans/san-pasqual-valley/planning-group",
    },
    {
        "class_name": "SandieSanYsidroSpider",
        "name": "sandie_san_ysidro",
        "agency": "San Ysidro Community Planning Group",
        "group_param": "planning/community-plans/san-ysidro/planning-group",
    },
    {
        "class_name": "ScrippsRanchSpider",
        "name": "sandie_scripps_ranch",
        "agency": "Scripps Ranch Community Planning Group",
        "group_param": "planning/community-plans/scripps-miramar-ranch/planning-group",
    },
    {
        "class_name": "SerraMesaSpider",
        "name": "sandie_serra_mesa",
        "agency": "Serra Mesa Community Planning Group",
        "group_param": "planning/community-plans/serra-mesa/planning-group",
    },
    {
        "class_name": "SkylineParadiseHillsSpider",
        "name": "sandie_skyline_paradise_hills",
        "agency": "Skyline/Paradise Hills Community Planning Group",
        "group_param": "planning/community-plans/skyline-paradise-hills/planning-group",
    },
    {
        "class_name": "SoutheasternSanDiegoSpider",
        "name": "sandie_southeastern_san_diego",
        "agency": "Southeastern San Diego Community Planning Group",
        "group_param": "planning/community-plans/southeastern-san-diego/planning-group",
    },
    {
        "class_name": "TierrasantaSpider",
        "name": "sandie_tierrasanta",
        "agency": "Tierrasanta Community Planning Group",
        "group_param": "planning/community-plans/tierrasanta/planning-group",
    },
    {
        "class_name": "TorreyHillsSpider",
        "name": "sandie_torrey_hills",
        "agency": "Torrey Hills Community Planning Group",
        "group_param": "planning/community-plans/torrey-hills/planning-group",
    },
    {
        "class_name": "SandieTorreyPinesSpider",
        "name": "sandie_torrey_pines",
        "agency": "Torrey Pines Community Planning Group",
        "group_param": "planning/community-plans/torrey-pines/planning-group",
    },
    {
        "class_name": "UniversityCommunitySpider",
        "name": "sandie_university_community",
        "agency": "University Community Planning Group",
        "group_param": "planning/community-plans/university/planning-group",
    },
    {
        "class_name": "SandieUptownSpider",
        "name": "sandie_uptown",
        "agency": "Uptown Community Planning Group",
        "group_param": "planning/community-plans/uptown/planning-group",
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
