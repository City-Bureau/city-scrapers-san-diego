from datetime import datetime
from os.path import dirname, join
from unittest.mock import patch

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_citychula import (
    ChulaVistaBoardOfEthicsSpider,
    ChulaVistaTrafficSafetyCommissionSpider,
)

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


def _event_url(event_id, day):
    """City calendar event URL, as linked from that day's calendar month."""
    return (
        "https://www.chulavistaca.gov/Home/Components/Calendar/Event/"
        f"{event_id}/2854?curm={day.month}&cury={day.year}"
    )


def _source_for(titles, events, start):
    day = start.date()
    spider._calendar_event_urls = {day: events}
    meetings = [{"title": t, "start": start} for t in titles]
    spider._parse_sources(day, meetings)
    return [m["source"] for m in meetings]


def test_source_only_matching_meeting_gets_calendar_event():
    """
    Real case: Board of Ethics, Feb 25, 2026. eScribe has two interview panels;
    the city calendar only lists the subcommittee one.
    """
    start = datetime(2026, 2, 25, 14)
    event_url = _event_url(38373, start)
    sources = _source_for(
        [
            "Board of Ethics Interview Panel",
            "Board of Ethics Subcommittee Interview Panel",
        ],
        [("Board of Ethics - Subcommittee Interview Panel", event_url)],
        start,
    )
    assert sources == [ESCRIBE_URL, event_url]


def test_source_pd_matches_police_department():
    """
    Real case: Police Department Community Advisory Committee, Jan 8, 2026.
    The city calendar's "PD" title matches eScribe's "Police Department" one.
    """
    start = datetime(2026, 1, 8, 9, 30)
    event_url = _event_url(38048, start)
    sources = _source_for(
        ["Police Department Community Advisory Committee Special Meeting"],
        [("PD Community Advisory Committee - Special Meeting", event_url)],
        start,
    )
    assert sources == [event_url]


def test_source_no_calendar_event_uses_escribe():
    """
    Real case: Board of Ethics Regular Meeting, Apr 15, 2026, is in eScribe
    but has no city calendar event that day.
    """
    start = datetime(2026, 4, 15, 17, 15)
    assert _source_for(["Board of Ethics Regular Meeting"], [], start) == [ESCRIBE_URL]


# --- city calendar meetings missing from eScribe ---


def test_city_calendar_fetches_escribe_period():
    with freeze_time("2026-01-09"):
        with patch.object(spider, "_fetch_city_calendar", return_value=None):
            list(spider.start_requests())
    months = spider._fetched_calendar_months
    assert min(months) == (2023, 1)
    assert max(months) == (2027, 1)
    assert len(months) == 49


def _calendar_meeting(title, start, event_url):
    return {
        "title": title,
        "start": start,
        "links": [],
        "source": event_url,
        "id": event_url,
    }


def test_calendar_meeting_not_in_escribe_is_kept():
    """
    Real case: Traffic Safety Commission, Jun-Aug 2025. eScribe has the Jun 12
    and Aug 14 meetings; the cancelled Jul 10 meeting is only on the city
    calendar, so it is kept as its own meeting.
    """
    traffic_spider = ChulaVistaTrafficSafetyCommissionSpider()
    traffic_response = file_response(
        join(dirname(__file__), "files", "sandie_citychula_traffic_safety.json"),
        url="https://pub-chulavista.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings?MeetingViewId=29",  # noqa
    )
    june = datetime(2025, 6, 12, 18)
    july = datetime(2025, 7, 10, 18)
    august = datetime(2025, 8, 14, 18)
    events = [
        ("Traffic Safety Commission", june, _event_url(35570, june)),
        ("CANCELLED Traffic Safety Commission", july, _event_url(36244, july)),
        ("Traffic Safety Commission", august, _event_url(36612, august)),
    ]
    with freeze_time("2026-01-09"):
        traffic_spider._calendar_event_urls = {
            start.date(): [(title, url)] for title, start, url in events
        }
        traffic_spider._calendar_meetings = [
            _calendar_meeting(*event) for event in events
        ]
        items = list(traffic_spider.parse_calendar(traffic_response))

    june_item, august_item, calendar_item = items
    assert june_item["source"] == _event_url(35570, june)
    assert june_item["links"]
    assert august_item["source"] == _event_url(36612, august)
    assert august_item["links"]
    assert calendar_item["title"] == "CANCELLED Traffic Safety Commission"
    assert calendar_item["start"] == july
    assert calendar_item["source"] == _event_url(36244, july)
    assert calendar_item["links"] == []


def test_calendar_cancelled_event_cancels_escribe_meeting_if_no_cancellation_notice():
    day = datetime(2026, 9, 10).date()
    event_url = _event_url(40994, day)
    spider._calendar_event_urls = {
        day: [("Traffic Safety Commission Meeting - Cancelled", event_url)]
    }
    meeting = {
        "title": "Traffic Safety Commission Regular Meeting",
        "start": datetime(2026, 9, 10, 18),
        "links": [],
    }
    with freeze_time("2026-01-09"):
        spider._parse_sources(day, [meeting])
    assert meeting["source"] == event_url
    assert meeting["status"] == CANCELLED


def test_calendar_cancelled_event_cancels_escribe_meeting_with_agenda_and_notice():
    """
    Real case: Veterans Advisory Commission, Nov 20, 2024. eScribe lists both a
    cancellation notice and an agenda, so on its own the meeting looks held;
    the city calendar title marks it cancelled.
    """
    day = datetime(2024, 11, 20).date()
    event_source = _event_url(33142, day)
    meeting = {
        "title": "Veterans Advisory Commission Regular Meeting",
        "start": datetime(2024, 11, 20, 18),
        "links": [
            {
                "href": "https://pub-chulavista.escribemeetings.com/FileStream.ashx?DocumentId=46503",  # noqa
                "title": "Cancellation Notice (PDF)",
            },
            {
                "href": "https://pub-chulavista.escribemeetings.com/Meeting.aspx?Id=e79c6d4a-27de-45f0-8b65-cee348359cc1&Agenda=Agenda&lang=English",  # noqa
                "title": "Agenda (HTML)",
            },
        ],
    }

    with freeze_time("2026-01-09"):
        # status as set in _create_meeting: the agenda outweighs the notice
        meeting["status"] = spider._get_status(
            meeting, text=spider._status_text(meeting)
        )
        assert meeting["status"] == "passed"

        spider._calendar_event_urls = {
            day: [
                (
                    "Veterans Advisory Commission Regular Meeting - Cancelled",
                    event_source,
                )
            ]
        }
        spider._parse_sources(day, [meeting])

    assert meeting["source"] == event_source
    assert meeting["status"] == CANCELLED
