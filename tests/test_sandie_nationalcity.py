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
from scrapy import signals
from scrapy.http import HtmlResponse, TextResponse
from scrapy.utils.test import get_crawler
from twisted.python.failure import Failure

from city_scrapers.mixins.sandie_nationalcity import (
    NationalCityError,
    SandieNationalCityMixin,
)
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


with open(join(dirname(__file__), "files", "sandie_nationalcity_escribe.json")) as f:
    escribe_meetings = json.load(f)["d"]  # saved eSCRIBE calendar response

escribe_response = TextResponse(
    url="https://pub-nationalcity.escribemeetings.com"
    "/MeetingsCalendarView.aspx/GetCalendarMeetings",
    body=json.dumps({"d": escribe_meetings}).encode(),
    encoding="utf-8",
)


@pytest.fixture
def council_spider():
    return SandieCityCouncilSpider()


@pytest.fixture
def boards_spider():
    return SandieBoardsCommissionsSpider()


@pytest.fixture
def council_items(council_spider):
    """Meetings parse_escribe() yields for the saved eSCRIBE response"""
    with freeze_time("2026-09-25"):
        return list(council_spider.parse_escribe(escribe_response))


@pytest.fixture
def boards_results(boards_spider):
    """Everything parse() yields for the fixture page: meetings and the
    next-page request"""
    with freeze_time("2026-09-25"):
        return list(boards_spider.parse(test_response))


@pytest.fixture
def boards_items(boards_results):
    return [item for item in boards_results if isinstance(item, Meeting)]


def _by_start(items, start):
    return [item for item in items if item["start"] == start]


def _one(items, start):
    (item,) = _by_start(items, start)
    return item


# ============ City Council Spider Tests ============


def test_council_spider_configuration(council_spider):
    """Test that City Council spider is properly configured"""
    assert council_spider.name == "sandie_national_council_committees"
    assert council_spider.agency == "San Diego National City - City Council"
    assert council_spider.escribe_url == "https://pub-nationalcity.escribemeetings.com"

    assert council_spider.event_type is None


def test_spider_requires_event_type_or_escribe_url():
    with pytest.raises(NotImplementedError, match="event_type or escribe_url"):
        type("NoSourceSpider", (SandieNationalCityMixin,), {"name": "x", "agency": "X"})


@freeze_time("2026-09-25")
def test_council_start_requests_only_escribe(council_spider):
    """The council spider makes one request, to eSCRIBE, and never the website"""
    (request,) = list(council_spider.start_requests())
    assert request.method == "POST"
    assert request.url == (
        "https://pub-nationalcity.escribemeetings.com"
        "/MeetingsCalendarView.aspx/GetCalendarMeetings"
    )
    assert request.callback == council_spider.parse_escribe
    assert request.errback == council_spider._request_failed
    assert json.loads(request.body) == {
        "calendarStartDate": "2024-09-24",
        "calendarEndDate": "2027-09-24",
    }


def test_council_never_fetches_website(council_spider):
    """Crawling the council spider never touches the Akamai-protected site"""
    council_spider._akamai_get = lambda url: pytest.fail("website was fetched")
    for request in council_spider.start_requests():
        assert "nationalcityca.gov" not in request.url


def test_council_count(council_items):
    """The meeting before the 2024-09-24 cutoff is dropped; the other 6 are kept"""
    assert len(council_items) == 6
    assert not _by_start(council_items, datetime(2024, 9, 17, 18, 0))


def test_council_no_duplicates(council_items):
    assert len({item["id"] for item in council_items}) == len(council_items)


def test_council_title(council_items):
    """'Regular' and 'Cancellation Notice of a' are dropped from titles"""
    assert [item["title"] for item in council_items] == [
        "City Council Workshop",
        "Special City Council Meeting - Closed Session",
        "City Council Meeting",
        "Special City Council Meeting",
        "City Council Meeting",
        "City Council Meeting",
    ]


def test_council_start(council_items):
    assert [item["start"] for item in council_items] == [
        datetime(2026, 7, 21, 15, 0),
        datetime(2026, 9, 9, 13, 30),
        datetime(2026, 9, 15, 18, 0),
        datetime(2026, 9, 22, 17, 0),
        datetime(2026, 10, 6, 18, 0),
        datetime(2026, 11, 3, 18, 0),
    ]


def test_council_end(council_items):
    """eSCRIBE's EndDate (a scheduled block) is not used"""
    for item in council_items:
        assert item["end"] is None


def test_council_classification(council_items):
    for item in council_items:
        assert item["classification"] == CITY_COUNCIL


def test_council_abbreviated_title_is_city_council(council_spider):
    """Titles like "Special CC Meeting - ..." are still CITY_COUNCIL"""
    assert (
        council_spider._parse_escribe_classification(
            "Special CC Meeting - Certify Election - Incumbents Only"
        )
        == CITY_COUNCIL
    )


def test_council_status(council_items):
    """Past meetings are PASSED, upcoming ones TENTATIVE, and the
    "Cancellation Notice of a ..." meeting CANCELLED"""
    assert [item["status"] for item in council_items] == [
        PASSED,
        PASSED,
        PASSED,
        PASSED,
        TENTATIVE,
        CANCELLED,
    ]


def test_council_links(council_items):
    regular = _one(council_items, datetime(2026, 9, 15, 18, 0))
    assert regular["links"][0] == {
        "href": "https://pub-nationalcity.escribemeetings.com"
        "/FileStream.ashx?DocumentId=11499",
        "title": "Agenda Cover Page (PDF)",
    }
    # No agenda published yet: no links
    assert _one(council_items, datetime(2026, 10, 6, 18, 0))["links"] == []


def test_council_source(council_items):
    """Source is the meeting's eSCRIBE page, or the eSCRIBE portal if none"""
    regular = _one(council_items, datetime(2026, 9, 15, 18, 0))
    assert regular["source"] == (
        "https://pub-nationalcity.escribemeetings.com"
        "/Meeting?Id=2def99e5-4dd6-438a-b1ba-ccf55744c926"
    )
    upcoming = _one(council_items, datetime(2026, 10, 6, 18, 0))
    assert upcoming["source"] == "https://pub-nationalcity.escribemeetings.com"


def test_council_id(council_items):
    """Ids match those of the council meetings previously scraped from the
    website, e.g. the 9/15 City Council Meeting"""
    assert _one(council_items, datetime(2026, 9, 15, 18, 0))["id"] == (
        "sandie_national_council_committees/202609151800/x/city_council_meeting"
    )


def test_council_location(council_spider, council_items):
    """The Council Chamber maps to the default location; others keep their name"""
    assert _one(council_items, datetime(2026, 7, 21, 15, 0))["location"] == {
        "name": "Martin Luther King Jr. Community Center",
        "address": "",
    }
    for item in council_items:
        if item["start"] != datetime(2026, 7, 21, 15, 0):
            assert item["location"] == council_spider.location


@freeze_time("2026-09-25")
def test_council_unparseable_meeting_is_skipped(council_spider):
    """A meeting with a bad StartDate is skipped instead of crashing"""
    bad = dict(escribe_meetings[1], StartDate="TBD")
    items = list(council_spider._parse_escribe_meetings([bad, escribe_meetings[2]]))
    assert [item["start"] for item in items] == [datetime(2026, 9, 9, 13, 30)]
    assert council_spider._escribe_items_skipped == 1


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


def test_parse_yields_next_page_request(boards_results):
    """The fixture page has a Next link, so parse() also yields page 3"""
    requests = [r for r in boards_results if not isinstance(r, Meeting)]
    assert [r.url for r in requests] == [
        "https://www.nationalcityca.gov/government/boards-commissions-committees/-toggle-all/-sortn-EDate/-sortd-desc/-npage-3"  # noqa
    ]


def test_council_closed_to_public(council_items):
    """Only the "Closed Session" meeting is closed to the public"""
    assert [item["closed_to_public"] for item in council_items] == [
        False,
        True,
        False,
        False,
        False,
        False,
    ]


def test_boards_closed_to_public(boards_items):
    for item in boards_items:
        assert item["closed_to_public"] is ("closed" in item["title"].lower())


@freeze_time("2026-09-25")
def test_website_closed_session_is_closed_to_public():
    """Website meetings with "Closed" in the title are closed to the public"""
    body = b"""<table><tbody><tr>
        <td>Special Planning Commission Meeting - Closed Session</td>
        <td class="event_datetime">09/29/2026 5:00 PM</td>
    </tr></tbody></table>"""
    response = HtmlResponse(url=test_response.url, body=body, encoding="utf-8")
    (item,) = list(SandieBoardsCommissionsSpider().parse(response))
    assert item["closed_to_public"] is True


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
def test_meetings_before_cutoff_are_skipped(boards_spider):
    """Two years later the cutoff is 2026-09-25: only the meetings on the page
    from that date on are kept"""
    items = [r for r in boards_spider.parse(test_response) if isinstance(r, Meeting)]
    assert items
    assert all(item["start"] >= datetime(2026, 9, 25) for item in items)


# ============ curl-cffi Crawl Tests ============


@freeze_time("2026-09-25")
def test_run_crawl_fetches_listing_via_akamai_get(boards_items):
    """_run_crawl fetches listing pages through curl-cffi and yields meetings"""
    spider = SandieBoardsCommissionsSpider()
    fetched = []

    def fake_get(url):
        fetched.append(url)
        return test_response if url == spider.start_url else None

    spider._akamai_get = fake_get
    items = list(spider._run_crawl(None))

    # Page 1 (the fixture) is fetched, then its Next link (page 3)
    assert fetched == [spider.start_url, test_response.url.replace("-2", "-3")]
    assert items == boards_items
    # A blocked later page is not reported as a problem
    assert spider._problems == []
    assert spider._listing_pages == 1
    assert spider._meetings_parsed == len(boards_items)


@freeze_time("2026-09-25")
def test_run_crawl_blocked_first_listing_page_is_reported():
    """A blocked first listing page stops the crawl and is recorded as a
    problem (there is no eSCRIBE fallback)"""
    spider = SandieBoardsCommissionsSpider()
    assert spider.escribe_url is None
    spider._akamai_get = lambda url: None
    assert list(spider._run_crawl(None)) == []
    assert spider._failed_requests == 1
    assert spider._problems == [f"could not fetch listing page {spider.start_url}"]


def test_run_crawl_page_without_rows_is_reported():
    """A fetched page with no table rows means the layout changed"""
    spider = SandieBoardsCommissionsSpider()
    spider._akamai_get = lambda url: HtmlResponse(
        url=url, body=b"<html><body>No table</body></html>", encoding="utf-8"
    )
    assert list(spider._run_crawl(None)) == []
    assert "no meeting rows found" in spider._problems[0]


def test_boards_start_requests_use_website(boards_spider):
    (request,) = list(boards_spider.start_requests())
    assert request.url == "data:,"
    assert request.callback == boards_spider._run_crawl
    assert request.errback == boards_spider._request_failed


def test_row_without_start_date_is_skipped():
    """A matching row with no parseable date is skipped instead of crashing"""
    body = b"""<table><tbody><tr>
        <td>Planning Commission Meeting</td><td>TBD</td>
    </tr></tbody></table>"""
    response = HtmlResponse(url=test_response.url, body=body, encoding="utf-8")
    assert list(SandieBoardsCommissionsSpider().parse(response)) == []


def _live_row_response(datetime_cell, agenda_text=""):
    body = f"""<table><tbody><tr>
        <td>Planning Commission Meeting</td>
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
        agenda_text="2026 09-14 PC MIN",
    )
    items = list(SandieBoardsCommissionsSpider().parse(response))
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
    items = list(SandieBoardsCommissionsSpider().parse(response))
    assert items[0]["start"] == datetime(2026, 2, 19, 18, 0)
    assert items[0]["end"] == datetime(2026, 2, 19, 20, 0)


def _listing_page(url, date, title="Planning Commission Meeting"):
    body = f"""<table><tbody><tr>
        <td>{title}</td>
        <td class="event_datetime">{date} 6:00 PM</td>
    </tr></tbody></table>
        <a href="/government/boards-commissions-committees/-npage-99">Next</a>"""
    return HtmlResponse(url=url, body=body.encode(), encoding="utf-8")


def test_parse_follows_next_page_while_after_cutoff():
    """Pagination continues while the page's meetings are on/after the cutoff"""
    spider = SandieBoardsCommissionsSpider()
    date = spider._start_cutoff().strftime("%m/%d/%Y")
    results = list(spider.parse(_listing_page(test_response.url, date)))
    assert [r.url for r in results if hasattr(r, "callback")] == [
        "https://www.nationalcityca.gov/government/"
        "boards-commissions-committees/-npage-99"
    ]


def test_parse_stops_paging_before_cutoff():
    """Pagination stops once a page reaches meetings before the cutoff"""
    spider = SandieBoardsCommissionsSpider()
    date = (spider._start_cutoff() - timedelta(days=1)).strftime("%m/%d/%Y")
    assert list(spider.parse(_listing_page(test_response.url, date))) == []


def test_run_crawl_stops_at_cutoff():
    """_run_crawl fetches pages until one reaches meetings before the cutoff"""
    spider = SandieBoardsCommissionsSpider()
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


def _crawled_spider(spider_cls):
    """A spider attached to a crawler, recording the spider_error signals sent"""
    crawler = get_crawler(spider_cls)
    spider = spider_cls.from_crawler(crawler)
    spider.errors = []
    crawler.signals.connect(
        lambda failure, response, spider: spider.errors.append(failure.value),
        signal=signals.spider_error,
        weak=False,
    )
    return spider


def _close(spider, reason="finished"):
    spider.crawler.signals.send_catch_log(
        signal=signals.spider_closed, spider=spider, reason=reason
    )


@freeze_time("2026-09-25")
def test_no_error_reported_for_a_good_run():
    spider = _crawled_spider(SandieCityCouncilSpider)
    list(spider.parse_escribe(escribe_response))
    _close(spider)
    assert spider.errors == []


def test_zero_meetings_is_reported():
    spider = _crawled_spider(SandieCityCouncilSpider)
    _close(spider)
    (error,) = spider.errors
    assert isinstance(error, NationalCityError)
    assert "0 meetings parsed" in str(error)
    assert spider.crawler.stats.get_value("spider_exceptions/NationalCityError") == 1


def test_zero_meetings_not_reported_when_run_did_not_finish():
    """A run stopped early (e.g. shutdown) isn't reported for 0 meetings"""
    spider = _crawled_spider(SandieCityCouncilSpider)
    _close(spider, reason="shutdown")
    assert spider.errors == []


def test_unexpected_escribe_response_is_reported():
    spider = _crawled_spider(SandieCityCouncilSpider)
    response = TextResponse(
        url=escribe_response.url, body=b"<html>Error</html>", encoding="utf-8"
    )
    assert list(spider.parse_escribe(response)) == []
    _close(spider)
    (error,) = spider.errors
    assert "Unexpected eSCRIBE response" in str(error)
    assert "0 meetings parsed" in str(error)


def test_unparseable_escribe_meetings_are_reported():
    """Every meeting failing to parse means the API changed"""
    spider = _crawled_spider(SandieCityCouncilSpider)
    body = json.dumps({"d": [{"StartDate": "TBD", "MeetingName": "X"}]}).encode()
    response = TextResponse(url=escribe_response.url, body=body, encoding="utf-8")
    assert list(spider.parse_escribe(response)) == []
    _close(spider)
    assert "none of the 1 eSCRIBE meeting(s) could be parsed" in str(spider.errors[0])


def test_failed_escribe_request_is_reported():
    """A network/HTTP failure on the eSCRIBE request reaches the errback"""
    spider = _crawled_spider(SandieCityCouncilSpider)
    (request,) = list(spider.start_requests())
    failure = Failure(ConnectionRefusedError("refused"))
    failure.request = request
    request.errback(failure)
    _close(spider)
    (error,) = spider.errors
    assert f"request to {request.url} failed" in str(error)
    assert "failed_requests=1" in str(error)


def test_blocked_website_is_reported():
    spider = _crawled_spider(SandieBoardsCommissionsSpider)
    spider._akamai_get = lambda url: None
    list(spider._run_crawl(None))
    _close(spider)
    (error,) = spider.errors
    assert "could not fetch listing page" in str(error)
    assert "listing_pages=0" in str(error)


# ============ Akamai Challenge Page Tests ============


def test_akamai_challenge_page_is_detected(boards_spider):
    """A 200 with Akamai's JavaScript challenge (bm-verify) is not a real page"""
    with open(
        join(dirname(__file__), "files", "sandie_nationalcity_akamai_challenge.html"),
        "rb",
    ) as f:
        challenge = f.read()
    assert boards_spider._is_akamai_challenge(challenge)
    assert not boards_spider._is_akamai_challenge(test_response.body)


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
    spider = SandieBoardsCommissionsSpider()
    assert spider._akamai_get(spider.start_url) is None
    assert len(calls) == spider.akamai_retries
