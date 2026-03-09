from datetime import datetime
from os.path import dirname, join
from unittest.mock import patch

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_citychula import ChulaVistaBoardOfEthicsSpider

test_response = file_response(
    join(dirname(__file__), "files", "sandie_citychula.json"),
    url="https://pub-chulavista.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings?MeetingViewId=15",  # noqa
)

# Load saved city calendar HTML
with open(
    join(dirname(__file__), "files", "sandie_citychula_calendar.html"),
    "r",
    encoding="utf-8",
) as f:
    calendar_html = f.read()

spider = ChulaVistaBoardOfEthicsSpider()


@pytest.fixture
def parsed_items():
    with freeze_time("2026-01-09"):
        return list(spider.parse_calendar(test_response))


@pytest.fixture
def parsed_items_with_upcoming():
    with freeze_time("2026-01-09"):
        with patch.object(spider, "_fetch_city_calendar", return_value=calendar_html):
            spider._calendar_meetings = []
            requests = list(spider.start_requests())  # triggers city calendar fetch
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
    assert parsed_items[0]["end"] == datetime(2025, 12, 17, 18, 15)


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "City Hall, Bldg. A, Executive Conference Room #103",
        "address": "276 Fourth Avenue, Chula Vista, CA",
    }


def test_links(parsed_items):
    links = parsed_items[0]["links"]
    assert len(links) == 6
    titles = {link["title"] for link in links}
    expected_titles = {
        "Agenda Cover Page (PDF)",
        "Agenda (PDF)",
        "Agenda (HTML)",
        "Post Agenda (PDF)",
        "Post Agenda (HTML)",
        "Board of Ethics Regular Meeting Agenda - Spanish",
    }
    assert titles == expected_titles
    for link in links:
        assert link["href"].startswith("http")


def test_source(parsed_items):
    assert parsed_items[0]["source"].startswith(
        "https://pub-chulavista.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings"  # noqa
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == "passed"


def test_all_day(parsed_items):
    for item in parsed_items:
        assert item["all_day"] is False


# --- upcoming meeting tests from city main calendar ---


def test_upcoming_title(parsed_items_with_upcoming):
    upcoming = [i for i in parsed_items_with_upcoming if i["status"] == "tentative"]
    assert any("Board of Ethics" in i["title"] for i in upcoming)


def test_upcoming_start_in_future(parsed_items_with_upcoming):
    upcoming = [i for i in parsed_items_with_upcoming if i["status"] == "tentative"]
    for item in upcoming:
        assert item["start"] >= datetime(2026, 1, 9)


def test_upcoming_links_empty(parsed_items_with_upcoming):
    upcoming = [i for i in parsed_items_with_upcoming if i["status"] == "tentative"]
    for item in upcoming:
        assert item["links"] == []
