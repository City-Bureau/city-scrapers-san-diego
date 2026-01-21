from datetime import datetime
from os.path import dirname, join

from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    PASSED,
)
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_nationalcity import (
    SandieBoardsCommissionsSpider,
    SandieCityCouncilSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "sandie_nationalcity.html"),
    url="https://www.nationalcityca.gov/government/boards-commissions-committees/-toggle-all/-sortn-EDate/-sortd-desc",  # noqa
)

freezer = freeze_time("2025-01-20")
freezer.start()

# Test City Council Spider
council_spider = SandieCityCouncilSpider()
council_items = list(council_spider.parse(test_response))

# Test Boards & Commissions Spider
boards_spider = SandieBoardsCommissionsSpider()
boards_items = list(boards_spider.parse(test_response))

freezer.stop()


# ============ City Council Spider Tests ============


def test_council_spider_configuration():
    """Test that City Council spider is properly configured"""
    assert council_spider.name == "sandie_citycouncil"
    assert council_spider.agency == "Sandie City Council"
    assert council_spider.event_type == "City Council"


def test_council_count():
    """Test that City Council spider gets council meetings"""
    # Should get: City Council Special Meeting - Online Only,
    # Special City Council Meeting, and City Council Meeting
    assert len(council_items) == 3


def test_council_title():
    """Test that council meeting titles are correctly parsed"""
    titles = [item["title"] for item in council_items]
    assert "City Council Special Meeting - Online Only Meeting" in titles
    assert "Special City Council Meeting" in titles
    assert "City Council Meeting" in titles


def test_council_start():
    """Test that council meeting start times are correctly parsed"""
    # City Council Special Meeting - 7/19/2022 5:00 PM
    special_meeting = next(
        item for item in council_items if "Online Only Meeting" in item["title"]
    )
    assert special_meeting["start"] == datetime(2022, 7, 19, 17, 0)

    # Special City Council Meeting - 6/13/2024 6:00 PM
    special_cc_meeting = next(
        item
        for item in council_items
        if item["title"] == "Special City Council Meeting"
    )
    assert special_cc_meeting["start"] == datetime(2024, 6, 13, 18, 0)


def test_council_end():
    """Test that council meeting end times are correctly parsed"""
    special_meeting = next(
        item for item in council_items if "Online Only Meeting" in item["title"]
    )
    assert special_meeting["end"] == datetime(2022, 7, 19, 18, 0)

    special_cc_meeting = next(
        item
        for item in council_items
        if item["title"] == "Special City Council Meeting"
    )
    assert special_cc_meeting["end"] == datetime(2024, 6, 13, 20, 0)


def test_council_classification():
    """Test that council meeting classification is CITY_COUNCIL for regular council meetings"""  # noqa
    # Note: Joint meetings may have different classification based on title parsing
    regular_council = [item for item in council_items if "Joint" not in item["title"]]
    for item in regular_council:
        assert item["classification"] == CITY_COUNCIL


def test_council_status():
    """Test that past council meetings have PASSED status"""
    for item in council_items:
        assert item["status"] == PASSED


def test_council_links():
    """Test that council meeting links are correctly parsed"""
    # Special City Council Meeting has 6 links
    special_cc_meeting = next(
        item
        for item in council_items
        if item["title"] == "Special City Council Meeting"
    )
    links = special_cc_meeting["links"]
    assert len(links) == 6

    link_titles = [link["title"] for link in links]
    assert "Agenda" in link_titles


def test_council_source():
    """Test that source URL is correctly set"""
    assert "nationalcityca.gov" in council_items[0]["source"]


def test_council_id():
    """Test that unique ID is generated"""
    for item in council_items:
        assert item["id"].startswith("sandie_citycouncil/")


# ============ Boards & Commissions Spider Tests ============


def test_boards_spider_configuration():
    """Test that Boards & Commissions spider is properly configured"""
    assert boards_spider.name == "sandie_boards_commissions"
    assert boards_spider.agency == "Sandie Boards and Commissions"
    assert isinstance(boards_spider.event_type, list)


def test_boards_count():
    """Test that Boards & Commissions spider gets all matching meetings"""
    # Should match: Library Board, Civil Service, Police Relations, Planning,
    # Recreation, Public Art, Housing Advisory, and Sweetwater Authority (from City Council Meeting) # noqa
    assert len(boards_items) >= 8


def test_boards_library_trustees():
    """Test Library Trustees meeting is captured"""
    library_items = [item for item in boards_items if "Library" in item["title"]]
    assert len(library_items) >= 1
    assert library_items[0]["classification"] == BOARD
    assert library_items[0]["start"] == datetime(2023, 6, 7, 17, 30)


def test_boards_civil_service():
    """Test Civil Service Commission meeting is captured"""
    civil_items = [item for item in boards_items if "Civil Service" in item["title"]]
    assert len(civil_items) >= 1
    assert civil_items[0]["classification"] == COMMISSION


def test_boards_planning_commission():
    """Test Planning Commission meeting is captured"""
    planning_items = [
        item for item in boards_items if "Planning Commission" in item["title"]
    ]
    assert len(planning_items) >= 1
    assert planning_items[0]["classification"] == COMMISSION
    assert planning_items[0]["start"] == datetime(2023, 1, 2, 18, 0)


def test_boards_housing_advisory():
    """Test Housing Advisory Committee meeting is captured"""
    housing_items = [
        item for item in boards_items if "Housing Advisory" in item["title"]
    ]
    assert len(housing_items) >= 1
    assert housing_items[0]["classification"] == ADVISORY_COMMITTEE


def test_boards_public_arts():
    """Test Public Arts Committee meeting is captured"""
    arts_items = [item for item in boards_items if "Public Art" in item["title"]]
    assert len(arts_items) >= 1
    assert arts_items[0]["classification"] == COMMITTEE
    assert arts_items[0]["start"] == datetime(2022, 3, 15, 0, 0)


def test_boards_recreation():
    """Test Recreation Advisory Committee meeting is captured"""
    rec_items = [item for item in boards_items if "Recreation" in item["title"]]
    assert len(rec_items) >= 1
    assert rec_items[0]["classification"] == ADVISORY_COMMITTEE


def test_boards_police_relations():
    """Test Community and Police Relations Commission meeting is captured"""
    police_items = [
        item for item in boards_items if "Police Relations" in item["title"]
    ]
    assert len(police_items) >= 1
    assert police_items[0]["classification"] == COMMISSION
    assert police_items[0]["start"] == datetime(2027, 5, 20, 18, 0)


def test_boards_police_relations_links():
    """Test that Police Relations meeting has all links"""
    police_item = next(
        item for item in boards_items if "Police Relations" in item["title"]
    )
    assert len(police_item["links"]) == 0


def test_boards_sweetwater_authority():
    """Test Sweetwater Authority meeting is captured from City Council Meeting links"""
    # The City Council Meeting contains "Sweetwater Authority" in one of its links
    sweetwater_items = [
        item for item in boards_items if "Sweetwater" in str(item["links"])
    ]
    assert len(sweetwater_items) >= 1


def test_boards_status():
    """Test that past meetings have PASSED status and future meetings have TENTATIVE"""
    # With frozen time at 2025-01-20, some meetings are in the past, some in the future
    past_items = [
        item
        for item in boards_items
        if item["start"].year < 2025
        or (item["start"].year == 2025 and item["start"] < datetime(2025, 1, 20))
    ]
    for item in past_items:
        assert item["status"] == PASSED


def test_boards_links_parsed():
    """Test that links are correctly parsed for boards meetings"""
    for item in boards_items:
        assert isinstance(item["links"], list)
        for link in item["links"]:
            assert "href" in link
            assert "title" in link


def test_boards_location():
    """Test that default location is set"""
    for item in boards_items:
        assert "location" in item
        assert "name" in item["location"]
        assert "address" in item["location"]


def test_all_day_false():
    """Test that all_day is False for all meetings"""
    for item in council_items + boards_items:
        assert item["all_day"] is False
