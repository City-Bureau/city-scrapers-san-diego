from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_citychula import ChulaVistaBoardOfEthicsSpider

# Load a saved JSON response (example)
test_response = file_response(
    join(dirname(__file__), "files", "sandie_citychula.json"),
    url="https://pub-chulavista.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings?MeetingViewId=15",  # noqa
)

spider = ChulaVistaBoardOfEthicsSpider()  # ← Changed spider name


@pytest.fixture
def parsed_items():
    with freeze_time("2026-01-09"):
        return list(spider.parse_calendar(test_response))


def test_count(parsed_items):
    assert len(parsed_items) == 1


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "Board of Ethics Regular Meeting"


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == BOARD


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2025, 12, 17, 17, 15)


def test_end(parsed_items):
    # Add test for end time since you added it
    assert parsed_items[0]["end"] == datetime(2025, 12, 17, 18, 15)


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "City Hall, Bldg. A, Executive Conference Room #103",
        "address": "City Hall, Bldg. A, Executive Conference Room #103, 276 Fourth Avenue, Chula Vista, CA",  # noqa
    }


def test_links(parsed_items):
    links = parsed_items[0]["links"]

    # At least one document link should exist
    assert len(links) >= 1

    # Titles should come from MeetingDocumentLink.Title
    titles = [link["title"] for link in links]
    assert "Agenda Cover Page (PDF)" in titles
    assert "Agenda (PDF)" in titles
    assert "Agenda (HTML)" in titles

    # URLs should be fully qualified and valid
    for link in links:
        assert link["href"].startswith("http")


def test_source(parsed_items):
    source = parsed_items[0]["source"]
    assert source.startswith(
        "https://pub-chulavista.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings"  # noqa
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] in ("tentative", "passed", "cancelled")


@pytest.mark.parametrize("item", ["parsed_items"])
def test_all_day(item, parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False
