from datetime import datetime
from os.path import dirname, join
from unittest.mock import patch

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED
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
        f"?MeetingviewId={spider.meeting_view_id}&Year=2025"
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

ESCRIBE_URL = "https://pub-chulavista.escribemeetings.com/?MeetingviewId=15&Year=2026"
EVENT_URL = "https://www.chulavistaca.gov/Home/Components/Calendar/Event/1/2854"


def _source_for(titles, events):
    day = datetime(2026, 2, 25).date()
    spider._calendar_event_urls = {day: events}
    meetings = [{"title": t, "start": datetime(2026, 2, 25, 17)} for t in titles]
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


# --- city calendar meetings missing from eScribe ---


def test_city_calendar_fetches_escribe_period():
    with freeze_time("2026-01-09"):
        with patch.object(spider, "_fetch_city_calendar", return_value=None):
            list(spider.start_requests())
    months = spider._fetched_calendar_months
    assert min(months) == (2023, 1)
    assert max(months) == (2027, 1)
    assert len(months) == 49


def _calendar_meeting(title, event_url):
    meeting = {
        "title": title,
        "start": datetime(2025, 12, 17, 17, 15),
        "links": [],
        "source": event_url,
    }
    meeting["id"] = event_url
    return meeting


def test_calendar_meeting_not_in_escribe_is_kept():
    day = datetime(2025, 12, 17).date()
    other_url = "https://www.chulavistaca.gov/Home/Components/Calendar/Event/1/9999"
    events = [
        ("Board of Ethics Regular Meeting", EVENT_URL + "?curm=12&cury=2025"),
        ("Board of Ethics Subcommittee", other_url),
    ]
    with freeze_time("2026-01-09"):
        spider._calendar_event_urls = {day: events}
        spider._calendar_meetings = [
            _calendar_meeting(title, url) for title, url in events
        ]
        items = list(spider.parse_calendar(test_response))

    escribe_item, calendar_item = items
    assert escribe_item["source"] == EVENT_URL + "?curm=12&cury=2025"
    assert escribe_item["links"]
    assert calendar_item["title"] == "Board of Ethics Subcommittee"
    assert calendar_item["source"] == other_url
    assert calendar_item["links"] == []


def test_calendar_cancelled_event_cancels_escribe_meeting():
    day = datetime(2026, 9, 10).date()
    spider._calendar_event_urls = {
        day: [("Traffic Safety Commission Meeting - Cancelled", EVENT_URL)]
    }
    meeting = {
        "title": "Traffic Safety Commission Regular Meeting",
        "start": datetime(2026, 9, 10, 18),
        "links": [],
    }
    with freeze_time("2026-01-09"):
        spider._parse_sources(day, [meeting])
    assert meeting["source"] == EVENT_URL
    assert meeting["status"] == CANCELLED
