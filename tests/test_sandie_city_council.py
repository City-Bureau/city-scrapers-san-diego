from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import (
    CANCELLED,
    CITY_COUNCIL,
    COMMITTEE,
    NOT_CLASSIFIED,
    PASSED,
)
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy import Selector
from scrapy.http import HtmlResponse, TextResponse

from city_scrapers.spiders.sandie_city_council import SandieCityCouncilSpider


def _file(name):
    return join(dirname(__file__), "files", name)


# Views AJAX response for October 2026, as fetched by _calendar_requests
test_ajax_response = file_response(
    _file("sandie_city_council_ajax.json"),
    url=f"{SandieCityCouncilSpider.ajax_url}&calendar_timestamp=1790841600",
)

# Committee documents search for Oct 5 - Dec 5 2026
documents_response = file_response(
    _file("sandie_city_council_documents.html"),
    url=SandieCityCouncilSpider.documents_url,
)

# City Council documents search for Oct 1 2026 - Jan 1 2027
council_documents_response = file_response(
    _file("sandie_city_council_council_documents.html"),
    url=SandieCityCouncilSpider.council_documents_url,
)


def _videos_response(view_id):
    return file_response(
        _file(f"sandie_city_council_videos_{view_id}.html"),
        url=f"{SandieCityCouncilSpider.video_base_url}ViewPublisher.php?view_id={view_id}",  # noqa: E501
    )


@pytest.fixture
def spider():
    return SandieCityCouncilSpider()


@pytest.fixture
def parsed_ajax_items(spider):
    """Meetings from the October 2026 calendar, with no videos or documents"""
    with freeze_time("2026-11-05"):
        return list(spider.parse_ajax_calendar(test_ajax_response))


@pytest.fixture
def video_spider():
    """Spider after the City Council and Land Use and Housing Committee archived
    videos pages and the committee documents search have been parsed"""
    spider = SandieCityCouncilSpider()
    for view_id in [3, 12]:
        list(
            spider.parse_videos(
                _videos_response(view_id), view_id=view_id, remaining=[11]
            )
        )
    with freeze_time("2026-11-05"):
        list(spider.parse_documents(documents_response))
    return spider


@pytest.fixture
def parsed_video_items(video_spider):
    with freeze_time("2026-11-05"):
        return list(video_spider.parse_ajax_calendar(test_ajax_response))


@pytest.fixture
def council_spider():
    """Spider after the committee and City Council documents searches have been
    parsed"""
    spider = SandieCityCouncilSpider()
    with freeze_time("2026-11-05"):
        list(spider.parse_documents(documents_response))
        list(spider.parse_documents(council_documents_response))
    return spider


@pytest.fixture
def parsed_council_items(council_spider):
    with freeze_time("2026-11-05"):
        return list(council_spider.parse_ajax_calendar(test_ajax_response))


def _find(items, title, day):
    (item,) = [
        item for item in items if item["title"] == title and item["start"].day == day
    ]
    return item


def _video_links(item):
    return [link["href"] for link in item["links"] if link["title"] == "Video"]


# ============ Request Chain Tests ============


def test_start_requests(spider):
    """Video pages are fetched one at a time before the documents and calendar"""
    requests = list(spider.start_requests())
    assert [request.url for request in requests] == [
        "https://sandiego.granicus.com/ViewPublisher.php?view_id=3"
    ]
    assert requests[0].cb_kwargs["remaining"] == [
        47,
        67,
        24,
        53,
        54,
        64,
        49,
        51,
        12,
        52,
        11,
    ]


def test_parse_videos_next_request(spider):
    requests = list(
        spider.parse_videos(_videos_response(12), view_id=12, remaining=[52, 11])
    )
    assert [request.url for request in requests] == [
        "https://sandiego.granicus.com/ViewPublisher.php?view_id=52"
    ]
    assert requests[0].cb_kwargs["remaining"] == [11]


@freeze_time("2026-11-05")
def test_videos_then_documents_request(spider):
    """After the last videos page comes the committee documents search, over
    Oct 1 2026 through Jan 1 2027, the same months as the calendar"""
    requests = list(spider.parse_videos(_videos_response(12), view_id=11, remaining=[]))
    assert [request.url for request in requests] == [
        f"{spider.documents_url}?dropid=11"
        f"&mtids={spider.documents_mtids.replace(',', '%2C')}"
        "&dropsv=10%2F01%2F2026+00%3A00%3A00&dropev=01%2F01%2F2027+00%3A00%3A00"
    ]


@freeze_time("2026-11-05")
def test_committee_then_council_documents_request(spider):
    requests = list(
        spider._next_documents_requests(
            [(spider.council_documents_url, spider.council_documents_mtids)]
        )
    )
    assert [request.url for request in requests] == [
        f"{spider.council_documents_url}?dropid=11"
        f"&mtids={spider.council_documents_mtids.replace(',', '%2C')}"
        "&dropsv=10%2F01%2F2026+00%3A00%3A00&dropev=01%2F01%2F2027+00%3A00%3A00"
    ]
    assert requests[0].cb_kwargs["remaining"] == []


@freeze_time("2026-11-05")
def test_documents_then_calendar_requests(spider):
    requests = list(spider.parse_documents(documents_response))
    assert len(requests) == 3
    assert all(
        request.callback.__name__ == "parse_ajax_calendar" for request in requests
    )


@freeze_time("2026-11-05")
def test_calendar_requests(spider):
    """1am on Oct 1, Nov 1 and Dec 1 2026 in Los Angeles time"""
    urls = [request.url for request in spider._calendar_requests()]
    assert urls == [
        f"{spider.ajax_url}&calendar_timestamp=1790841600",
        f"{spider.ajax_url}&calendar_timestamp=1793523600",
        f"{spider.ajax_url}&calendar_timestamp=1796115600",
    ]


# ============ Calendar AJAX Tests ============


def test_ajax_count(parsed_ajax_items):
    assert len(parsed_ajax_items) == 33


def test_ajax_only_current_month(parsed_ajax_items):
    """Days from September shown in the October grid are skipped"""
    assert all(item["start"].month == 10 for item in parsed_ajax_items)


def test_ajax_title(parsed_ajax_items):
    assert parsed_ajax_items[8]["title"] == "Adjourned Land Use & Housing Committee"


def test_ajax_start(parsed_ajax_items):
    assert parsed_ajax_items[8]["start"] == datetime(2026, 10, 8, 13, 0)


def test_ajax_defaults(parsed_ajax_items):
    item = parsed_ajax_items[8]
    assert item["description"] == ""
    assert item["end"] is None
    assert item["time_notes"] == ""
    assert item["all_day"] is False


def test_ajax_location(parsed_ajax_items):
    assert parsed_ajax_items[8]["location"] == {
        "name": "San Diego City Administration Center",
        "address": "202 C Street, San Diego",
    }


def test_ajax_status(parsed_ajax_items):
    assert parsed_ajax_items[0]["status"] == PASSED


def test_ajax_status_adjourned(parsed_ajax_items):
    """ "Adjourned" anywhere in the title means the meeting was called off"""
    adjourned = [
        item["title"] for item in parsed_ajax_items if item["status"] == CANCELLED
    ]
    assert adjourned == [
        "Adjourned Economic Development and Intergovernmental Relations Committee",
        "Adjourned Land Use & Housing Committee",
        "Closed Session Adjourned",
        "Housing Authority Adjourned",
        "Public Facilities Financing Authority Adjourned",
    ]


def test_ajax_closed_to_public(parsed_ajax_items):
    """Closed Session meetings are closed to the public"""
    closed = [item["title"] for item in parsed_ajax_items if item["closed_to_public"]]
    assert closed == [
        "Closed Session",
        "Closed Session Adjourned",
        "Closed Session",
        "Closed Session",
    ]


def test_ajax_id(parsed_ajax_items):
    assert (
        parsed_ajax_items[8]["id"]
        == "sandie_city_council/202610081300/x/adjourned_land_use_housing_committee"
    )


def test_ajax_classification(parsed_ajax_items):
    assert parsed_ajax_items[0]["classification"] == CITY_COUNCIL
    assert parsed_ajax_items[1]["classification"] == NOT_CLASSIFIED
    assert parsed_ajax_items[8]["classification"] == COMMITTEE


def test_ajax_source(spider, parsed_ajax_items):
    """Source is the calendar page, not the AJAX URL"""
    assert parsed_ajax_items[8]["source"] == spider.base_url


def test_ajax_links(parsed_ajax_items):
    """The calendar's own links aren't used, so without documents or videos
    every meeting has no links"""
    assert all(item["links"] == [] for item in parsed_ajax_items)


# ============ Body Matching Tests ============


def test_parse_view_id(spider):
    assert spider._parse_view_id("City Council") == 3
    assert spider._parse_view_id("Special City Council") == 3
    assert spider._parse_view_id("Adjourned Land Use & Housing Committee") == 12
    assert (
        spider._parse_view_id(
            "Adjourned Economic Development and Intergovernmental Relations Committee"
        )
        == 49
    )
    assert spider._parse_view_id("Closed Session") is None
    assert spider._parse_view_id("Special Housing Authority") is None


# ============ Video Link Tests ============


def test_video_link_shared_by_same_day_council_meetings(parsed_video_items):
    """City Council at 10am and 2pm on Oct 26 share the regular session clip"""
    council = [
        item
        for item in parsed_video_items
        if item["title"] == "City Council" and item["start"].day == 26
    ]
    assert len(council) == 2
    for item in council:
        assert _video_links(item) == [
            "https://sandiego.granicus.com/MediaPlayer.php?view_id=3&clip_id=9520"
        ]


def test_video_link_special_meeting(parsed_video_items):
    special = _find(parsed_video_items, "Special City Council", 26)
    assert _video_links(special) == [
        "https://sandiego.granicus.com/MediaPlayer.php?view_id=3&clip_id=9519"
    ]


def test_video_link_committee(parsed_video_items):
    special = _find(parsed_video_items, "Special Land Use & Housing Committee", 16)
    assert _video_links(special) == [
        "https://sandiego.granicus.com/MediaPlayer.php?view_id=12&clip_id=9513"
    ]


def test_no_video_link(parsed_video_items):
    """No clip on Oct 8 for Land Use and Housing, and no view_id for Closed
    Session"""
    assert _video_links(parsed_video_items[8]) == []
    assert _video_links(parsed_video_items[1]) == []


def test_no_links(video_spider):
    """No documents and no matching video clip"""
    assert (
        video_spider._parse_links(datetime(2026, 10, 5).date(), "Closed Session") == []
    )


# ============ Committee Document Tests ============


def test_document_links_agenda_and_actions(parsed_video_items):
    item = _find(parsed_video_items, "Special Land Use & Housing Committee", 16)
    assert item["links"] == [
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecomm/Meetings/ViewMeeting?id=7204&doctype=1&site=comm",  # noqa: E501
            "title": "Agenda",
        },
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecomm/Meetings/ViewMeeting?id=7204&doctype=2&site=comm",  # noqa: E501
            "title": "Actions",
        },
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecomm/Meetings/ViewMeeting?id=7216&doctype=1&site=comm",  # noqa: E501
            "title": "Public Comment",
        },
        {
            "href": "https://sandiego.granicus.com/MediaPlayer.php?view_id=12&clip_id=9513",  # noqa: E501
            "title": "Video",
        },
    ]


def test_document_links_public_comment(parsed_video_items):
    item = _find(parsed_video_items, "Public Safety Committee", 14)
    assert {
        "href": "https://sandiego.hylandcloud.com/211agendaonlinecomm/Meetings/ViewMeeting?id=7213&doctype=1&site=comm",  # noqa: E501
        "title": "Public Comment",
    } in item["links"]


def test_document_links_economic_development(parsed_video_items):
    """Search spells it "Economic Development & Intergovernmental Relations", and
    the public comment is listed second on its date, without a visible date"""
    item = _find(
        parsed_video_items,
        "Adjourned Economic Development and Intergovernmental Relations Committee",
        7,
    )
    assert [link["title"] for link in item["links"]] == ["Agenda", "Public Comment"]


def test_no_document_links_for_council_without_council_search(parsed_video_items):
    """Without the City Council search, only the video is left"""
    council = [
        item
        for item in parsed_video_items
        if item["title"] == "City Council" and item["start"].day == 26
    ]
    assert len(council) == 2
    for item in council:
        assert [link["title"] for link in item["links"]] == ["Video"]


# ============ City Council Document Tests ============


def test_council_document_links_agenda_and_summary(parsed_council_items):
    items = [
        item
        for item in parsed_council_items
        if item["title"] == "City Council" and item["start"].day == 19
    ]
    assert items[0]["links"] == [
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7211&doctype=1&site=council",  # noqa: E501
            "title": "Agenda",
        },
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7211&doctype=3&site=council",  # noqa: E501
            "title": "Summary",
        },
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7223&doctype=1&site=council",  # noqa: E501
            "title": "Public Comment",
        },
    ]


def test_council_document_links_shared_by_same_day_meetings(parsed_council_items):
    """The 10am and 2pm sessions on Oct 5 share one agenda"""
    council = [
        item
        for item in parsed_council_items
        if item["title"] == "City Council" and item["start"].day == 5
    ]
    assert len(council) == 2
    assert council[0]["links"] == council[1]["links"]


def test_council_document_links_housing_authority(parsed_council_items):
    """ "Housing Authority City Council" documents go to the Housing Authority,
    not to the City Council meetings on the same day"""
    item = _find(parsed_council_items, "Housing Authority Adjourned", 13)
    assert [link["href"] for link in item["links"]] == [
        "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7210&doctype=1&site=council",  # noqa: E501
    ]
    for council in parsed_council_items:
        if council["title"] == "City Council" and council["start"].day == 13:
            assert "id=7210" not in str(council["links"])


def test_council_document_links_closed_session(parsed_council_items):
    item = _find(parsed_council_items, "Closed Session", 5)
    assert [link["title"] for link in item["links"]] == ["Agenda"]


def test_council_document_links_public_comment(parsed_council_items):
    items = [
        item
        for item in parsed_council_items
        if item["title"] == "City Council" and item["start"].day == 12
    ]
    assert [link["title"] for link in items[0]["links"]] == [
        "Public Comment",
        "Agenda",
        "Summary",
    ]


def test_council_document_links_special_meeting(parsed_council_items):
    """Documents with "special" in the title go to the special meeting only"""
    special = _find(parsed_council_items, "Special City Council", 26)
    assert [link["href"] for link in special["links"]] == [
        "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7238&doctype=1&site=council",  # noqa: E501
        "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7237&doctype=1&site=council",  # noqa: E501
        "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7237&doctype=3&site=council",  # noqa: E501
    ]
    for regular in parsed_council_items:
        if regular["title"] == "City Council" and regular["start"].day == 26:
            assert [link["href"] for link in regular["links"]] == [
                "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7218&doctype=1&site=council",  # noqa: E501
                "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7218&doctype=3&site=council",  # noqa: E501
                "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/ViewMeeting?id=7239&doctype=1&site=council",  # noqa: E501
            ]


# ============ Warning Tests ============


def _calendar_html(day_html):
    return f"""<table class="calendar-view-table calendar-view-month"><tbody><tr>
        <td class="current-month">{day_html}</td>
    </tr></tbody></table>"""


def _day(events_html, date="2026-10-05T12:00:00Z"):
    return (
        f'<time class="calendar-view-day__number" datetime="{date}">5</time>'
        f"<ul>{events_html}</ul>"
    )


def test_meeting_without_start_time_is_skipped(spider, caplog):
    """A meeting with no time is skipped with a warning; the rest of the day is
    still parsed"""
    html = _calendar_html(
        _day(
            '<li><a href="/a">City Council</a></li>'
            '<li><a href="/b">Rules Committee</a>'
            '<span class="fine-print">9:00 am</span></li>'
        )
    )
    with freeze_time("2026-11-05"):
        items = list(spider._parse_calendar(Selector(text=html), spider.base_url))
    assert [item["title"] for item in items] == ["Rules Committee"]
    assert "no start time: City Council on 2026-10-05" in caplog.text


def test_meeting_without_title_is_skipped(spider, caplog):
    html = _calendar_html(_day('<li><span class="fine-print">9:00 am</span></li>'))
    assert list(spider._parse_calendar(Selector(text=html), spider.base_url)) == []
    assert "no title on 2026-10-05" in caplog.text


def test_day_without_date_is_skipped(spider, caplog):
    html = _calendar_html(
        _day(
            '<li><a href="/a">City Council</a>'
            '<span class="fine-print">10:00 am</span></li>',
            date="",
        )
    )
    assert list(spider._parse_calendar(Selector(text=html), spider.base_url)) == []
    assert "Skipping 1 meeting(s) on a day with no date" in caplog.text


def test_ajax_response_not_json(spider, caplog):
    response = HtmlResponse(
        url=test_ajax_response.url, body=b"<textarea>[]</textarea>", encoding="utf-8"
    )
    assert list(spider.parse_ajax_calendar(response)) == []
    assert "Calendar response is not JSON" in caplog.text


def test_ajax_response_without_calendar(spider, caplog):
    response = TextResponse(
        url=test_ajax_response.url, body=b'[{"command": "settings"}]', encoding="utf-8"
    )
    assert list(spider.parse_ajax_calendar(response)) == []
    assert "No calendar found in response" in caplog.text


@freeze_time("2026-11-05")
def test_documents_page_without_documents(spider, caplog):
    """An empty search still moves on to the calendar requests"""
    response = HtmlResponse(
        url=spider.documents_url, body=b"<html></html>", encoding="utf-8"
    )
    requests = list(spider.parse_documents(response))
    assert len(requests) == 3
    assert "No documents found" in caplog.text


@freeze_time("2026-11-05")
def test_document_for_unknown_body(spider, caplog):
    response = HtmlResponse(
        url=spider.documents_url,
        body=b"""<div id="meetings-list">
            <a href="/x" title="View Agenda for New Committee on 10/5/2026 9:00:00 AM">
            Agenda</a>
            <a href="/y" title="View Agenda for Rules Committee">Agenda</a>
        </div>""",
        encoding="utf-8",
    )
    list(spider.parse_documents(response))
    assert spider.document_links == {}
    assert "unknown body: View Agenda for New Committee" in caplog.text
    assert "no date: View Agenda for Rules Committee" in caplog.text


def test_videos_page_without_videos(spider, caplog):
    response = HtmlResponse(
        url=f"{spider.video_base_url}ViewPublisher.php?view_id=3",
        body=b"<html></html>",
        encoding="utf-8",
    )
    list(spider.parse_videos(response, view_id=3, remaining=[11]))
    assert spider.video_links == {}
    assert "No videos found" in caplog.text
