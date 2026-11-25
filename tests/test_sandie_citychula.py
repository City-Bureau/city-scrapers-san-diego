from datetime import datetime
from os.path import dirname, join
from unittest.mock import Mock, patch

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.utils import file_response
from curl_cffi import requests as curl_requests
from freezegun import freeze_time
from scrapy import signals
from scrapy.http import HtmlResponse

from city_scrapers.spiders.sandie_citychula import (
    ChulaVistaBoardOfEthicsSpider,
    ChulaVistaTrafficSafetyCommissionSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "sandie_citychula.json"),
    url="https://pub-chulavista.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings?MeetingViewId=15",  # noqa
)

spider = ChulaVistaBoardOfEthicsSpider()


def _calendar_spider(spider_class=ChulaVistaBoardOfEthicsSpider):
    """A spider with a city calendar ID, as the fixtures use CID 99."""
    calendar_spider = spider_class()
    calendar_spider.calendar_id = 99
    calendar_spider.calendar_exclude_keywords = ["Awards", "Reception"]
    return calendar_spider


def _city_response(name, url):
    return file_response(join(dirname(__file__), "files", name), url=url)


city_calendar_response = _city_response(
    "sandie_citychula_civicplus.html",
    "https://www.chulavistaca.gov/Calendar.aspx?CID=99",
)


@pytest.fixture
def parsed_items():
    with freeze_time("2026-01-09"):
        spider._calendar_events = []
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


# --- city calendar (CivicPlus, fetched with curl_cffi) ---

EVENT_URL = "https://www.chulavistaca.gov/Calendar.aspx?EID={}"
CURL_GET = "city_scrapers.mixins.sandie_citychula.curl_requests.get"
SLEEP = "city_scrapers.mixins.sandie_citychula.time.sleep"


def _city_pages(detail_fixture=None):
    """
    Stand-in for _city_get: the calendar fixture, then the detail page fixture
    (None: request failed, "": page without a location).
    """

    def city_get(url, tries=1):
        if "CID=" in url:
            return _city_response("sandie_citychula_civicplus.html", url)
        if detail_fixture is None:
            return None
        if detail_fixture == "":
            return HtmlResponse(url, body=b"<html></html>")
        return _city_response(detail_fixture, url)

    return city_get


def _run(detail_fixture="sandie_citychula_civicplus_detail.html"):
    """Run the spider on the fixtures, returning it and its meetings."""
    calendar_spider = _calendar_spider()
    with freeze_time("2026-01-09"), patch.object(
        calendar_spider, "_city_get", side_effect=_city_pages(detail_fixture)
    ):
        (request,) = list(calendar_spider.start_requests())
        return calendar_spider, list(request.callback(test_response))


def test_start_requests_without_calendar_id_requests_escribe():
    escribe_spider = ChulaVistaBoardOfEthicsSpider()
    escribe_spider.calendar_id = None
    with freeze_time("2026-01-09"), patch.object(
        escribe_spider, "_city_get"
    ) as city_get:
        (request,) = list(escribe_spider.start_requests())
    assert request.url.startswith(escribe_spider.api_url_calendar)
    city_get.assert_not_called()


def test_city_calendar_url_date_range():
    with freeze_time("2026-01-09 20:00"):
        url = _calendar_spider()._city_calendar_url()
    assert url.startswith("https://www.chulavistaca.gov/Calendar.aspx?")
    assert "CID=99" in url
    # same period as eScribe: 3 years back, 1 year ahead
    assert "startDate=01%2F09%2F2023" in url
    assert "enddate=01%2F09%2F2027" in url


def test_city_get_uses_curl_cffi():
    url = EVENT_URL.format(1)
    with patch(
        CURL_GET, return_value=Mock(status_code=200, content=b"<p>ok</p>")
    ) as get:
        response = spider._city_get(url)
    assert get.call_args.kwargs["impersonate"] == spider.curl_impersonate
    assert response.url == url
    assert response.css("p::text").get() == "ok"


@pytest.mark.parametrize(
    "curl_result",
    [
        {"return_value": Mock(status_code=403)},
        {"side_effect": curl_requests.RequestsError("timeout")},
    ],
)
def test_city_get_failure_returns_none(curl_result):
    with patch(CURL_GET, **curl_result):
        assert spider._city_get(EVENT_URL.format(1)) is None


def test_city_calendar_retried_after_one_off_403():
    calendar_spider = _calendar_spider()
    with open(
        join(dirname(__file__), "files", "sandie_citychula_civicplus.html"), "rb"
    ) as f:
        calendar_page = Mock(status_code=200, content=f.read())
    with freeze_time("2026-01-09"), patch(
        CURL_GET, side_effect=[Mock(status_code=403), calendar_page]
    ) as get, patch(SLEEP) as sleep:
        list(calendar_spider.start_requests())
    assert get.call_count == calendar_spider.calendar_tries == 2
    sleep.assert_called_once_with(calendar_spider.retry_backoff)
    assert len(calendar_spider._calendar_events) == 2
    assert calendar_spider._problems == []


def test_city_calendar_failure_after_all_tries_reported():
    calendar_spider = _calendar_spider()
    with patch(CURL_GET, return_value=Mock(status_code=403)) as get, patch(SLEEP):
        list(calendar_spider.start_requests())
    assert get.call_count == 2
    assert "request to city calendar" in _closed_spider_error(calendar_spider)


def test_city_calendar_events():
    calendar_spider, _ = _run()
    events = calendar_spider._calendar_events
    # the awards reception is excluded
    assert [e["url"] for e in events] == [
        EVENT_URL.format(1001),
        EVENT_URL.format(1002),
    ]
    assert events[0]["title"] == "Board of Ethics Regular Meeting"
    assert events[0]["start"] == datetime(2025, 12, 17, 17, 15)
    assert events[0]["end"] == datetime(2025, 12, 17, 18, 15)
    assert events[1]["end"] is None


def test_matched_escribe_meeting_source_is_detail_page():
    _, (meeting, _) = _run()
    assert meeting["source"] == EVENT_URL.format(1001)
    # the eScribe location is kept
    assert meeting["location"] == {
        "name": "City Hall, Bldg. A, Executive Conference Room #103",
        "address": "276 Fourth Avenue, Chula Vista, CA",
    }
    assert meeting["links"]


def test_city_meeting_location_from_detail_page():
    _, (_, meeting) = _run()
    assert meeting["title"] == "Board of Ethics Regular Meeting"
    assert meeting["start"] == datetime(2026, 2, 18, 17, 15)
    assert meeting["source"] == EVENT_URL.format(1002)
    assert meeting["links"] == []
    assert meeting["status"] == "tentative"
    assert meeting["location"] == {
        "name": "Civic Center Library - Community Room",
        "address": "365 F Street, Chula Vista, CA 91910",
    }


def test_city_location_from_detail_text():
    detail = _city_response(
        "sandie_citychula_civicplus_detail_text.html", EVENT_URL.format(1)
    )
    assert spider._parse_city_location(detail) == {
        "name": "Council Chambers",
        "address": "276 Fourth Avenue, Chula Vista, CA 91910",
    }


def test_city_location_not_found():
    detail = HtmlResponse(EVENT_URL.format(1), body=b"<html></html>")
    assert spider._parse_city_location(detail) is None


def test_city_event_failure_uses_default_location():
    calendar_spider, (_, meeting) = _run(detail_fixture=None)
    assert meeting["location"] == calendar_spider.location
    assert meeting["source"] == EVENT_URL.format(1002)


# --- source matching between eScribe meetings and city calendar events ---

ESCRIBE_URL = "https://pub-chulavista.escribemeetings.com/?MeetingviewId=15&Year=2026"


def _event(title, start, event_id):
    return {
        "title": title,
        "start": start,
        "end": None,
        "url": EVENT_URL.format(event_id),
    }


def _source_for(titles, events, start):
    spider._calendar_events = events
    meetings = [{"title": t, "start": start} for t in titles]
    spider._parse_sources(start.date(), meetings)
    return [m["source"] for m in meetings]


def test_source_only_matching_meeting_gets_calendar_event():
    """
    Real case: Board of Ethics, Feb 25, 2026. eScribe has two interview panels;
    the city calendar only lists the subcommittee one.
    """
    start = datetime(2026, 2, 25, 14)
    sources = _source_for(
        [
            "Board of Ethics Interview Panel",
            "Board of Ethics Subcommittee Interview Panel",
        ],
        [_event("Board of Ethics - Subcommittee Interview Panel", start, 38373)],
        start,
    )
    assert sources == [ESCRIBE_URL, EVENT_URL.format(38373)]


def test_source_pd_matches_police_department():
    """
    Real case: Police Department Community Advisory Committee, Jan 8, 2026.
    The city calendar's "PD" title matches eScribe's "Police Department" one.
    """
    start = datetime(2026, 1, 8, 9, 30)
    sources = _source_for(
        ["Police Department Community Advisory Committee Special Meeting"],
        [_event("PD Community Advisory Committee - Special Meeting", start, 38048)],
        start,
    )
    assert sources == [EVENT_URL.format(38048)]


def test_source_no_calendar_event_uses_escribe():
    """
    Real case: Board of Ethics Regular Meeting, Apr 15, 2026, is in eScribe
    but has no city calendar event that day.
    """
    start = datetime(2026, 4, 15, 17, 15)
    assert _source_for(["Board of Ethics Regular Meeting"], [], start) == [ESCRIBE_URL]


def test_source_event_on_other_day_not_matched():
    start = datetime(2026, 4, 15, 17, 15)
    events = [_event("Board of Ethics Regular Meeting", datetime(2026, 4, 16, 17), 1)]
    assert _source_for(["Board of Ethics Regular Meeting"], events, start) == [
        ESCRIBE_URL
    ]


def test_city_event_start_overrides_escribe_start():
    """
    Real case: Traffic Safety Commission, Dec 10, 2026. eScribe lists the
    meeting at 10:00 AM; the city calendar event (EID=776) and every other
    meeting this year are at 6:00 PM.
    """
    traffic_spider = ChulaVistaTrafficSafetyCommissionSpider()
    event = _event("Traffic Safety Commission", datetime(2026, 12, 10, 18), 776)
    traffic_spider._calendar_events = [event]
    meeting = Meeting(
        title="Traffic Safety Commission Regular Meeting",
        start=datetime(2026, 12, 10, 10),
        end=datetime(2026, 12, 10, 13),
        links=[],
    )
    with freeze_time("2026-11-25"):
        meeting["status"] = traffic_spider._get_status(meeting)
        meeting["id"] = traffic_spider._get_id(meeting)
        old_id = meeting["id"]
        traffic_spider._parse_sources(meeting["start"].date(), [meeting])
    assert meeting["source"] == EVENT_URL.format(776)
    assert meeting["start"] == datetime(2026, 12, 10, 18)
    assert meeting["end"] is None
    assert meeting["id"] != old_id
    assert "/202612101800/" in meeting["id"]


def test_city_event_without_time_keeps_escribe_start():
    start = datetime(2026, 12, 10, 18)
    spider._calendar_events = [
        _event("Board of Ethics Regular Meeting", datetime(2026, 12, 10), 1)
    ]
    meeting = {"title": "Board of Ethics Regular Meeting", "start": start}
    with freeze_time("2026-11-25"):
        spider._parse_sources(start.date(), [meeting])
    assert meeting["start"] == start


# --- city calendar meetings missing from eScribe ---


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
    traffic_spider._calendar_events = [
        _event("Traffic Safety Commission", june, 35570),
        _event("CANCELLED Traffic Safety Commission", july, 36244),
        _event("Traffic Safety Commission", august, 36612),
    ]
    with freeze_time("2026-01-09"), patch.object(
        traffic_spider, "_city_get", return_value=None
    ):
        june_item, august_item, calendar_item = list(
            traffic_spider.parse_calendar(traffic_response)
        )

    assert june_item["source"] == EVENT_URL.format(35570)
    assert june_item["links"]
    assert august_item["source"] == EVENT_URL.format(36612)
    assert august_item["links"]
    assert calendar_item["title"] == "CANCELLED Traffic Safety Commission"
    assert calendar_item["start"] == july
    assert calendar_item["source"] == EVENT_URL.format(36244)
    assert calendar_item["links"] == []
    assert calendar_item["status"] == CANCELLED
    assert calendar_item["location"] == traffic_spider.location


def test_calendar_cancelled_event_cancels_escribe_meeting_if_no_cancellation_notice():
    start = datetime(2026, 9, 10, 18)
    spider._calendar_events = [
        _event("Traffic Safety Commission Meeting - Cancelled", start, 40994)
    ]
    meeting = {
        "title": "Traffic Safety Commission Regular Meeting",
        "start": start,
        "links": [],
    }
    with freeze_time("2026-01-09"):
        spider._parse_sources(start.date(), [meeting])
    assert meeting["source"] == EVENT_URL.format(40994)
    assert meeting["status"] == CANCELLED


def test_calendar_cancelled_event_cancels_escribe_meeting_with_agenda_and_notice():
    """
    Real case: Veterans Advisory Commission, Nov 20, 2024. eScribe lists both a
    cancellation notice and an agenda, so on its own the meeting looks held;
    the city calendar title marks it cancelled.
    """
    start = datetime(2024, 11, 20, 18)
    meeting = {
        "title": "Veterans Advisory Commission Regular Meeting",
        "start": start,
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

        spider._calendar_events = [
            _event(
                "Veterans Advisory Commission Regular Meeting - Cancelled",
                start,
                33142,
            )
        ]
        spider._parse_sources(start.date(), [meeting])

    assert meeting["source"] == EVENT_URL.format(33142)
    assert meeting["status"] == CANCELLED


# --- fail loudly: major breakages are reported once on spider close ---


def _closed_spider_error(calendar_spider, reason="finished"):
    """Close the spider and return the error sent to Sentry, if any."""
    calendar_spider.crawler = Mock()
    calendar_spider._on_spider_closed(calendar_spider, reason)
    send = calendar_spider.crawler.signals.send_catch_log
    if not send.called:
        return None
    assert send.call_args.kwargs["signal"] is signals.spider_error
    return str(send.call_args.kwargs["failure"].value)


def test_no_error_reported_for_normal_run():
    calendar_spider, _ = _run()
    assert _closed_spider_error(calendar_spider) is None


def test_zero_meetings_reported():
    calendar_spider = _calendar_spider()
    assert "0 meetings parsed" in _closed_spider_error(calendar_spider)


def test_zero_meetings_not_reported_when_not_finished():
    calendar_spider = _calendar_spider()
    assert _closed_spider_error(calendar_spider, reason="shutdown") is None


def test_escribe_failure_reported_and_city_meetings_kept():
    calendar_spider = _calendar_spider()
    with freeze_time("2026-01-09"), patch.object(
        calendar_spider,
        "_city_get",
        side_effect=_city_pages("sandie_citychula_civicplus_detail.html"),
    ):
        (request,) = list(calendar_spider.start_requests())
        assert request.errback == calendar_spider._escribe_failed
        meetings = list(request.errback(Mock(request=request, value="Timeout")))
    # every city event is kept, as none matched an eScribe meeting
    assert [m["source"] for m in meetings] == [
        EVENT_URL.format(1001),
        EVENT_URL.format(1002),
    ]
    error = _closed_spider_error(calendar_spider)
    assert f"request to {request.url} failed" in error
    assert "0 meetings parsed" not in error


def test_city_calendar_failure_reported_and_escribe_requested():
    calendar_spider = _calendar_spider()
    with patch.object(calendar_spider, "_city_get", return_value=None):
        (request,) = list(calendar_spider.start_requests())
    assert request.url.startswith(calendar_spider.api_url_calendar)
    assert "request to city calendar" in _closed_spider_error(calendar_spider)


def test_missing_calendar_not_reported():
    """Calendars with no events in range have no CID block on the page."""
    calendar_spider = _calendar_spider()
    calendar_spider.calendar_id = 12345
    calendar_spider._parse_city_calendar(city_calendar_response)
    assert calendar_spider._calendar_events == []
    assert calendar_spider._problems == []


def test_unexpected_escribe_response_reported():
    calendar_spider = _calendar_spider()
    response = HtmlResponse(
        calendar_spider.api_url_calendar, body=b"<html>Service Unavailable</html>"
    )
    assert list(calendar_spider.parse_calendar(response)) == []
    assert "Unexpected eScribe response" in _closed_spider_error(calendar_spider)


def test_all_detail_pages_failing_reported():
    calendar_spider, _ = _run(detail_fixture=None)
    assert "all 1 city calendar detail page(s) failed" in _closed_spider_error(
        calendar_spider
    )


def test_detail_pages_without_location_reported():
    calendar_spider, _ = _run(detail_fixture="")
    assert "no location found on any of 1" in _closed_spider_error(calendar_spider)
