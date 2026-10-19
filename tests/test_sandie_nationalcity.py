import json
from datetime import datetime, timedelta
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
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

from city_scrapers.spiders.sandie_nationalcity import (
    SandieBoardsCommissionsSpider,
    SandieCityCouncilSpider,
)

# Page 2 of the live listing, saved 2026-09-27: meetings from 2026-09-09 to
# 2027-02-18. Frozen at 2026-09-25 so it has both past and upcoming meetings;
# the start cutoff (today - 2 years) is 2024-09-25.
test_response = file_response(
    join(dirname(__file__), "files", "sandie_nationalcity.html"),
    url="https://www.nationalcityca.gov/government/boards-commissions-committees/-toggle-all/-sortn-EDate/-sortd-desc/-npage-2",  # noqa
)


@pytest.fixture
def council_spider():
    return SandieCityCouncilSpider()


@pytest.fixture
def boards_spider():
    return SandieBoardsCommissionsSpider()


@pytest.fixture
def council_results(council_spider):
    """Everything parse() yields for the fixture page: meetings and the
    next-page request"""
    with freeze_time("2026-09-25"):
        return list(council_spider.parse(test_response))


@pytest.fixture
def council_items(council_results):
    return [item for item in council_results if isinstance(item, Meeting)]


@pytest.fixture
def boards_items(boards_spider):
    with freeze_time("2026-09-25"):
        return [
            item
            for item in boards_spider.parse(test_response)
            if isinstance(item, Meeting)
        ]


def _by_start(items, start):
    return [item for item in items if item["start"] == start]


# ============ City Council Spider Tests ============


def test_council_spider_configuration(council_spider):
    """Test that City Council spider is properly configured"""
    assert council_spider.name == "sandie_national_council_committees"
    assert council_spider.agency == "San Diego National City - City Council"
    assert council_spider.event_type == "City Council"


def test_council_count(council_items):
    """Test that City Council spider gets the page's 4 council meetings"""
    assert len(council_items) == 4


def test_council_title(council_items):
    """Test that council meeting titles are correctly parsed"""
    assert [item["title"] for item in council_items] == [
        "Special City Council Meeting",
        "City Council Meeting",
        "Special City Council Meeting - Closed Session",
        "Special City Council Meeting - Closed Session",
    ]


def test_council_start(council_items):
    """Test that council meeting start times are correctly parsed"""
    assert [item["start"] for item in council_items] == [
        datetime(2026, 9, 29, 17, 0),
        datetime(2026, 9, 15, 18, 0),
        datetime(2026, 9, 15, 17, 0),
        datetime(2026, 9, 9, 13, 30),
    ]


def test_council_end(council_items):
    """Rows with a time range get an end; rows with only a start time don't"""
    assert [item["end"] for item in council_items] == [
        None,
        None,
        datetime(2026, 9, 15, 18, 0),
        None,
    ]


def test_council_classification(council_items):
    """Test that council meeting classification is CITY_COUNCIL"""
    for item in council_items:
        assert item["classification"] == CITY_COUNCIL


def test_council_status(council_items):
    """Past meetings are PASSED, the upcoming 9/29 meeting is TENTATIVE"""
    assert [item["status"] for item in council_items] == [
        TENTATIVE,
        PASSED,
        PASSED,
        PASSED,
    ]


def test_council_links(council_items):
    """Test that council meeting links are correctly parsed"""
    (meeting,) = _by_start(council_items, datetime(2026, 9, 15, 18, 0))
    assert len(meeting["links"]) == 9
    assert meeting["links"][0] == {
        "href": "https://www.nationalcityca.gov/home/showpublisheddocument/37388/639246616538870000",  # noqa
        "title": "Agenda Packet - Regular City Council Meeting of September 15, 2026",
    }
    assert {
        "href": "https://www.nationalcityca.gov/home/showpublisheddocument/37398/639250804584170000",  # noqa
        "title": "Written Public Comment",
    } in meeting["links"]


def test_council_source(council_spider, council_items):
    """Source is the main listing URL, not the page the meeting was found on"""
    for item in council_items:
        assert item["source"] == council_spider.start_url


def test_council_id(council_items):
    """Test that unique ID is generated"""
    assert council_items[0]["id"] == (
        "sandie_national_council_committees/202609291700/x/"
        "special_city_council_meeting"
    )


def test_council_location(council_spider, council_items):
    """Test that the default location is used"""
    for item in council_items:
        assert item["location"] == council_spider.location


def test_parse_yields_next_page_request(council_results):
    """The fixture page has a Next link, so parse() also yields page 3"""
    requests = [r for r in council_results if not isinstance(r, Meeting)]
    assert [r.url for r in requests] == [
        "https://www.nationalcityca.gov/government/boards-commissions-committees/-toggle-all/-sortn-EDate/-sortd-desc/-npage-3"  # noqa
    ]


# ============ Boards & Commissions Spider Tests ============


def test_boards_spider_configuration(boards_spider):
    """Test that Boards & Commissions spider is properly configured"""
    assert boards_spider.name == "sandie_national_boards_commissions"
    assert boards_spider.agency == "San Diego National City - Boards and Commissions"
    assert isinstance(boards_spider.event_type, list)


def test_boards_count(boards_items):
    """Test that Boards & Commissions spider gets all matching meetings"""
    # 16 board rows (one of them a combined meeting split into two) plus the
    # 9/15 City Council Meeting, whose links mention board appointments
    assert len(boards_items) == 18


def test_boards_classification(boards_items):
    """Test that each board type gets the right classification"""
    expected = {
        "Planning Commission Meeting": COMMISSION,
        "Civil Service Commission Meeting": COMMISSION,
        "Community and Police Relations Commission": COMMISSION,
        "Public Art Committee": COMMITTEE,
        "Public Arts Committee": COMMITTEE,
        "Parks, Recreation and Senior Citizen's Advisory Committee": (
            ADVISORY_COMMITTEE
        ),
        "Housing Advisory Meeting": ADVISORY_COMMITTEE,
    }
    for item in boards_items:
        if item["title"] in expected:
            assert item["classification"] == expected[item["title"]]


def test_boards_past_meeting(boards_items):
    """Test a past Planning Commission meeting with agenda and packet"""
    (meeting,) = _by_start(boards_items, datetime(2026, 9, 21, 18, 0))
    assert meeting["title"] == "Planning Commission Meeting"
    assert meeting["end"] == datetime(2026, 9, 21, 20, 0)
    assert meeting["status"] == PASSED
    assert [link["title"] for link in meeting["links"]] == [
        "September 21, 2026 Planning Commission Meeting Agenda",
        "September 21 2026 Planning Commission Meeting Complete Packet",
    ]


def test_boards_upcoming_meeting(boards_items):
    """Test an upcoming meeting with no documents yet"""
    (meeting,) = _by_start(boards_items, datetime(2027, 2, 18, 18, 0))
    assert meeting["title"] == "Community and Police Relations Commission"
    assert meeting["status"] == TENTATIVE
    assert meeting["links"] == []


def test_boards_cancelled_meeting(boards_items):
    """A '- Meeting Cancelled' title gets CANCELLED status"""
    (meeting,) = _by_start(boards_items, datetime(2026, 9, 17, 16, 0))
    assert meeting["title"] == (
        "Parks, Recreation and Senior Citizen's Advisory Committee - Meeting Cancelled"
    )
    assert meeting["status"] == CANCELLED
    assert meeting["links"][0]["title"] == (
        "Cancellation Notice - Lack of Quorum 9.17.2026"
    )


def test_boards_combined_meeting_is_split(boards_items):
    """'Planning Commission and Housing Advisory Committee Meeting' becomes two"""
    meetings = _by_start(boards_items, datetime(2026, 10, 19, 18, 0))
    assert sorted(item["title"] for item in meetings) == [
        "Housing Advisory Meeting",
        "Planning Commission Meeting",
    ]
    assert len({item["id"] for item in meetings}) == 2


def test_boards_matches_council_meeting_with_board_links(boards_items):
    """Rows match on all their text, so the 9/15 City Council Meeting (with
    board appointment ballots in its links) is also picked up here"""
    (meeting,) = _by_start(boards_items, datetime(2026, 9, 15, 18, 0))
    assert meeting["title"] == "City Council Meeting"
    assert "Planning Commission" in str(meeting["links"])


def test_boards_status(boards_items):
    """Past meetings are PASSED (or CANCELLED), upcoming ones TENTATIVE"""
    now = datetime(2026, 9, 25)
    for item in boards_items:
        if item["status"] == CANCELLED:
            continue
        assert item["status"] == (PASSED if item["start"] < now else TENTATIVE)


def test_boards_links_parsed(boards_items):
    """Test that links are correctly parsed for boards meetings"""
    for item in boards_items:
        assert isinstance(item["links"], list)
        for link in item["links"]:
            assert link["href"].startswith("https://www.nationalcityca.gov/")
            assert link["title"]


def test_boards_location(boards_spider, boards_items):
    """Test that default location is set"""
    for item in boards_items:
        assert item["location"] == boards_spider.location


def test_all_day_false(council_items, boards_items):
    """Test that all_day is False for all meetings"""
    for item in council_items + boards_items:
        assert item["all_day"] is False


# ============ Start Cutoff Tests ============


@freeze_time("2026-09-25")
def test_start_cutoff_is_two_years_before_today(boards_spider):
    assert boards_spider._start_cutoff() == datetime(2024, 9, 24)


@freeze_time("2024-02-29")
def test_start_cutoff_on_leap_day(boards_spider):
    assert boards_spider._start_cutoff() == datetime(2022, 2, 28)


@freeze_time("2028-09-25")
def test_meetings_before_cutoff_are_skipped(council_spider):
    """Two years later the cutoff is 2026-09-25: only the upcoming meetings on
    the page are kept"""
    items = [r for r in council_spider.parse(test_response) if isinstance(r, Meeting)]
    assert [item["start"] for item in items] == [datetime(2026, 9, 29, 17, 0)]


# ============ curl-cffi Crawl Tests ============


@freeze_time("2026-09-25")
def test_run_crawl_fetches_listing_via_akamai_get(council_items):
    """_run_crawl fetches listing pages through curl-cffi and yields meetings"""
    spider = SandieCityCouncilSpider()
    spider._fetch_escribe_meetings = lambda start, end: []  # no network
    fetched = []

    def fake_get(url):
        fetched.append(url)
        return test_response if url == spider.start_url else None

    spider._akamai_get = fake_get
    items = list(spider._run_crawl(None))

    # Page 1 (the fixture) is fetched, then its Next link (page 3)
    assert fetched == [spider.start_url, test_response.url.replace("-2", "-3")]
    assert items == council_items


@freeze_time("2026-09-25")
def test_run_crawl_blocked_listing_yields_nothing():
    """A blocked listing page stops the crawl without raising (no eSCRIBE)"""
    spider = SandieBoardsCommissionsSpider()
    assert spider.escribe_url is None
    spider._akamai_get = lambda url: None
    assert list(spider._run_crawl(None)) == []


def test_row_without_start_date_is_skipped():
    """A matching row with no parseable date is skipped instead of crashing"""
    from scrapy.http import HtmlResponse

    body = b"""<table><tbody><tr>
        <td>City Council Meeting</td><td>TBD</td>
    </tr></tbody></table>"""
    response = HtmlResponse(url=test_response.url, body=body, encoding="utf-8")
    assert list(SandieCityCouncilSpider().parse(response)) == []


def _live_row_response(datetime_cell, agenda_text=""):
    from scrapy.http import HtmlResponse

    body = f"""<table><tbody><tr>
        <td>Special City Council Meeting</td>
        <td class="event_datetime">{datetime_cell}</td>
        <td><a href="/home/showpublisheddocument/1">{agenda_text}</a></td>
    </tr></tbody></table>""".encode()
    return HtmlResponse(url=test_response.url, body=body, encoding="utf-8")


@freeze_time("2026-09-25")
def test_live_markup_without_end_time():
    """Live rows with no end time use the hidden startDate and have no end"""
    response = _live_row_response(
        "09/29/2026 5:00 PM "
        '<time itemprop="startDate">09/29/2026 5:00 PM</time> '
        '<time itemprop="endDate">09/29/2026</time>',
        agenda_text="2026 09-14 CC SP MIN",
    )
    spider = SandieCityCouncilSpider()
    items = list(spider.parse(response))
    assert len(items) == 1
    assert items[0]["start"] == datetime(2026, 9, 29, 17, 0)
    assert items[0]["end"] is None


@freeze_time("2026-09-25")
def test_live_markup_with_time_range():
    """Live rows with a range use the hidden startDate/endDate times"""
    response = _live_row_response(
        "02/19/2026 6:00 PM - 8:00 PM "
        '<time itemprop="startDate">02/19/2026 6:00 PM</time> '
        '<time itemprop="endDate">02/19/2026 8:00 PM</time>'
    )
    items = list(SandieCityCouncilSpider().parse(response))
    assert items[0]["start"] == datetime(2026, 2, 19, 18, 0)
    assert items[0]["end"] == datetime(2026, 2, 19, 20, 0)


def _listing_page(url, date, title="Planning Commission Meeting"):
    from scrapy.http import HtmlResponse

    body = f"""<table><tbody><tr>
        <td>{title}</td>
        <td class="event_datetime">{date} 6:00 PM</td>
    </tr></tbody></table>
        <a href="/government/boards-commissions-committees/-npage-99">Next</a>"""
    return HtmlResponse(url=url, body=body.encode(), encoding="utf-8")


def test_parse_follows_next_page_while_after_cutoff():
    """Pagination continues while the page's meetings are on/after the cutoff"""
    spider = SandieCityCouncilSpider()
    date = spider._start_cutoff().strftime("%m/%d/%Y")
    results = list(spider.parse(_listing_page(test_response.url, date)))
    assert [r.url for r in results if hasattr(r, "callback")] == [
        "https://www.nationalcityca.gov/government/"
        "boards-commissions-committees/-npage-99"
    ]


def test_parse_stops_paging_before_cutoff():
    """Pagination stops once a page reaches meetings before the cutoff"""
    spider = SandieCityCouncilSpider()
    date = (spider._start_cutoff() - timedelta(days=1)).strftime("%m/%d/%Y")
    assert list(spider.parse(_listing_page(test_response.url, date))) == []


def test_run_crawl_stops_at_cutoff():
    """_run_crawl fetches pages until one reaches meetings before the cutoff"""
    spider = SandieCityCouncilSpider()
    cutoff = spider._start_cutoff()
    dates = [
        (cutoff + timedelta(days=days)).strftime("%m/%d/%Y")
        for days in (400, 30, -1, -400)
    ]
    fetched = []

    def fake_get(url):
        fetched.append(url)
        return _listing_page(url, dates[len(fetched) - 1])

    spider._akamai_get = fake_get
    list(spider._run_crawl(None))
    assert len(fetched) == 3


# ============ eSCRIBE Fallback Tests ============

with open(join(dirname(__file__), "files", "sandie_nationalcity_escribe.json")) as f:
    escribe_meetings = json.load(f)["d"]  # saved eSCRIBE calendar response


def _council_spider_with_fallback(listing_pages):
    """Council spider whose website fetches return listing_pages in order (None =
    blocked) and whose eSCRIBE fetch returns the fixture, recording the range."""
    spider = SandieCityCouncilSpider()
    pages = iter(listing_pages)
    spider._akamai_get = lambda url: next(pages, None)
    spider.escribe_ranges = []

    def fake_fetch(start, end):
        spider.escribe_ranges.append((start, end))
        return escribe_meetings

    spider._fetch_escribe_meetings = fake_fetch
    return spider


def test_council_spider_has_escribe_fallback(council_spider):
    assert council_spider.escribe_url == (
        "https://pub-nationalcity.escribemeetings.com"
    )


@freeze_time("2026-09-25")
def test_escribe_meeting_parsing(council_spider, council_items):
    """eSCRIBE entries map to meetings with website-style titles"""
    items = list(council_spider._parse_escribe_meetings(escribe_meetings))
    by_start = {item["start"]: item for item in items}

    # 2024-09-17 is before the 2024-09-25 cutoff; the other 6 are kept
    assert datetime(2024, 9, 17, 18, 0) not in by_start
    assert len(items) == 6

    regular = by_start[datetime(2026, 9, 15, 18, 0)]
    assert regular["title"] == "City Council Meeting"
    assert regular["end"] is None  # eSCRIBE's EndDate (10pm) is not used
    assert regular["classification"] == CITY_COUNCIL
    assert regular["status"] == PASSED
    assert regular["location"] == council_spider.location
    assert regular["links"][0] == {
        "href": "https://pub-nationalcity.escribemeetings.com"
        "/FileStream.ashx?DocumentId=11499",
        "title": "Agenda Cover Page (PDF)",
    }
    # Same listing page as the website's meetings
    assert regular["source"] == council_spider.start_url
    # Same id as the website's version of this meeting
    (website_version,) = _by_start(council_items, datetime(2026, 9, 15, 18, 0))
    assert regular["id"] == website_version["id"]

    closed = by_start[datetime(2026, 9, 9, 13, 30)]
    assert closed["title"] == "Special City Council Meeting - Closed Session"

    # No agenda published yet: no links
    upcoming = by_start[datetime(2026, 10, 6, 18, 0)]
    assert upcoming["status"] == TENTATIVE
    assert upcoming["links"] == []

    workshop = by_start[datetime(2026, 7, 21, 15, 0)]
    assert workshop["location"] == {
        "name": "Martin Luther King Jr. Community Center",
        "address": "",
    }

    cancelled = by_start[datetime(2026, 11, 3, 18, 0)]
    assert cancelled["title"] == "City Council Meeting"
    assert cancelled["status"] == CANCELLED


@freeze_time("2026-09-25")
def test_fallback_when_first_listing_page_blocked():
    """If the website is blocked from the start, all meetings come from eSCRIBE"""
    spider = _council_spider_with_fallback([None])
    items = list(spider._run_crawl(None))

    assert spider.escribe_ranges[0][0] == datetime(2024, 9, 24)  # the cutoff
    assert len(items) == 6  # fixture minus the meeting before the cutoff
    assert all(item["source"] == spider.start_url for item in items)


@freeze_time("2026-09-25")
def test_fallback_fills_only_what_the_website_missed():
    """After page 2 is blocked, eSCRIBE only fills in meetings up to the oldest
    listed date, and skips meetings the website already produced"""
    spider = _council_spider_with_fallback([test_response, None])
    items = list(spider._run_crawl(None))

    # Oldest row on the fixture page is the 9/9 1:30pm closed session
    assert spider.escribe_ranges[0][1] == datetime(2026, 9, 9, 13, 30)
    # Both sources use start_url, so tell them apart by their document links
    sources = {
        item["start"]: (
            "escribe"
            if item["links"][0]["href"].startswith(spider.escribe_url)
            else "website"
        )
        for item in items
    }
    # The 4 website meetings (9/9 not duplicated from eSCRIBE); the July
    # workshop comes from eSCRIBE; 9/22, 10/6 and 11/3 are newer than the
    # website's coverage and are skipped
    assert len(items) == len(sources)
    assert sources == {
        datetime(2026, 7, 21, 15, 0): "escribe",
        datetime(2026, 9, 9, 13, 30): "website",
        datetime(2026, 9, 15, 17, 0): "website",
        datetime(2026, 9, 15, 18, 0): "website",
        datetime(2026, 9, 29, 17, 0): "website",
    }


# ============ Akamai Challenge Page Tests ============


def test_akamai_challenge_page_is_detected(council_spider):
    """A 200 with Akamai's JavaScript challenge (bm-verify) is not a real page"""
    with open(
        join(dirname(__file__), "files", "sandie_nationalcity_akamai_challenge.html"),
        "rb",
    ) as f:
        challenge = f.read()
    assert council_spider._is_akamai_challenge(challenge)
    assert not council_spider._is_akamai_challenge(test_response.body)


def test_akamai_get_retries_challenge_page(monkeypatch):
    """_akamai_get retries a challenge page like a 403 and returns None"""
    from types import SimpleNamespace

    from city_scrapers.mixins import sandie_nationalcity as mixin

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, content=b"<script>bm-verify</script>")

    monkeypatch.setattr(mixin.cffi_requests, "get", fake_get)
    monkeypatch.setattr(mixin.time, "sleep", lambda seconds: None)
    spider = SandieCityCouncilSpider()
    assert spider._akamai_get(spider.start_url) is None
    assert len(calls) == spider.akamai_retries
