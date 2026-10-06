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
        with patch.object(spider, "_fetch_city_calendar", return_value=None):
            spider._calendar_meetings = []
            spider._calendar_event_urls = {}
            spider._fetched_calendar_months = set()
            return list(spider.parse_calendar(test_response))


@pytest.fixture
def parsed_items_with_upcoming():
    with freeze_time("2026-01-09"):
        with patch.object(spider, "_fetch_city_calendar", return_value=calendar_html):
            spider._calendar_meetings = []
            list(spider.start_requests())  # triggers city calendar fetch
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
    assert parsed_items[0]["source"] == (
        "https://pub-chulavista.escribemeetings.com/"
        f"?MeetingviewId={spider.meeting_view_id}"
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


def test_upcoming_source(parsed_items_with_upcoming):
    upcoming = [i for i in parsed_items_with_upcoming if i["status"] == "tentative"]
    assert upcoming
    for item in upcoming:
        assert item["source"].startswith(
            "https://www.chulavistaca.gov/Home/Components/Calendar/Event/"
        )


# --- source matching between eScribe meetings and city calendar events ---

ESCRIBE_URL = "https://pub-chulavista.escribemeetings.com/?MeetingviewId=15"
EVENT_URL = "https://www.chulavistaca.gov/Home/Components/Calendar/Event/1/2854"


def _source_for(titles, events):
    day = datetime(2026, 2, 25).date()
    spider._calendar_event_urls = {day: events}
    meetings = [{"title": t} for t in titles]
    spider._parse_sources(day, meetings)
    return [m["source"] for m in meetings]


def test_source_only_matching_meeting_gets_calendar_event():
    sources = _source_for(
        [
            "Board of Ethics Interview Panel",
            "Board of Ethics Subcommittee Interview Panel",
        ],
        [("Board of Ethics Subcommittee Interview Panel", EVENT_URL)],
    )
    assert sources == [ESCRIBE_URL, EVENT_URL]


def test_source_single_meeting_and_event_paired_despite_title():
    sources = _source_for(
        ["Board of Ethics Regular Meeting"],
        [("CANCELLED Board of Ethics Regular Meeting", EVENT_URL)],
    )
    assert sources == [EVENT_URL]


def test_source_no_calendar_event_uses_escribe():
    assert _source_for(["Board of Ethics Regular Meeting"], []) == [ESCRIBE_URL]
