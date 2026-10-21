import logging
import re
from datetime import datetime
from os.path import dirname, exists, join

import pytest
import scrapy
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CANCELLED,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy.http import HtmlResponse
from twisted.python.failure import Failure

from city_scrapers.spiders.sandie_encinitas import (
    SandieEncinitasBoardsCommissionsSpider,
    SandieEncinitasCouncilCommitteesSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "sandie_encinitas.html"),
    url="https://encinitas.granicus.com/ViewPublisher.php?view_id=7",
)

council_spider = SandieEncinitasCouncilCommitteesSpider()
boards_spider = SandieEncinitasBoardsCommissionsSpider()


def agenda_response(query):
    """
    Saved agenda pages for a generated agenda ("clip_id=3932") and a custom
    agenda ("event_id=5564"). Every other agenda is treated as an agenda that is
    only available as a PDF, whose generated page is empty.
    """
    url = boards_spider.agenda_url.format(query)
    name = query.replace("_id=", "_")
    path = join(dirname(__file__), "files", f"sandie_encinitas_agenda_{name}.html")
    if exists(path):
        return file_response(path, url=url)
    return HtmlResponse(url=url, body=b"<html><body></body></html>")


def run_spider(spider):
    """Parse the listing, then the agenda requests"""
    items = []
    for result in spider.parse(test_response):
        if isinstance(result, scrapy.Request):
            response = agenda_response(result.url.split("&")[-1])
            items.extend(result.callback(response, **result.cb_kwargs))
        else:
            items.append(result)
    return items


@pytest.fixture(scope="module")
def council_items():
    with freeze_time("2026-10-21"):
        return run_spider(council_spider)


@pytest.fixture(scope="module")
def boards_items():
    with freeze_time("2026-10-21"):
        return run_spider(boards_spider)


def get_item(items, start, title=None):
    matches = [
        item
        for item in items
        if item["start"] == start and (title is None or item["title"] == title)
    ]
    assert len(matches) == 1
    return matches[0]


# --- shared behavior ---


def test_count(council_items, boards_items):
    assert len(council_items) == 50
    assert len(boards_items) == 58


def test_unique_ids(council_items, boards_items):
    for items in (council_items, boards_items):
        ids = [item["id"] for item in items]
        assert len(ids) == len(set(ids))


def test_rolling_window(council_items, boards_items):
    # The fixture includes archived meetings from September 2024, which are
    # older than the two year window
    cutoff = datetime(2024, 10, 20)
    for item in council_items + boards_items:
        assert item["start"] >= cutoff
    assert min(item["start"] for item in council_items) == datetime(
        2024, 10, 23, 17, 30
    )
    assert min(item["start"] for item in boards_items) == datetime(2024, 10, 21)


def test_rolling_window_uses_local_time():
    # At 5am UTC it's still 10pm on October 20 in San Diego, so the cutoff is
    # 2024-10-20 22:00 and the 2024-10-21 meeting is in the window
    with freeze_time("2026-10-21 05:00:00"):
        items = run_spider(boards_spider)
    assert min(item["start"] for item in items) == datetime(2024, 10, 21)


def test_agency():
    assert council_spider.agency == "City of Encinitas- City Council Committees"
    assert boards_spider.agency == "City of Encinitas- Boards & Commissions"


def test_source(council_items, boards_items):
    for item in council_items + boards_items:
        assert (
            item["source"] == "https://www.encinitasca.gov/government/agendas-webcasts"
        )


def test_common_fields(council_items, boards_items):
    for item in council_items + boards_items:
        assert item["description"] == ""
        assert item["end"] is None
        assert item["all_day"] is False
        assert item["time_notes"] == council_spider.time_notes


def test_status(council_items, boards_items):
    for item in council_items + boards_items:
        if item["status"] == CANCELLED:
            continue
        expected = TENTATIVE if item["start"] >= datetime(2026, 10, 21) else PASSED
        assert item["status"] == expected


def test_titles_cleaned(council_items, boards_items):
    for item in council_items + boards_items:
        title = item["title"].lower()
        assert "p.m." not in title
        assert "a.m." not in title
        assert "amended" not in title
        assert "added" not in title
        assert "cancel" not in title
        assert item["title"] == item["title"].strip(" -")


def test_links(council_items, boards_items):
    for item in council_items + boards_items:
        for link in item["links"]:
            assert link["href"].startswith("https://")
            assert link["title"]


# --- City Council Committees ---


def test_council_upcoming_closed_session(council_items):
    item = get_item(council_items, datetime(2026, 10, 21, 15, 30))
    assert item["title"] == "Special City Council Meeting - Closed Session"
    assert item["closed_to_public"] is True
    assert item["classification"] == CITY_COUNCIL
    assert item["status"] == TENTATIVE
    assert item["location"] == {
        "name": "Encinitas City Hall, Council Chambers",
        "address": "505 S. Vulcan Avenue, Encinitas, CA 92024",
    }
    assert item["links"] == [
        {
            "href": "https://encinitas.granicus.com/AgendaViewer.php?view_id=7&event_id=5765",  # noqa
            "title": "Agenda",
        }
    ]


def test_council_upcoming_cancelled(council_items):
    item = get_item(council_items, datetime(2026, 11, 11, 18, 0))
    assert item["title"] == "Regular City Council Meeting"
    assert item["status"] == CANCELLED
    assert item["closed_to_public"] is False
    assert item["links"] == []


def test_council_upcoming_duplicates_merged(council_items):
    # "Cultural Tourism Committee Meeting - 9:00 a.m." is listed twice
    item = get_item(council_items, datetime(2026, 11, 5, 9, 0))
    assert item["title"] == "Cultural Tourism Committee Meeting"
    assert item["classification"] == COMMITTEE
    assert item["location"] == {
        "name": "Encinitas City Hall",
        "address": "505 S. Vulcan Avenue, Encinitas, CA 92024",
    }


def test_council_archived_time_from_title(council_items):
    # "Special City Council Meeting - FY 2026-2027 Annual Workplan Q1 Update 4:00 p.m."
    item = get_item(council_items, datetime(2026, 10, 14, 16, 0))
    assert (
        item["title"]
        == "Special City Council Meeting - FY 2026-2027 Annual Workplan Q1 Update"
    )
    assert item["status"] == PASSED
    assert item["closed_to_public"] is False
    assert item["links"] == [
        {
            "href": "https://encinitas.granicus.com/AgendaViewer.php?view_id=7&clip_id=3946",  # noqa
            "title": "Agenda",
        },
        {
            "href": "https://encinitas.granicus.com/MediaPlayer.php?view_id=7&clip_id=3946",  # noqa
            "title": "Video",
        },
        {
            "href": "https://archive-video.granicus.com/encinitas/encinitas_b4f092ea-c360-4118-a677-3fd466561e82.mp3",  # noqa
            "title": "MP3 Audio",
        },
    ]


def test_council_archived_amendment_notes(council_items):
    # "Regular City Council Meeting 6:00 p.m. AMENDED to remove Item 12B"
    item = get_item(council_items, datetime(2026, 9, 23, 18, 0))
    assert item["title"] == "Regular City Council Meeting"
    # "AMENDED Special City Council Meeting - Closed Session 5:00 p.m. Item #3 Added"
    item = get_item(council_items, datetime(2026, 9, 2, 17, 0))
    assert item["title"] == "Special City Council Meeting - Closed Session"
    assert item["closed_to_public"] is True
    # "AMENDED (Item #2 Added) Special City Council - Closed Session Meeting 3:00 p.m."
    item = get_item(council_items, datetime(2024, 11, 20, 15, 0))
    assert item["title"] == "Special City Council - Closed Session Meeting"
    assert item["closed_to_public"] is True


def test_council_archived_without_time(council_items):
    # The agenda is only available as a PDF, so the time can't be recovered
    item = get_item(council_items, datetime(2026, 9, 29), "Skate Feature Committee")
    assert item["classification"] == COMMITTEE
    assert item["location"]["name"] == "Encinitas City Hall"
    # The agenda isn't published
    item = get_item(council_items, datetime(2024, 11, 7), "Cultural Tourism Committee")
    assert item["status"] == PASSED


def test_council_excluded_meetings(council_items):
    titles = [item["title"] for item in council_items]
    assert all(
        "City Council" in title
        or "Cultural Tourism Committee" in title
        or "School District Liaison Committee" in title
        or "Skate Feature Committee" in title
        for title in titles
    )
    # Housing Authority, San Dieguito Water District and Zoning Administrative
    # Hearing meetings belong to other agencies
    assert not any("Housing Authority" in title for title in titles)
    assert not any(title.startswith("Regular San Dieguito") for title in titles)


# --- Boards & Commissions ---


def test_boards_upcoming(boards_items):
    item = get_item(boards_items, datetime(2026, 10, 22, 17, 30))
    assert item["title"] == "Urban Forest Advisory Committee"
    assert item["classification"] == ADVISORY_COMMITTEE
    assert item["status"] == TENTATIVE
    assert item["closed_to_public"] is False
    assert item["location"] == {
        "name": "Encinitas City Hall, Council Chambers",
        "address": "505 S. Vulcan Avenue, Encinitas, CA 92024",
    }


def test_archived_listing_prioritized(boards_items):
    # Listed in both the upcoming (2:00 PM) and archived (no time) sections
    items = [
        item
        for item in boards_items
        if item["title"] == "Senior Citizen Commission Regular Meeting"
        and item["start"].date() == datetime(2026, 10, 20).date()
    ]
    assert len(items) == 1
    # The archived meeting has no time in its title, and its agenda isn't saved
    assert items[0]["start"] == datetime(2026, 10, 20)
    assert items[0]["status"] == PASSED
    assert [link["title"] for link in items[0]["links"]] == [
        "Agenda",
        "Video",
        "MP3 Audio",
    ]
    assert "clip_id=3963" in items[0]["links"][0]["href"]


def agenda_clip_ids(item):
    return [
        link["href"].split("clip_id=")[1]
        for link in item["links"]
        if link["title"] == "Agenda" and "clip_id=" in link["href"]
    ]


def test_own_panel_prioritized(boards_items):
    # Listed in the "Urban Forest Advisory Committee" panel (clip 3549) and the
    # "Committees, Subcommittees, and Task Forces" panel (clip 3547)
    items = [
        item
        for item in boards_items
        if item["start"].date() == datetime(2025, 7, 24).date()
    ]
    assert len(items) == 1
    assert items[0]["title"] == "Urban Forest Advisory Committee"
    assert agenda_clip_ids(items[0]) == ["3549"]


def test_joint_meeting_other_panel_ignored():
    # Joint City Council and SDWD meetings are listed in both the "City Council"
    # (clip 3306) and "SDWD" (clip 3313) panels
    spider = SandieEncinitasCouncilCommitteesSpider()
    spider.lookback_days = 365 * 3
    with freeze_time("2026-10-21"):
        items = run_spider(spider)
    items = [
        item
        for item in items
        if item["start"].date() == datetime(2024, 9, 18).date()
        and "SDWD" in item["title"]
    ]
    assert len(items) == 1
    assert items[0]["title"] == "Special City Council & SDWD - Closed Session Meetings"
    assert agenda_clip_ids(items[0]) == ["3306"]


def test_in_progress(boards_items):
    # The date column shows an "In Progress" video link, but the row still has
    # its date in the data-eventDate attribute, so the agenda isn't needed
    item = get_item(boards_items, datetime(2026, 10, 20, 17, 30))
    assert item["title"] == "Parks and Recreation Commission Regular Meeting"
    assert item["status"] == PASSED
    assert item["links"] == [
        {
            "href": "https://encinitas.granicus.com/MediaPlayer.php?view_id=7&event_id=5564",  # noqa
            "title": "Video",
        },
        {
            "href": "https://encinitas.granicus.com/AgendaViewer.php?view_id=7&event_id=5564",  # noqa
            "title": "Agenda",
        },
    ]
    with freeze_time("2026-10-21"):
        requests = [
            result
            for result in boards_spider.parse(test_response)
            if isinstance(result, scrapy.Request)
        ]
    assert not any("event_id=" in request.url for request in requests)


def without_listed_date_response():
    """The listing with the date removed from the in progress meeting's row"""
    body = re.sub(
        rb'(upcoming-date--running" data-label="Date:") data-eventdate="[^"]*"',
        rb"\1",
        test_response.body,
    )
    assert body != test_response.body
    return HtmlResponse(url=test_response.url, body=body, encoding="utf-8")


def test_upcoming_without_listed_date():
    # The date and time come from the agenda: "Tuesday, October 20, 2026 5:30 p.m."
    with freeze_time("2026-10-21"):
        results = list(boards_spider.parse(without_listed_date_response()))
    requests = [r for r in results if isinstance(r, scrapy.Request)]
    event_requests = [r for r in requests if "event_id=" in r.url]
    assert [r.url for r in event_requests] == [
        boards_spider.agenda_url.format("event_id=5564")
    ]
    request = event_requests[0]
    with freeze_time("2026-10-21"):
        items = list(
            request.callback(agenda_response("event_id=5564"), **request.cb_kwargs)
        )
    assert [item["start"] for item in items] == [datetime(2026, 10, 20, 17, 30)]
    assert items[0]["title"] == "Parks and Recreation Commission Regular Meeting"


def test_upcoming_without_any_date(caplog):
    # The agenda is a PDF, so there's no date to use
    with freeze_time("2026-10-21"):
        results = list(boards_spider.parse(without_listed_date_response()))
    request = next(
        r for r in results if isinstance(r, scrapy.Request) and "event_id=" in r.url
    )
    with caplog.at_level(logging.WARNING):
        items = list(
            request.callback(agenda_response("event_id=1"), **request.cb_kwargs)
        )
    assert items == []
    assert "Skipping upcoming meeting" in caplog.text


def test_boards_cancelled_golf_authority(boards_items):
    item = get_item(boards_items, datetime(2026, 10, 27, 16, 30))
    assert item["title"] == "Encinitas Ranch Golf Authority"
    assert item["classification"] == BOARD
    assert item["status"] == CANCELLED
    assert item["location"] == {
        "name": "Encinitas Ranch Golf Course Clubhouse",
        "address": "1275 Quail Gardens Drive, Encinitas, CA 92024",
    }


def test_boards_archived_amendment_notes(boards_items):
    # "AMENDED Parks and Recreation Commission Regular Meeting (Item 8A updated)"
    titles = [
        item["title"] for item in boards_items if item["start"] == datetime(2026, 8, 18)
    ]
    assert sorted(titles) == [
        "Parks and Recreation Commission Regular Meeting",
        "Senior Citizen Commission Regular Meeting",
    ]
    item = get_item(
        boards_items, datetime(2026, 9, 2), "Youth Commission Special Meeting"
    )
    assert item["status"] == PASSED


def test_boards_excludes_other_agencies(boards_items):
    titles = [item["title"] for item in boards_items]
    # Joint meetings with the City Council are scraped by the council spider
    assert not any("City Council" in title for title in titles)
    assert not any("Business Commission" in title for title in titles)
    assert not any("Zoning" in title for title in titles)
    assert not any("San Dieguito" in title for title in titles)


def test_boards_bodies(boards_items):
    titles = " ".join(item["title"] for item in boards_items)
    for body in [
        "Planning Commission",
        "Environmental Commission",
        "Youth Commission",
        "Commission for the Arts",
        "Public Health and Safety Commission",
        "Parks and Recreation Commission",
        "Encinitas Ranch Golf Authority",
        "Urban Forest Advisory Committee",
        "Senior Citizen Commission",
        "Mobility and Traffic Safety Commission",
        "Affordable Housing Task Force",
    ]:
        assert body in titles


# --- Start times from agendas ---


def test_agenda_generated_time(boards_items):
    # Header of the generated agenda: "OCTOBER 1, 2026 - 06:00 PM"
    item = get_item(boards_items, datetime(2026, 10, 1, 18, 0))
    assert item["title"] == "Planning Commission"
    assert item["id"] == (
        "sandie_encinitas_boards_commissions/202610011800/x/planning_commission"
    )
    assert item["status"] == PASSED


def agenda_meeting(start, status=PASSED):
    """An archived meeting without a time in its title"""
    return Meeting(
        title="Planning Commission",
        description="",
        classification=COMMISSION,
        start=start,
        end=None,
        all_day=False,
        closed_to_public=False,
        time_notes="",
        location=boards_spider.default_location,
        links=[],
        source=boards_spider.base_url,
        status=status,
        id="",
    )


def parse_agenda(response, start, status=PASSED):
    with freeze_time("2026-10-21"):
        meeting = agenda_meeting(start, status=status)
        return list(boards_spider._parse_agenda(response, meeting))[0]


def test_agenda_custom_html_time():
    # Agendas that aren't generated by Granicus use their own format:
    # "Tuesday, October 20, 2026 5:30 p.m."
    item = parse_agenda(agenda_response("event_id=5564"), datetime(2026, 10, 20))
    assert item["start"] == datetime(2026, 10, 20, 17, 30)


def test_agenda_other_date_ignored():
    # The agenda is for October 1, not October 2
    item = parse_agenda(agenda_response("clip_id=3932"), datetime(2026, 10, 2))
    assert item["start"] == datetime(2026, 10, 2)


def test_agenda_stub_ignored():
    # Meetings with PDF agendas have a generated agenda with only a header,
    # whose time and location are defaults (the actual agenda says "4:30 p.m.")
    response = HtmlResponse(
        url=boards_spider.agenda_url.format("clip_id=3899"),
        body=b"""
        <div>City of Encinitas<br/><br/>Encinitas Ranch Golf Authority<br/><br/>
        AGENDA</div><hr/>
        <div><span style="font-size: 14pt">AUGUST 25, 2026 - 11:30 AM</span><br/>
        City of Encinitas - Council Chambers<br/>505 S. Vulcan Ave<br/>
        Encinitas, California 92024</div>
        <div><strong>Each speaker is allowed three (3) minutes to address the
        Commission.</strong></div>
        """,
    )
    item = parse_agenda(response, datetime(2026, 8, 25))
    assert item["start"] == datetime(2026, 8, 25)


def test_agenda_implausible_time_ignored():
    # e.g. a Parks and Recreation Commission agenda for "JUNE 16, 2026 - 11:30 PM"
    response = agenda_response("clip_id=3932")
    body = response.body.replace(b"06:00 PM", b"11:30 PM")
    assert body != response.body
    item = parse_agenda(response.replace(body=body), datetime(2026, 10, 1))
    assert item["start"] == datetime(2026, 10, 1)


def test_agenda_keeps_cancelled_status():
    item = parse_agenda(
        agenda_response("clip_id=3932"), datetime(2026, 10, 1), status=CANCELLED
    )
    assert item["start"] == datetime(2026, 10, 1, 18, 0)
    assert item["status"] == CANCELLED


def test_agenda_error_logged(caplog):
    meeting = Meeting(title="Planning Commission", start=datetime(2026, 10, 1))
    failure = Failure(ConnectionError("Connection refused"))
    failure.request = scrapy.Request(
        boards_spider.agenda_url.format("clip_id=3932"),
        callback=boards_spider._parse_agenda,
        cb_kwargs={"meeting": meeting},
    )
    with caplog.at_level(logging.WARNING):
        items = list(boards_spider._handle_agenda_error(failure))
    assert items == [meeting]
    assert "Failed to fetch agenda" in caplog.text


def test_invalid_date_logged(caplog):
    with caplog.at_level(logging.WARNING):
        assert boards_spider._parse_start("Not a date", "6:00 p.m.") is None
    assert "Failed to parse start" in caplog.text
