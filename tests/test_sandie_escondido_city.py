from datetime import datetime
from os.path import dirname, join
from unittest.mock import Mock

import pytest
import scrapy
from city_scrapers_core.constants import (
    BOARD,
    CANCELLED,
    CITY_COUNCIL,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy.http import HtmlResponse

from city_scrapers.spiders.sandie_escondido_city import (
    SandieEscondidoCityCityCouncilSpider,
    SandieEscondidoCityLibraryBoardOfTrusteesSpider,
    SandieEscondidoCityPublicArtCommissionSpider,
    SandieEscondidoCitySubcommitteeSpider,
    SandieEscondidoCityTransportationCommissionSpider,
)

BASE_URL = "https://escondido-ca.municodemeetings.com"


def _file(name, url):
    return file_response(join(dirname(__file__), "files", name), url=url)


test_response = _file("sandie_escondido_city.html", f"{BASE_URL}/")
calendar_response = _file(
    "sandie_escondido_city_calendar.html",
    "https://ca-escondido.civicplus.com/calendar.aspx",
)


@pytest.fixture(scope="module")
def spider():
    return SandieEscondidoCityCityCouncilSpider()


@pytest.fixture(scope="module")
def parsed_results(spider):
    with freeze_time("2026-11-17"):
        return list(spider.parse(test_response))


@pytest.fixture(scope="module")
def parsed_items(parsed_results):
    """Meetings without a video, which are yielded from the listing"""
    return [item for item in parsed_results if isinstance(item, Meeting)]


@pytest.fixture(scope="module")
def requests(parsed_results):
    return [item for item in parsed_results if isinstance(item, scrapy.Request)]


@pytest.fixture(scope="module")
def video_requests(spider, requests):
    """Meetings with a video are yielded after their details page is fetched"""
    return [req for req in requests if req.callback == spider._parse_video]


@pytest.fixture(scope="module")
def page_requests(requests, video_requests):
    return [req for req in requests if req not in video_requests]


@pytest.fixture(scope="module")
def video_items(spider, video_requests):
    """The 10/07/2026 council meeting, parsed from its details page"""
    detail_request = video_requests[1]
    detail_response = _file("sandie_escondido_city_detail.html", detail_request.url)
    with freeze_time("2026-11-17"):
        return list(spider._parse_video(detail_response, **detail_request.cb_kwargs))


@pytest.fixture(scope="module")
def calendar_items():
    calendar_spider = SandieEscondidoCityLibraryBoardOfTrusteesSpider()
    # The Library Board meeting on 12/10/2026 at 4:00 PM is listed on the portal
    calendar_spider.seen_starts.add(datetime(2026, 12, 10, 16, 0))
    with freeze_time("2026-11-17"):
        return list(calendar_spider._parse_calendar(calendar_response))


@freeze_time("2026-11-17 12:00")
def test_start_requests(spider):
    # The listing's date range ends a year ahead, on 11/17/2027
    date_range = (
        "date_filter_1%5Bvalue%5D%5Bmonth%5D=11"
        "&date_filter_1%5Bvalue%5D%5Bday%5D=17"
        "&date_filter_1%5Bvalue%5D%5Byear%5D=2027"
    )
    urls = [request.url for request in spider.start_requests()]
    assert urls == [f"{BASE_URL}/?field_microsite_tid=2&{date_range}"]
    subcommittee_spider = SandieEscondidoCitySubcommitteeSpider()
    urls = [request.url for request in subcommittee_spider.start_requests()]
    assert urls == [f"{BASE_URL}/?field_microsite_tid=8&{date_range}"]


def test_count(parsed_items, video_requests):
    # 25 rows, one of which repeats a Planning Commission meeting, and 6 of
    # which list a council meeting along with its closed session. The 4 meetings
    # of the 2 rows with a video are yielded from their details pages.
    assert len(parsed_items) == 26
    meetings_with_video = [
        meeting
        for request in video_requests
        for meeting in request.cb_kwargs["meetings"]
    ]
    assert len(meetings_with_video) == 4


def test_duplicates_removed(parsed_items):
    ids = [item["id"] for item in parsed_items]
    assert len(ids) == len(set(ids))


def test_next_page(page_requests):
    assert [request.url for request in page_requests] == [
        f"{BASE_URL}/meetings3?page=1"
    ]


def test_video_requests(video_requests):
    assert [request.url for request in video_requests] == [
        f"{BASE_URL}/bc-citycouncil/page/council-meeting-closed-session-400-pm-32",
        f"{BASE_URL}/bc-citycouncil/page/council-meeting-closed-session-430-pm-10",
    ]


def test_title(parsed_items):
    # "Cancelled - Council Meeting (Closed Session 4:00 PM)"
    assert parsed_items[0]["title"] == "Council Meeting"
    assert parsed_items[1]["title"] == "Council Meeting (Closed Session)"
    assert parsed_items[2]["title"] == "Library Board of Trustees Meeting"
    # "CANCELLED - Economic Development Subcommittee Meeting"
    assert parsed_items[15]["title"] == "Economic Development Subcommittee Meeting"
    # "CANCELLED: Council/School Subcommittee Meeting"
    assert parsed_items[19]["title"] == "Council/School Subcommittee Meeting"


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2026, 12, 16, 17, 0)
    assert parsed_items[17]["start"] == datetime(2026, 10, 28, 10, 0)


def test_closed_session_start(parsed_items, video_items):
    # "Council Meeting (Closed Session 4:00 PM)" at 5:00 PM
    assert parsed_items[1]["start"] == datetime(2026, 12, 16, 16, 0)
    # "Council Meeting (Closed Session 4:30 PM)" at 5:00 PM
    assert video_items[1]["start"] == datetime(2026, 10, 7, 16, 30)


def test_end(parsed_items):
    assert parsed_items[0]["end"] is None


def test_closed_to_public(parsed_items):
    assert parsed_items[0]["closed_to_public"] is False
    assert parsed_items[1]["closed_to_public"] is True
    assert parsed_items[2]["closed_to_public"] is False


def test_time_notes(parsed_items):
    assert parsed_items[0]["time_notes"] == ""


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "sandie_escondido_city_council/202612161700/x/council_meeting"
    )
    assert (
        parsed_items[1]["id"]
        == "sandie_escondido_city_council/202612161600/x/council_meeting_closed_session_"  # noqa
    )


def test_status(parsed_items):
    # "Cancelled - Council Meeting (Closed Session 4:00 PM)": only the regular
    # meeting is cancelled
    assert parsed_items[0]["status"] == CANCELLED
    assert parsed_items[1]["status"] == TENTATIVE
    assert parsed_items[2]["status"] == TENTATIVE
    assert parsed_items[12]["status"] == PASSED


def _parse_row(title, date="2024-10-09T17:00:00-07:00"):
    """Parse a listing with a single row with the given title"""
    body = f"""
    <table><tbody><tr>
      <td><span class="date-display-single" content="{date}"></span></td>
      <td class="views-field views-field-title">{title}</td>
    </tr></tbody></table>
    """
    response = HtmlResponse(url=f"{BASE_URL}/", body=body, encoding="utf-8")
    # Within the lookback of the 2024 meetings
    with freeze_time("2026-01-01"):
        return [
            item
            for item in SandieEscondidoCityCityCouncilSpider().parse(response)
            if isinstance(item, Meeting)
        ]


@pytest.mark.parametrize(
    "title",
    [
        "Council Meeting (Closed Session 4:00 PM - Cancelled)",
        "Council Meeting (Cancelled - Closed Session 4:00 PM)",
    ],
)
def test_closed_session_cancelled(title):
    """Only the closed session is cancelled, the regular meeting took place"""
    regular, closed = _parse_row(title)
    assert regular["title"] == "Council Meeting"
    assert regular["start"] == datetime(2024, 10, 9, 17, 0)
    assert regular["status"] == PASSED
    assert regular["closed_to_public"] is False
    assert closed["title"] == "Council Meeting (Closed Session)"
    assert closed["start"] == datetime(2024, 10, 9, 16, 0)
    assert closed["status"] == CANCELLED
    assert closed["closed_to_public"] is True


def test_regular_meeting_cancelled():
    """Only the regular meeting is cancelled, the closed session took place"""
    regular, closed = _parse_row("Cancelled - Council Meeting (Closed Session 4:00 PM)")
    assert regular["status"] == CANCELLED
    assert closed["status"] == PASSED


def test_closed_session_only():
    """A row that is only a closed session lists a single meeting"""
    (meeting,) = _parse_row(
        "Cancelled - Closed Session Council Meeting", "2024-06-19T16:00:00-07:00"
    )
    assert meeting["title"] == "Closed Session Council Meeting"
    assert meeting["status"] == CANCELLED
    assert meeting["closed_to_public"] is True


@pytest.mark.parametrize(
    "raw_title,title",
    [
        ("Council Special Meeting - 4pm", "Special Council Meeting"),
        ("Planning Commission Meeting - 7:00 P.M.", "Planning Commission Meeting"),
        ("Special Council Meeting", "Special Council Meeting"),
    ],
)
def test_title_normalized(raw_title, title):
    (meeting,) = _parse_row(raw_title, "2024-12-16T16:00:00-08:00")
    assert meeting["title"] == title
    assert meeting["start"] == datetime(2024, 12, 16, 16, 0)


def test_no_closed_session():
    """A "(No Closed Session)" note doesn't list a closed session"""
    (meeting,) = _parse_row(
        "Special Meeting (No Closed Session)", "2026-03-25T08:30:00-07:00"
    )
    assert meeting["title"] == "Special Meeting (No Closed Session)"
    assert meeting["start"] == datetime(2026, 3, 25, 8, 30)
    assert meeting["status"] == TENTATIVE
    assert meeting["closed_to_public"] is False


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "Escondido City Hall, Council Chambers",
        "address": "201 N. Broadway, Escondido, CA 92025",
    }


def test_source(parsed_items):
    assert parsed_items[0]["source"] == (
        f"{BASE_URL}/bc-citycouncil/page/cancelled-council-meeting-closed-session-400-pm-5"  # noqa
    )


def test_links(parsed_items):
    assert parsed_items[0]["links"] == []
    assert parsed_items[12]["links"] == [
        {
            "href": "https://mccmeetings.blob.core.usgovcloudapi.net/escondidca-pubu/MEET-Packet-ebcd19bcdfae41be90702c8c51a12a64.pdf",  # noqa
            "title": "Agenda Packet",
        },
    ]


def test_video_links(video_items):
    """Both the regular meeting and its closed session link to the video"""
    expected = [
        {
            "href": "https://mccmeetings.blob.core.usgovcloudapi.net/escondidca-pubu/MEET-Packet-7699b019eb8840cfab1347d7b26c4a55.pdf",  # noqa
            "title": "Agenda Packet",
        },
        {
            "href": "https://mccmeetings.blob.core.usgovcloudapi.net/escondidca-pubu/MEET-Minutes-7699b019eb8840cfab1347d7b26c4a55.pdf",  # noqa
            "title": "Minutes",
        },
        {
            "href": "https://escondido.12milesout.com/Video/Meeting/c0227366-b885-4fb3-93ed-f77ce4982953",  # noqa
            "title": "Video",
        },
    ]
    assert [item["title"] for item in video_items] == [
        "Council Meeting",
        "Council Meeting (Closed Session)",
    ]
    assert video_items[0]["links"] == expected
    assert video_items[1]["links"] == expected


def test_video_page_error(spider, video_requests):
    """Meetings keep the details page link if the page can't be fetched"""
    request = video_requests[0]
    failure = Mock(request=request, value=Exception("timeout"))
    meetings = list(spider._handle_video_error(failure))
    assert [meeting["start"] for meeting in meetings] == [
        datetime(2026, 11, 4, 17, 0),
        datetime(2026, 11, 4, 16, 0),
    ]
    assert meetings[0]["links"][-1] == {
        "href": f"{BASE_URL}/bc-citycouncil/page/council-meeting-closed-session-400-pm-32",  # noqa
        "title": "Video",
    }


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == CITY_COUNCIL


def test_all_day(parsed_items):
    assert all(item["all_day"] is False for item in parsed_items)


def test_lookback_stops_pagination():
    """Pages aren't followed once meetings older than the lookback are reached"""
    with freeze_time("2030-01-01"):
        results = list(SandieEscondidoCityCityCouncilSpider().parse(test_response))
    assert [item for item in results if isinstance(item, Meeting)] == []
    assert [item for item in results if isinstance(item, scrapy.Request)] == []


@freeze_time("2026-11-17 12:00")
def test_calendar_request():
    """The calendar is requested after the portal's last page"""
    response = HtmlResponse(url=f"{BASE_URL}/", body=b"<table></table>")
    (request,) = list(SandieEscondidoCityLibraryBoardOfTrusteesSpider().parse(response))
    assert request.url == (
        "https://ca-escondido.civicplus.com/calendar.aspx?Keywords="
        "&startDate=11%2F17%2F2026&enddate=11%2F17%2F2027&CID=30"
        "&showPastEvents=false"
    )


def test_no_calendar_for_city_council():
    response = HtmlResponse(url=f"{BASE_URL}/", body=b"<table></table>")
    assert list(SandieEscondidoCityCityCouncilSpider().parse(response)) == []


def test_calendar_count(calendar_items):
    # 13 Library Board meetings in the calendar, one of which is on the portal
    assert len(calendar_items) == 12


def test_calendar_skips_portal_meetings(calendar_items):
    starts = [item["start"] for item in calendar_items]
    assert datetime(2026, 12, 10, 16, 0) not in starts
    assert starts[0] == datetime(2026, 11, 12, 16, 0)
    assert starts[-1] == datetime(2027, 11, 11, 16, 0)


def test_calendar_meeting(calendar_items):
    item = calendar_items[1]
    assert item["title"] == "Library Board of Trustees Meeting"
    assert item["start"] == datetime(2027, 1, 14, 18, 0)
    assert item["end"] is None
    assert item["classification"] == BOARD
    assert item["status"] == TENTATIVE
    assert item["closed_to_public"] is False
    assert item["location"] == {
        "name": "Escondido City Hall, Council Chambers",
        "address": "201 N. Broadway, Escondido, CA 92025",
    }
    assert item["links"] == []
    assert item["source"].startswith(
        "https://ca-escondido.civicplus.com/Calendar.aspx?EID="
    )
    assert "&" not in item["source"]
    assert (
        item["id"]
        == "sandie_escondido_library_board_of_trustees/202701141800/x/library_board_of_trustees_meeting"  # noqa
    )


def _parse_calendar(spider_class):
    with freeze_time("2026-11-17"):
        return list(spider_class()._parse_calendar(calendar_response))


def test_calendar_patterns():
    transportation = _parse_calendar(SandieEscondidoCityTransportationCommissionSpider)
    assert [item["title"] for item in transportation] == [
        "Transportation and Community Safety Commission"
    ] * 4
    public_art = _parse_calendar(SandieEscondidoCityPublicArtCommissionSpider)
    assert {item["title"] for item in public_art} == {"Public Art Commission Meeting"}
    subcommittees = _parse_calendar(SandieEscondidoCitySubcommitteeSpider)
    assert [(item["title"], item["location"]["name"]) for item in subcommittees] == [
        ("Utilities Subcommittee Meeting", "Escondido City Hall, Mitchell Room")
    ]
