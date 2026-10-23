import logging
from datetime import date, datetime
from os.path import dirname, join
from unittest.mock import MagicMock, patch

import pytest
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CANCELLED,
    CITY_COUNCIL,
    COMMISSION,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy.http import HtmlResponse

from city_scrapers.mixins import sandie_carlsbad as mixin
from city_scrapers.spiders.sandie_carlsbad import (
    SandieCarlsbadBoardsCommissionsSpider,
    SandieCarlsbadCouncilCommitteesSpider,
)

FILES = join(dirname(__file__), "files")
CALENDAR_URL = "https://www.carlsbadca.gov/departments/calendar/-curm-{m}/-cury-{y}/-seldept-16"  # noqa
AGENDAS_URL = "https://www.carlsbadca.gov/city-hall/meetings-agendas"
LASERFICHE = "https://records.carlsbadca.gov/WebLink/ElectronicFile.aspx?docid={}&dbid=0&repo=CityOfCarlsbad"  # noqa
CHAMBER = {
    "name": "City Council Chamber",
    "address": "1200 Carlsbad Village Drive, Carlsbad, CA 92008",
}


def _html(url, body):
    return HtmlResponse(url=url, body=body.encode(), encoding="utf-8")


def _calendar_day(label, events):
    """One calendar cell in the live markup: events are (time, title, id)."""
    items = "".join(
        f'<div class="calendar_item"><span class="calendar_eventtime">{t}</span>'
        f'<a class="calendar_eventlink" href="/Home/Components/Calendar/Event/'
        f'{event_id}/17?curm=10&amp;cury=2025&amp;seldept=16" title="{title}">'
        f"{title}</a></div>"
        for t, title, event_id in events
    )
    return (
        f'<td class="calendar_day calendar_day_with_items" aria-label="Scheduled '
        f'events, {label}"><span class="calendar_day_value">1</span>'
        f'<div class="calendar_items">{items}</div></td>'
    )


def _calendar(*days):
    return f"<html><body><table><tr>{''.join(days)}</tr></table></body></html>"


def _folder_links(folders):
    return "".join(
        f'<li><span class="doc_folder_img default"></span><a class="content_link" '
        f'title="Click to open {title} folder" '
        f'href="/city-hall/meetings-agendas/-folder-{fid}">{title}</a></li>'
        for title, fid in folders
    )


def _folder_list(*folders):
    """A board page's document widget in the live markup: folders are (title,
    folder id)."""
    return (
        '<html><body><div class="document_widget content_area"><ul>'
        f"{_folder_links(folders)}</ul></div></body></html>"
    )


def _folder_page(*docs, subfolders=()):
    """A document folder in the live markup: a breadcrumb that links to the
    folder itself, subfolders and documents (title, document id)."""
    items = "".join(
        f'<li><img class="thumb_img" alt="application/pdf" src="/pdf.png">'
        f'<a class="content_link" target="_blank" '
        f'href="/home/showpublisheddocument/{did}/639269703204630000">{title}</a></li>'
        for title, did in docs
    )
    return (
        '<html><body><div class="document_widget content_area">'
        '<div class="document_breadcrumb"><a class="content_link" '
        'href="/city-hall/meetings-agendas/-folder-314">Meeting agendas and '
        'materials</a> » <a class="content_link" href="/city-hall/meetings-agendas/'
        '-folder-1">This folder</a></div>'
        f"<ul>{_folder_links(subfolders)}{items}</ul></div></body></html>"
    )


def _document(did, title):
    href = f"https://www.carlsbadca.gov/home/showpublisheddocument/{did}/639269703204630000"  # noqa
    return {"href": href, "title": title}


def _swagit_page(*rows, next_page=None):
    """A Swagit archive tab in the live markup: rows are (title, date, video
    id); next_page adds the pagination's "Next" link."""
    items = "".join(
        f'<tr><td><a target="_blank" href="/videos/{vid}">{title}</a></td>'
        f"<td nowrap>\n  {day}\n</td><td>01h 10m</td></tr>"
        for title, day, vid in rows
    )
    pagination = (
        f'<li class="next"><a rel="next" href="?page={next_page}">Next</a></li>'
        if next_page
        else '<li class="next disabled"><span>Next</span></li>'
    )
    return (
        '<html><body><table class="table videos" id="video-table"><thead><tr>'
        f"<th>Video</th><th>Date</th><th>Duration</th></tr></thead><tbody>{items}"
        f'</tbody></table><ul class="pagination">{pagination}</ul></body></html>'
    )


def _video(vid):
    return {
        "href": f"https://carlsbadca.new.swagit.com/videos/{vid}",
        "title": "Meeting Video",
    }


def _laserfiche_doc(entry_id, name):
    return {"name": name, "entryId": entry_id, "type": -2, "isEdoc": True}


def _laserfiche_folder(entry_id, name):
    return {"name": name, "entryId": entry_id, "type": 0, "isEdoc": False}


def _meeting(title, start, status=PASSED, closed=False, links=()):
    return {
        "title": title,
        "start": start,
        "status": status,
        "closed_to_public": closed,
        "links": list(links),
    }


def _by_start(items, start):
    return next(item for item in items if item["start"] == start)


# The live calendar for October 2026 (department "City Hall"), saved
# 2026-10-19 (the page marks Oct. 19 as today). Frozen at that date so it has
# past, cancelled and upcoming meetings.
@pytest.fixture(scope="module")
def boards_items():
    response = file_response(
        join(FILES, "sandie_carlsbad_boards_commissions.html"),
        url=CALENDAR_URL.format(m=10, y=2026),
    )
    with freeze_time("2026-10-19 12:00"):
        return list(SandieCarlsbadBoardsCommissionsSpider().parse(response))


# The live calendar for October 2025, saved 2026-10-19: both City Council
# meetings that month were closed sessions.
@pytest.fixture(scope="module")
def council_items():
    response = file_response(
        join(FILES, "sandie_carlsbad_council_committees.html"),
        url=CALENDAR_URL.format(m=10, y=2025),
    )
    with freeze_time("2026-10-19 12:00"):
        return list(SandieCarlsbadCouncilCommitteesSpider().parse(response))


# A whole run with the network mocked: October 2025 comes from the saved
# calendar, every other month is an empty calendar. The board page has
# folders for both Oct. 7 meetings (a 3:45 p.m. closed session and a 5 p.m.
# regular meeting that isn't on the calendar); Oct. 21 is only in Laserfiche,
# which has a closed session and a regular session that day. Swagit has the
# Oct. 21 regular meeting and the closed session's open part ("Special
# Meeting").
@pytest.fixture(scope="module")
def crawl():
    october = file_response(
        join(FILES, "sandie_carlsbad_council_committees.html"),
        url=CALENDAR_URL.format(m=10, y=2025),
    ).body.decode()
    pages = {
        CALENDAR_URL.format(m=10, y=2025): october,
        AGENDAS_URL: _folder_list(
            (
                "Oct. 7, 2025, 3:45 p.m. City Council Chamber - Special Meeting - "
                "Closed Session",
                1001,
            ),
            ("Oct. 7, 2025, 5 p.m. City Council Chamber - Regular Meeting", 1002),
        ),
        f"{AGENDAS_URL}/-folder-1001": _folder_page(
            ("10-07-2025 Closed Session Agenda", 11)
        ),
        f"{AGENDAS_URL}/-folder-1002": _folder_page(
            ("10-07-2025 Regular Meeting Agenda", 12)
        ),
    }
    empty_month = _calendar(
        '<td class="calendar_day" aria-label="Scheduled events, Monday, May 4, '
        '2026"></td>'
    )
    # Meeting Packets (9016814): a year folder, then a folder per meeting
    laserfiche = {
        9016814: [_laserfiche_folder(2025, "2025"), _laserfiche_folder(2024, "2024")],
        2025: [
            _laserfiche_folder(907, "2025-10-07; City Council; Closed Session"),
            _laserfiche_folder(921, "2025-10-21; City Council; Closed Session"),
            _laserfiche_folder(922, "2025-10-21; City Council; Regular Session"),
            _laserfiche_folder(1104, "2025-11-04; City Council; Regular Session"),
        ],
        907: [
            _laserfiche_doc(71, "2025-10-07; City Council; Agendas; Closed Session"),
            _laserfiche_doc(72, "2025-10-07; City Council; Minutes; Closed Session"),
        ],
        921: [
            _laserfiche_doc(21, "2025-10-21; City Council; Agendas; Closed Session"),
            _laserfiche_doc(
                23, "2025-10-21; City Council; CS01; Conference with Legal Counsel"
            ),
            _laserfiche_doc(24, "2025-10-21; City Council; Minutes; Closed Session"),
        ],
        922: [
            _laserfiche_doc(22, "2025-10-21; City Council; Agendas; Regular Session"),
        ],
    }
    swagit = _swagit_page(
        ("City Council Meeting", "Oct 21, 2025", 501),
        ("City Council Special Meeting", "Oct 21, 2025", 502),
    )
    spider = SandieCarlsbadCouncilCommitteesSpider()
    fetched, listed, videos = [], [], []

    def fake_get(url, referer=None):
        fetched.append(url)
        return _html(url, pages.get(url, empty_month))

    def fake_entries(folder_id):
        listed.append(folder_id)
        return laserfiche.get(folder_id, [])

    def fake_swagit(url):
        videos.append(url)
        return _html(url, swagit)

    with freeze_time("2026-10-01 12:00"), patch.object(
        spider, "_akamai_get", side_effect=fake_get
    ), patch.object(
        spider, "_laserfiche_entries", side_effect=fake_entries
    ), patch.object(
        spider, "_swagit_get", side_effect=fake_swagit
    ):
        items = list(spider._run_crawl(None))
    return {"items": items, "fetched": fetched, "listed": listed, "videos": videos}


# ============ Configuration ============


def test_spider_configuration():
    boards = SandieCarlsbadBoardsCommissionsSpider
    council = SandieCarlsbadCouncilCommitteesSpider
    assert boards.name == "sandie_carlsbad_boards_commissions"
    assert boards.agency == "City of Carlsbad- Boards & Commissions"
    assert council.name == "sandie_carlsbad_council_committees"
    assert council.agency == "City of Carlsbad- City Council Committees"
    assert [(b["title"], b["classification"]) for b in boards.boards] == [
        (
            "Agricultural Conversion Mitigation Fee Citizens Advisory Committee",
            ADVISORY_COMMITTEE,
        ),
        ("Arts Commission", COMMISSION),
        ("Community-Police Engagement Commission", COMMISSION),
        ("Environmental Sustainability Commission", COMMISSION),
        ("Historic Preservation Commission", COMMISSION),
        ("Housing Commission", COMMISSION),
        ("Investment Review Board", BOARD),
        ("Library Board of Trustees", BOARD),
        ("Parks & Recreation Commission", COMMISSION),
        ("Planning Commission", COMMISSION),
        ("Senior Commission", COMMISSION),
        ("Traffic Safety & Mobility Commission", COMMISSION),
    ]
    assert [(b["title"], b["classification"]) for b in council.boards] == [
        ("City Council", CITY_COUNCIL)
    ]
    # The Jira ticket's is_main agency, read by the Airtable slug sync workflow
    assert boards.is_main is True
    assert not getattr(council, "is_main", False)


def test_start_requests_does_not_touch_the_site(caplog):
    """caplog is pytest's built-in fixture that records log messages emitted
    during the test. The only Scrapy request is a data: URL, and its errback
    must log a warning so a failed run doesn't look clean."""
    spider = SandieCarlsbadCouncilCommitteesSpider()
    request = next(spider.start_requests())
    assert request.url == "data:,"
    with caplog.at_level(logging.WARNING):
        request.errback(MagicMock(getErrorMessage=MagicMock(return_value="boom")))
    assert "Request failed: boom" in caplog.text


def test_calendar_months_cover_two_years_back_and_twelve_ahead():
    with freeze_time("2026-10-19 12:00"):
        spider = SandieCarlsbadCouncilCommitteesSpider()
        months = list(spider._calendar_months())
        assert spider._start_cutoff() == datetime(2024, 10, 19)
    assert months[0] == (2024, 10)
    assert months[-1] == (2027, 10)
    assert len(months) == 37


def test_start_cutoff_on_leap_day():
    with freeze_time("2028-02-29 12:00"):
        cutoff = SandieCarlsbadCouncilCommitteesSpider()._start_cutoff()
    assert cutoff == datetime(2026, 2, 28)


# ============ Calendar ============


def test_boards_meetings(boards_items):
    """Only the ticket's boards: the page's City/Schools, Legislative and
    Economic Development committees, holiday and library events are skipped."""
    assert [
        (item["start"], item["title"], item["status"], item["classification"])
        for item in boards_items
    ] == [
        (datetime(2026, 10, 1, 17, 30), "Arts Commission", PASSED, COMMISSION),
        (
            datetime(2026, 10, 5, 16, 0),
            "Traffic Safety & Mobility Commission Meeting",
            CANCELLED,
            COMMISSION,
        ),
        (
            datetime(2026, 10, 19, 17, 30),
            "Parks & Recreation Commission Meeting",
            CANCELLED,
            COMMISSION,
        ),
        (
            datetime(2026, 10, 22, 15, 0),
            "Senior Commission Meeting",
            TENTATIVE,
            COMMISSION,
        ),
        (datetime(2026, 10, 28, 16, 0), "Library Board of Trustees", TENTATIVE, BOARD),
    ]


def test_boards_fields(boards_items):
    for item in boards_items:
        assert item["description"] == ""
        assert item["end"] is None
        assert item["all_day"] is False
        assert item["time_notes"] == ""
        assert item["location"] == CHAMBER
        assert item["links"] == []
        assert item["closed_to_public"] is False
    assert (
        boards_items[0]["source"]
        == "https://www.carlsbadca.gov/Home/Components/Calendar/Event/17455/17"
    )
    assert (
        boards_items[0]["id"]
        == "sandie_carlsbad_boards_commissions/202610011730/x/arts_commission"
    )
    assert len({item["id"] for item in boards_items}) == len(boards_items)


def test_council_meetings(council_items):
    """Both closed sessions, and not the month's subcommittee meetings."""
    assert [
        (item["start"], item["title"], item["status"], item["closed_to_public"])
        for item in council_items
    ] == [
        (
            datetime(2025, 10, 7, 15, 45),
            "City Council Meeting - Closed Session",
            PASSED,
            True,
        ),
        (
            datetime(2025, 10, 21, 16, 15),
            "City Council Meeting - Closed Session",
            PASSED,
            True,
        ),
    ]
    for item in council_items:
        assert item["classification"] == CITY_COUNCIL
        assert item["location"] == CHAMBER
        assert item["id"].startswith("sandie_carlsbad_council_committees/")


@pytest.mark.parametrize(
    "raw,title",
    [
        ("Arts Commission - Council Chamber", "Arts Commission"),
        ("City Council Meeting - CANCELED", "City Council Meeting"),
        (
            "City Council Meeting - Closed Session - Council Chamber",
            "City Council Meeting - Closed Session",
        ),
        (
            "Environmental Sustainability Commission - ADJOURNED",
            "Environmental Sustainability Commission",
        ),
        ("Housing Commission Regular Meeting", "Housing Commission Regular Meeting"),
    ],
)
def test_parse_title(raw, title):
    assert SandieCarlsbadCouncilCommitteesSpider()._parse_title(raw) == title


@pytest.mark.parametrize(
    "title,board",
    [
        (
            "Community-Police Engagement Meeting",
            "Community-Police Engagement Commission",
        ),
        ("Traffic and Mobility Commission", "Traffic Safety & Mobility Commission"),
        (
            "Traffic Safety & Mobility Commission Meeting",
            "Traffic Safety & Mobility Commission",
        ),
        ("Parks & Recreation Commission Meeting", "Parks & Recreation Commission"),
        ("Library Board of Trustees", "Library Board of Trustees"),
        (
            "Agricultural Conversion Mitigation Fee Committee",
            "Agricultural Conversion Mitigation Fee Citizens Advisory Committee",
        ),
        ("Public Art Advisory Subcommittee", None),
        # Seen on the live calendar for May 15, 2026
        ("Arts Commission Subcommittee Meeting", None),
        # Joint meetings belong to the council spider only
        ("Joint City Council and Planning Commission Meeting", None),
        ("City Council Meeting", None),
    ],
)
def test_boards_match(title, board):
    matched = SandieCarlsbadBoardsCommissionsSpider()._match_board(title)
    assert (matched or {}).get("title") == board


@pytest.mark.parametrize(
    "title,matches",
    [
        ("City Council Meeting", True),
        ("City Council Meeting - Closed Session", True),
        ("Joint City Council and Planning Commission Meeting", True),
        ("City Council Legislative Subcommittee", False),
        ("City/Schools Committee Special Meeting", False),
        ("Arts Commission", False),
    ],
)
def test_council_match(title, matches):
    spider = SandieCarlsbadCouncilCommitteesSpider()
    assert bool(spider._match_board(title)) is matches


def test_empty_page_logs_warning(caplog):
    spider = SandieCarlsbadCouncilCommitteesSpider()
    with caplog.at_level(logging.WARNING):
        items = list(spider.parse(_html("https://x", "<html></html>")))
    assert items == []
    assert "No calendar days found" in caplog.text


def test_day_without_date_logs_warning(caplog):
    page = _calendar(
        _calendar_day("Tuesday, October , ", [("5:00 PM", "City Council Meeting", 1)])
    )
    with caplog.at_level(logging.WARNING):
        items = list(
            SandieCarlsbadCouncilCommitteesSpider().parse(_html("https://x", page))
        )
    assert items == []
    assert "no parseable date" in caplog.text


def test_event_without_time_is_kept_at_midnight_with_a_note(caplog):
    """The live calendar lists Historic Preservation on Jan. 11, 2027 with no
    time (under "All Departments")."""
    spider = SandieCarlsbadBoardsCommissionsSpider()
    page = _calendar(
        _calendar_day(
            "Monday, January 11, 2027", [("", "Historic Preservation Commission", 1)]
        )
    )
    with freeze_time("2026-10-21 12:00"), caplog.at_level(logging.WARNING):
        meeting = next(spider.parse(_html("https://x", page)))
    assert "No start time" in caplog.text
    assert meeting["start"] == datetime(2027, 1, 11, 0, 0)
    assert meeting["time_notes"] == spider.no_time_notes


def test_weekend_and_today_cells_are_read():
    page = _calendar(
        '<td class="calendar_weekendday calendar_day_with_items" aria-label='
        '"Scheduled events, Saturday, October 3, 2026"><div class="calendar_item">'
        '<span class="calendar_eventtime">9:00 AM</span><a class="calendar_eventlink"'
        ' href="/e/1" title="City Council Special Meeting">x</a></div></td>'
        '<td class="calendar_today calendar_day_with_items" aria-label="Scheduled '
        'events, Monday, October 5, 2026"><div class="calendar_item"><span class='
        '"calendar_eventtime">5:00 PM</span><a class="calendar_eventlink" '
        'href="/e/2" title="City Council Meeting">x</a></div></td>'
    )
    with freeze_time("2026-10-05 12:00"):
        items = list(
            SandieCarlsbadCouncilCommitteesSpider().parse(_html("https://x", page))
        )
    assert [item["start"] for item in items] == [
        datetime(2026, 10, 3, 9, 0),
        datetime(2026, 10, 5, 17, 0),
    ]


@pytest.mark.parametrize(
    "events",
    [
        [
            ("5:00 PM", "City Council Meeting - CANCELED", 1),
            ("5:00 PM", "City Council Meeting", 2),
        ],
        [
            ("5:00 PM", "City Council Meeting", 2),
            ("5:00 PM", "City Council Meeting - CANCELED", 1),
        ],
    ],
)
def test_cancelled_listing_beside_its_repost_keeps_the_active_one(events):
    """Both listings have the same id once the CANCELED suffix is removed;
    the active one is kept whichever comes first."""
    page = _calendar(_calendar_day("Tuesday, October 27, 2026", events))
    with freeze_time("2026-10-01 12:00"):
        items = list(
            SandieCarlsbadCouncilCommitteesSpider().parse(_html("https://x", page))
        )
    assert [(item["status"], item["source"][-4:]) for item in items] == [
        (TENTATIVE, "2/17")
    ]


# ============ Board page folders ============


def test_board_page_folders():
    """Folder titles from the live City Council page, saved 2026-10-20: two
    meetings on Sept. 15 are told apart by their start times."""
    spider = SandieCarlsbadCouncilCommitteesSpider()
    page = _folder_list(
        ("Oct. 20, 2026, 5 p.m. City Council Chamber - Regular Meeting", 1658),
        ("Sept. 15, 2026, 5 p.m. City Council Chamber - Regular Meeting", 1639),
        (
            "Sept. 15, 2026, 4 p.m. City Council Chamber - Special Meeting - "
            "Closed Session",
            1640,
        ),
    )
    folders = spider._parse_folders(_html(AGENDAS_URL, page))
    assert folders[0] == (
        "Oct. 20, 2026, 5 p.m. City Council Chamber - Regular Meeting",
        "/city-hall/meetings-agendas/-folder-1658",
    )
    with freeze_time("2026-10-20 12:00"):
        parsed = [spider._parse_folder_title(title) for title, _ in folders]
    assert parsed == [
        (date(2026, 10, 20), datetime(2026, 10, 20, 17, 0)),
        (date(2026, 9, 15), datetime(2026, 9, 15, 17, 0)),
        (date(2026, 9, 15), datetime(2026, 9, 15, 16, 0)),
    ]


@pytest.mark.parametrize(
    "title,parsed",
    [
        (
            "Oct. 1, 2026, 5:30 p.m. City Council Chamber - Regular Meeting",
            (date(2026, 10, 1), datetime(2026, 10, 1, 17, 30)),
        ),
        (
            "July 14, 2026, 5 p.m. - City Council Chamber - Regular Meeting",
            (date(2026, 7, 14), datetime(2026, 7, 14, 17, 0)),
        ),
        (
            "Sept. 3, 2026, 10 a.m. City Council Chamber - Regular Meeting",
            (date(2026, 9, 3), datetime(2026, 9, 3, 10, 0)),
        ),
        ("March 9, 2026 City Council Chamber", (date(2026, 3, 9), None)),
        # A typo on the live Parks & Recreation page
        ("Sept. 21, 2626, 5:30 p.m. City Council Chamber - Meeting", (None, None)),
        ("Agendas", (None, None)),
    ],
)
def test_parse_folder_title(title, parsed):
    with freeze_time("2026-10-20 12:00"):
        assert (
            SandieCarlsbadCouncilCommitteesSpider()._parse_folder_title(title) == parsed
        )


def test_folders_are_walked_recursively():
    """Documents of a folder and its subfolders, up to max_folder_depth; the
    breadcrumb's links aren't documents or subfolders."""
    pages = {
        f"{AGENDAS_URL}/-folder-1": _folder_page(
            ("10-06-2026 Regular Meeting Agenda", 1), subfolders=[("Staff Reports", 2)]
        ),
        f"{AGENDAS_URL}/-folder-2": _folder_page(
            ("Item 1 Staff Report", 2), subfolders=[("Exhibits", 3)]
        ),
        # Doubled spaces as in the live "Special Meeting  Agenda"
        f"{AGENDAS_URL}/-folder-3": _folder_page(("Item 1  Exhibit A", 3)),
    }
    spider = SandieCarlsbadCouncilCommitteesSpider()
    with patch.object(
        spider,
        "_akamai_get",
        side_effect=lambda url, referer=None: _html(url, pages[url]),
    ):
        links = spider._folder_documents(f"{AGENDAS_URL}/-folder-1", None, 1)
        assert links == [
            _document(1, "10-06-2026 Regular Meeting Agenda"),
            _document(2, "Item 1 Staff Report"),
            _document(3, "Item 1 Exhibit A"),
        ]
        spider.max_folder_depth = 2
        links = spider._folder_documents(f"{AGENDAS_URL}/-folder-1", None, 1)
        assert len(links) == 2


# ============ Laserfiche ============


@pytest.mark.parametrize(
    "name,title,parsed",
    [
        (
            "2026-10-06; City Council; Agendas; Regular Session",
            "Agenda - Regular Session",
            date(2026, 10, 6),
        ),
        ("2014-04-22; City Council; Agendas;", "Agenda", date(2014, 4, 22)),
        (
            "2026-01-13; City Council; CS02; Conference with Labor Negotiators",
            "Item CS02 - Conference with Labor Negotiators",
            date(2026, 1, 13),
        ),
        (
            "2026-10-01; Arts Commission; Minutes; Regular Session",
            "Minutes - Regular Session",
            date(2026, 10, 1),
        ),
        (
            "2026-10-20; City Council; Resolution 2026-194",
            "Resolution 2026-194",
            date(2026, 10, 20),
        ),
        # The live name has a colon after the date
        (
            "2026-01-13: City Council; Meeting Video; Closed Session",
            "Meeting Video - Closed Session",
            date(2026, 1, 13),
        ),
        # The live name has doubled spaces
        (
            "2025-03-03; Traffic Safety and Mobility Commission; 02; Avenida  "
            "Encinas Coastal Rail Trail",
            "Item 02 - Avenida Encinas Coastal Rail Trail",
            date(2025, 3, 3),
        ),
        ("Agenda Template", "Document", None),
    ],
)
def test_laserfiche_names(name, title, parsed):
    spider = SandieCarlsbadCouncilCommitteesSpider()
    assert spider._laserfiche_title(name) == title
    assert spider._parse_laserfiche_date(name) == parsed


def test_laserfiche_listing_pages_through_results():
    spider = SandieCarlsbadCouncilCommitteesSpider()
    spider.laserfiche_page_size = 2
    pages = [
        {"data": {"results": [{"entryId": 1}, {"entryId": 2}], "totalEntries": 3}},
        {"data": {"results": [{"entryId": 3}], "totalEntries": 3}},
    ]
    responses = [MagicMock(json=MagicMock(return_value=page)) for page in pages]
    with patch.object(mixin.curl_requests, "post", side_effect=responses) as post:
        entries = spider._laserfiche_entries(4486195)
    assert [e["entryId"] for e in entries] == [1, 2, 3]
    assert [c.kwargs["json"]["start"] for c in post.call_args_list] == [0, 2]


def test_laserfiche_failure_logs_warning(caplog):
    spider = SandieCarlsbadCouncilCommitteesSpider()
    response = MagicMock(json=MagicMock(return_value={"data": None}))
    with caplog.at_level(logging.WARNING), patch.object(
        mixin.curl_requests, "post", return_value=response
    ):
        assert spider._laserfiche_entries(1) is None
    assert "Laserfiche folder 1 failed" in caplog.text


def test_laserfiche_links_of_the_same_special_or_cancelled_session():
    """A cancelled regular meeting and a special meeting on one date (Senior
    Commission, June 26, 2025) each get only their own packet folder."""
    spider = SandieCarlsbadBoardsCommissionsSpider()
    notice = {"href": LASERFICHE.format(1), "title": "Agenda - Notice of Cancellation"}
    item = {"href": LASERFICHE.format(2), "title": "Item 01 - Action Plan Update"}
    minutes = {"href": LASERFICHE.format(3), "title": "Minutes - Special Session"}
    cancellation = "2025-06-26; Senior Commission; Notice of Meeting Cancellation"
    special = "2025-06-26; Senior Commission; Special Session"
    spider._laserfiche_links[("Senior Commission", date(2025, 6, 26))] = [
        (cancellation, notice),
        (special, item),
        (special, minutes),
    ]
    regular = _meeting(
        "Senior Commission Meeting", datetime(2025, 6, 26, 15, 0), status=CANCELLED
    )
    special_meeting = _meeting(
        "Senior Commission Special Meeting", datetime(2025, 6, 26, 15, 30)
    )
    assert spider._links_for("Senior Commission", regular) == ([notice], "")
    assert spider._links_for("Senior Commission", special_meeting) == (
        [item, minutes],
        "",
    )


def test_agendas_folder_for_meetings_without_a_packet():
    spider = SandieCarlsbadCouncilCommitteesSpider()
    laserfiche = {
        9016814: [],
        4486195: [_laserfiche_folder(2025, "2025")],
        2025: [
            _laserfiche_doc(31, "2025-10-21; City Council; Agendas; Closed Session"),
        ],
    }
    meeting = {"title": "City Council Meeting", "start": datetime(2025, 10, 21, 16, 15)}
    with patch.object(spider, "_akamai_get", return_value=None), patch.object(
        spider, "_laserfiche_entries", side_effect=lambda fid: laserfiche[fid]
    ), patch.object(spider, "_swagit_get", return_value=None):
        spider._load_attachments([meeting])
    assert spider._laserfiche_links[("City Council", date(2025, 10, 21))] == [
        (
            "2025-10-21; City Council; Agendas; Closed Session",
            {
                "href": LASERFICHE.format(31),
                "title": "Agenda - Closed Session",
            },
        )
    ]


# ============ Akamai fetches ============


def test_akamai_challenge_is_retried_then_given_up(caplog):
    spider = SandieCarlsbadCouncilCommitteesSpider()
    spider.request_delay = 0
    spider.akamai_retry_backoff = 0
    challenge = MagicMock(status_code=200, content=b"<html>bm-verify</html>")
    with caplog.at_level(logging.WARNING), patch.object(
        mixin.curl_requests, "get", return_value=challenge
    ) as get:
        assert spider._akamai_get("https://www.carlsbadca.gov/x") is None
    assert get.call_count == 3
    assert get.call_args.kwargs["impersonate"] == mixin.IMPERSONATE
    assert "Akamai challenge page" in caplog.text


def test_akamai_page_is_returned_as_html_response():
    spider = SandieCarlsbadCouncilCommitteesSpider()
    page = MagicMock(status_code=200, content=b"<html><td>ok</td></html>")
    with patch.object(mixin.curl_requests, "get", return_value=page):
        response = spider._akamai_get("https://www.carlsbadca.gov/x")
    assert response.css("td::text").get() == "ok"


# ============ Whole run ============


def test_crawl_requests(crawl):
    """Every calendar month, then the board page and its folders for dates
    that have a meeting; the packets year folder and the run's meeting
    folders, and not the Agendas folder (every date has a packet); one page
    of the City Council video tab, which has no next page."""
    calendar_urls = [url for url in crawl["fetched"] if "/calendar/" in url]
    assert calendar_urls[0] == CALENDAR_URL.format(m=10, y=2024)
    assert len(calendar_urls) == 37
    assert crawl["fetched"][37:] == [
        AGENDAS_URL,
        f"{AGENDAS_URL}/-folder-1001",
        f"{AGENDAS_URL}/-folder-1002",
    ]
    assert sorted(crawl["listed"]) == [907, 921, 922, 2025, 9016814]
    assert crawl["videos"] == [
        "https://carlsbadca.new.swagit.com/views/295/city-council?page=1"
    ]
    assert len(crawl["items"]) == 2


def test_crawl_links_from_folder_with_the_same_start(crawl):
    """The board-page folder with the meeting's start time (not the 5 p.m.
    meeting's), plus the Laserfiche minutes the folder doesn't have; the
    Laserfiche agenda would repeat the folder's."""
    item = _by_start(crawl["items"], datetime(2025, 10, 7, 15, 45))
    assert item["links"] == [
        _document(11, "10-07-2025 Closed Session Agenda"),
        {"href": LASERFICHE.format(72), "title": "Minutes - Closed Session"},
    ]


def test_crawl_links_from_laserfiche_packet_of_the_same_session(crawl):
    """Every document in the closed session's packet folder, none from the
    regular session's folder on the same date, then the closed session's
    Swagit video (the "Special Meeting" one, not the regular meeting's)."""
    item = _by_start(crawl["items"], datetime(2025, 10, 21, 16, 15))
    assert item["links"] == [
        {"href": LASERFICHE.format(21), "title": "Agenda - Closed Session"},
        {
            "href": LASERFICHE.format(23),
            "title": "Item CS01 - Conference with Legal Counsel",
        },
        {"href": LASERFICHE.format(24), "title": "Minutes - Closed Session"},
        _video(502),
    ]


def test_folder_title_cancellation_reaches_the_meeting():
    spider = SandieCarlsbadCouncilCommitteesSpider()
    page = _calendar(
        _calendar_day(
            "Tuesday, October 27, 2026", [("5:00 PM", "City Council Meeting", 7)]
        )
    )
    with freeze_time("2026-10-01 12:00"):
        meeting = next(spider.parse(_html("https://x", page)))
        spider._folder_links[("City Council", date(2026, 10, 27))].append(
            (
                "Oct. 27, 2026, 5 p.m. City Council Chamber - Regular Meeting - "
                "CANCELED",
                datetime(2026, 10, 27, 17, 0),
                [],
            )
        )
        meeting = spider._finish(meeting)
    assert meeting["status"] == CANCELLED


def test_crawl_skips_unfetchable_month(caplog):
    spider = SandieCarlsbadCouncilCommitteesSpider()
    spider.months_ahead = 0
    with freeze_time("2026-10-01 12:00"), caplog.at_level(
        logging.WARNING
    ), patch.object(spider, "_akamai_get", return_value=None):
        assert list(spider._run_crawl(None)) == []
    assert "Could not fetch calendar month" in caplog.text


# ============ Videos ============


def test_videos_are_paged_until_the_earliest_date():
    """Pages are read newest first and stop at the page that goes past the
    run's earliest meeting date; only the run's boards and dates are kept."""
    pages = {
        1: _swagit_page(
            ("Senior Commission Meeting", "Oct 22, 2026", 11),
            ("Housing Commission Meeting", "Oct 08, 2026", 12),
            next_page=2,
        ),
        2: _swagit_page(
            ("Arts Commission Meeting", "Sep 03, 2026", 13),
            ("Arts Commission Meeting", "Aug 06, 2026", 14),
            next_page=3,
        ),
    }
    spider = SandieCarlsbadBoardsCommissionsSpider()
    fetched = []

    def fake_swagit(url):
        fetched.append(url)
        return _html(url, pages[int(url.rsplit("=", 1)[1])])

    needed = {
        "Senior Commission": {date(2026, 10, 22)},
        "Arts Commission": {date(2026, 9, 3)},
    }
    with patch.object(spider, "_swagit_get", side_effect=fake_swagit):
        spider._load_videos(needed)
    assert fetched == [
        "https://carlsbadca.new.swagit.com/views/295/all-boards-commissions?page=1",
        "https://carlsbadca.new.swagit.com/views/295/all-boards-commissions?page=2",
    ]
    assert dict(spider._videos) == {
        ("Senior Commission", date(2026, 10, 22)): [
            ("Senior Commission Meeting", _video(11))
        ],
        ("Arts Commission", date(2026, 9, 3)): [
            ("Arts Commission Meeting", _video(13))
        ],
    }


def test_add_videos():
    """A date's only video goes to its meeting; with several, the special
    (or regular) one like the meeting. Cancelled meetings, meetings that
    already have a Laserfiche video and a video two meetings would share get
    none."""
    spider = SandieCarlsbadBoardsCommissionsSpider()
    spider._videos.update(
        {
            ("Arts Commission", date(2026, 9, 3)): [
                ("Arts Commission Meeting", _video(1))
            ],
            ("Senior Commission", date(2025, 6, 26)): [
                ("Senior Commission Special Meeting", _video(2))
            ],
            ("Parks & Recreation Commission", date(2026, 7, 16)): [
                ("Parks & Recreation Commission Meeting", _video(3)),
                ("Parks & Recreation Commission Special Meeting", _video(4)),
            ],
            ("Library Board of Trustees", date(2026, 5, 27)): [
                ("Library Board of Trustees Meeting", _video(5))
            ],
        }
    )
    laserfiche_video = {"href": LASERFICHE.format(9), "title": "Meeting Video"}
    meetings = [
        _meeting("Arts Commission Meeting", datetime(2026, 9, 3, 17, 30)),
        _meeting(
            "Senior Commission Meeting", datetime(2025, 6, 26, 15), status=CANCELLED
        ),
        _meeting("Senior Commission Special Meeting", datetime(2025, 6, 26, 15, 30)),
        _meeting(
            "Parks & Recreation Commission Special Meeting",
            datetime(2026, 7, 16, 17, 30),
        ),
        _meeting("Library Board of Trustees", datetime(2026, 5, 27, 16)),
        _meeting("Library Board of Trustees", datetime(2026, 5, 27, 18)),
        _meeting(
            "Housing Commission Meeting",
            datetime(2026, 6, 11, 17),
            links=[laserfiche_video],
        ),
    ]
    spider._add_videos(meetings)
    assert [m["links"] for m in meetings] == [
        [_video(1)],
        [],
        [_video(2)],
        [_video(4)],
        [],
        [],
        [laserfiche_video],
    ]


def test_closed_session_gets_the_special_video():
    """Swagit calls a closed session's open part a special meeting."""
    spider = SandieCarlsbadCouncilCommitteesSpider()
    spider._videos[("City Council", date(2026, 9, 15))] = [
        ("City Council Meeting", _video(1)),
        ("City Council Special Meeting", _video(2)),
    ]
    meeting = _meeting(
        "City Council Meeting - Closed Session",
        datetime(2026, 9, 15, 16),
        closed=True,
    )
    spider._add_videos([meeting])
    assert meeting["links"] == [_video(2)]


def test_video_row_without_a_date_logs_warning(caplog):
    page = _swagit_page(("Arts Commission Meeting", "TBD", 1))
    spider = SandieCarlsbadBoardsCommissionsSpider()
    with caplog.at_level(logging.WARNING), patch.object(
        spider, "_swagit_get", return_value=_html("https://x", page)
    ):
        spider._load_videos({"Arts Commission": {date(2026, 9, 3)}})
    assert spider._videos == {}
    assert "Unparseable video date" in caplog.text


def test_swagit_failure_logs_warning(caplog):
    spider = SandieCarlsbadBoardsCommissionsSpider()
    with caplog.at_level(logging.WARNING), patch.object(
        mixin.curl_requests,
        "get",
        side_effect=mixin.curl_requests.RequestsError("timed out"),
    ):
        assert spider._swagit_get("https://carlsbadca.new.swagit.com/x") is None
    assert "Swagit page https://carlsbadca.new.swagit.com/x failed" in caplog.text
