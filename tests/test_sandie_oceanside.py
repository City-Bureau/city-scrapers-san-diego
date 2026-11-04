import re
from datetime import date, datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import CITY_COUNCIL, COMMISSION, COMMITTEE, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_oceanside import SandieOceansideSpider

test_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside.html"),
    url="https://www.ci.oceanside.ca.us/government/about-us/city-calendar/-curm-10/-cury-2026",  # noqa
)
test_detail_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_detail.html"),
    url="https://www.ci.oceanside.ca.us/Home/Components/Calendar/Event/3642/16",
)
test_council_detail_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_council_detail.html"),
    url="https://www.ci.oceanside.ca.us/Home/Components/Calendar/Event/2473/16",
)
test_legistar_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_legistar.html"),
    url="https://oceanside.legistar.com/Calendar.aspx",
)
test_records_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_records.html"),
    url="https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=16&DocumentTypeID=11&Search=Search",  # noqa
)
test_records_cioc_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_records_cioc.html"),
    url="https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=172&DocumentTypeID=173&Search=Search",  # noqa
)
test_records_ws_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_records_ws.html"),
    url="https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=184&DocumentTypeID=185&Search=Search",  # noqa
)
PFC = r"police and fire commission"
CIOC = r"citizen investment oversight committee"
WATER_SEWER = r"water[\s/-]*sewer"
test_records_uc_response = file_response(
    join(dirname(__file__), "files", "sandie_oceanside_records_uc.html"),
    url="https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=69&DocumentTypeID=116&Search=Search",  # noqa
)
UC = r"utilities commission"


@pytest.fixture(scope="module")
def parsed():
    # The context manager unfreezes time even if parsing raises, so frozen
    # time can't leak into other tests
    with freeze_time("2026-10-22"):
        spider = SandieOceansideSpider()

        legistar_events = spider._parse_legistar_events(test_legistar_response)
        list(spider.parse_legistar(legistar_events))
        list(spider.parse_records(test_records_response, body=PFC))
        list(spider.parse_records(test_records_cioc_response, body=CIOC))
        list(spider.parse_records(test_records_ws_response, body=WATER_SEWER))
        list(spider.parse_records(test_records_uc_response, body=UC))

        parsed_details = spider._parse_calendar(test_response)
        detail = next(
            d for d in parsed_details if d["source"] == test_detail_response.url
        )
        parsed_items = [spider._parse_detail(test_detail_response, **detail)]
        council_detail = next(
            d for d in parsed_details if d["source"] == test_council_detail_response.url
        )
        council_items = [
            spider._parse_detail(test_council_detail_response, **council_detail)
        ]

    return {
        "spider": spider,
        "legistar_events": legistar_events,
        "parsed_details": parsed_details,
        "detail": detail,
        "parsed_items": parsed_items,
        "council_items": council_items,
    }


@pytest.fixture(scope="module")
def spider(parsed):
    return parsed["spider"]


@pytest.fixture(scope="module")
def legistar_events(parsed):
    return parsed["legistar_events"]


@pytest.fixture(scope="module")
def parsed_details(parsed):
    return parsed["parsed_details"]


@pytest.fixture(scope="module")
def detail(parsed):
    return parsed["detail"]


@pytest.fixture(scope="module")
def parsed_items(parsed):
    return parsed["parsed_items"]


@pytest.fixture(scope="module")
def council_items(parsed):
    return parsed["council_items"]


CHALLENGE_HTML = """
<html><head><script> var i = 1792696350; var j = i + Number("8912" + "10911");
</script></head><body><script>
xhr.open("POST", "/_sec/verify?provider=interstitial", false);
xhr.send(JSON.stringify({"bm-verify": "AAQAAAAO/////abc+def==", "pow": j}));
</script></body></html>
"""

COUNCIL_LINKS = [
    {
        "href": "https://oceanside.legistar.com/View.ashx?M=A&ID=1355285&GUID=7F18C6DC-8088-47E1-B8A2-18FD726F0C82",  # noqa
        "title": "Agenda",
    },
    {
        "href": "https://oceanside.legistar.com/View.ashx?M=M&ID=1355285&GUID=7F18C6DC-8088-47E1-B8A2-18FD726F0C82",  # noqa
        "title": "Minutes",
    },
    {
        "href": "https://oceanside.legistar.com/Video.aspx?Mode=Granicus&ID1=100&Mode2=Video",  # noqa
        "title": "Video",
    },
    {
        "href": "https://oceanside.legistar.com/View.ashx?M=E1&ID=1355285&GUID=7F18C6DC-8088-47E1-B8A2-18FD726F0C82",  # noqa
        "title": "Español",
    },
]


def test_start_requests(spider):
    # Legistar and the records archive are requested up front; the calendar
    # follows on spider_idle
    assert [req.url for req in spider.start_requests()] == [
        "https://oceanside.legistar.com/Calendar.aspx",
        "https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=16&DocumentTypeID=11&Search=Search",  # noqa
        "https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=172&DocumentTypeID=173&Search=Search",  # noqa
        "https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=184&DocumentTypeID=185&Search=Search",  # noqa
        "https://records.ci.oceanside.ca.us/custom/filebank/archive-search-details.asp?DocumentTypeID=69&DocumentTypeID=116&Search=Search",  # noqa
    ]


def test_since_year():
    with freeze_time("2026-01-15"):
        assert SandieOceansideSpider().since_year == 2025
    with freeze_time("2026-10-22"):
        assert SandieOceansideSpider().since_year == 2025


def test_calendar_urls(spider):
    # 1 years back through 6 months ahead
    with freeze_time("2026-10-22"):
        urls = list(spider._calendar_urls())
    assert len(urls) == 19
    assert urls[0] == (
        "https://www.ci.oceanside.ca.us/government/about-us/city-calendar/-curm-10/-cury-2025"  # noqa
    )
    assert urls[-1] == (
        "https://www.ci.oceanside.ca.us/government/about-us/city-calendar/-curm-4/-cury-2027"  # noqa
    )


def test_calendar_count(parsed_details):
    # Community events, Arts/Youth/Historic Preservation commissions, Library
    # Board, etc. are filtered out
    assert len(parsed_details) == 8


def test_calendar_titles(parsed_details):
    assert [d["title"] for d in parsed_details] == [
        "Joint City Council/CDC/Harbor/OPFA Regular Meeting",
        "Planning Commission",
        "Cancelled - Economic Development Commission Meeting",
        "Police and Fire Commission Meeting",
        "Joint City Council/CDC/Harbor/OPFA Regular Meeting",
        "Community Relations Commission Standing Commission",
        "Planning Commission",
        "Housing Commission",
    ]


def test_calendar_source(parsed_details):
    # Query string (?curm=10&cury=2026) is dropped
    assert (
        parsed_details[0]["source"]
        == "https://www.ci.oceanside.ca.us/Home/Components/Calendar/Event/2473/16"
    )


def test_calendar_start(parsed_details):
    assert parsed_details[0]["start"] == datetime(2026, 10, 7, 15, 30)
    assert parsed_details[-1]["start"] == datetime(2026, 10, 27, 18, 15)


def _calendar_detail(event_id, title, start):
    return {
        "title": title,
        "start": start,
        "source": f"https://www.ci.oceanside.ca.us/Home/Components/Calendar/Event/{event_id}/16",  # noqa
    }


def test_dedupe_details(spider):
    crc = datetime(2025, 4, 1, 18, 0)
    workshop = datetime(2026, 4, 1, 17, 30)
    details = [
        _calendar_detail(1861, "Community Relations Commission", crc),
        _calendar_detail(3350, "Community Relations Commission", crc),
        _calendar_detail(3259, "Community Relations Commission", crc),
        _calendar_detail(2843, "Planning Commission Workshop", workshop),
        _calendar_detail(3072, "Planning Commission Interview Workshop", workshop),
        # Same meeting linked from the next month's page
        _calendar_detail(3072, "Planning Commission Interview Workshop", workshop),
    ]
    deduped = spider._dedupe_details(details)
    assert [d["source"].split("/")[-2] for d in deduped] == ["3350", "3072"]


def test_parse_detail_without_details(spider, detail):
    # Page without event details (e.g. unsolved Akamai challenge): no meeting
    blocked = file_response(
        join(dirname(__file__), "files", "sandie_oceanside.html"),
        url=test_detail_response.url,
    )
    assert spider._parse_detail(blocked, **detail) is None


def test_parse_challenge(spider):
    assert spider._parse_challenge(CHALLENGE_HTML) == {
        "bm-verify": "AAQAAAAO/////abc+def==",
        "pow": 1792696350 + 891210911,
    }
    assert spider._parse_challenge("<html>No challenge</html>") is None


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class FakeSession:
    """Serves the Akamai challenge until the solution is POSTed."""

    def __init__(self):
        self.verified = False
        self.posts = []

    def get(self, url, **kwargs):
        if self.verified:
            return FakeResponse("<ul class='detail-list'></ul>")
        return FakeResponse(CHALLENGE_HTML)

    def post(self, url, json=None, **kwargs):
        self.posts.append((url, json))
        self.verified = True
        return FakeResponse('{"reload": true}')


def test_fetch_solves_challenge():
    fetch_spider = SandieOceansideSpider()
    fetch_spider.request_delay = 0
    fetch_spider.session = FakeSession()
    html = fetch_spider._fetch_html(test_detail_response.url, referer="")
    assert "detail-list" in html
    assert fetch_spider.session.posts == [
        (
            "https://www.ci.oceanside.ca.us/_sec/verify?provider=interstitial",
            {"bm-verify": "AAQAAAAO/////abc+def==", "pow": 1792696350 + 891210911},
        )
    ]


def test_fetch_unsolved_challenge():
    fetch_spider = SandieOceansideSpider()
    fetch_spider.request_delay = 0
    fetch_spider.session = FakeSession()
    # Solution is POSTed but the challenge keeps coming back
    fetch_spider.session.post = lambda url, **kwargs: FakeResponse("")
    assert fetch_spider._fetch_html(test_detail_response.url, referer="") is None


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Police & Fire Commission Meeting", True),
        ("Police and Fire Commission Meeting", True),
        ("Utilities Commission Water-Sewer Committee Meeting", True),
        ("Water/Sewer Committee", True),
        ("Water-Sewer", True),
        ("Economic Development Commission", True),
        ("Planning Commission", True),
        ("Joint City Council/CDC/Harbor/OPFA Regular Meeting", True),
        ("Council Budget Workshop", True),
        ("Utilities Commission Budget Committee Meeting", False),
        ("Community Relations Commission", True),
        ("Housing Commission", True),
        ("Utilities Commission", True),
        ("Citizen Investment Oversight Committee Meeting", True),
        ("Arts Commission Meeting", False),
        ("Youth Commission", False),
        ("Downtown Advisory Committee", False),
        ("Halloween Trunk or Treat", False),
    ],
)
def test_is_relevant(title, expected, spider):
    assert spider._is_relevant(title) is expected


def test_count(parsed_items):
    assert len(parsed_items) == 1


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "Police and Fire Commission Meeting"


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2026, 10, 13, 17, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] == datetime(2026, 10, 13, 19, 0)


def test_time_notes(parsed_items):
    assert parsed_items[0]["time_notes"] == ""


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "sandie_oceanside/202610131700/x/police_and_fire_commission_meeting"
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == PASSED


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "Council Chambers - City Hall",
        "address": "300 N COAST HWY, OCEANSIDE, California 92054",
    }


def test_source(parsed_items):
    assert (
        parsed_items[0]["source"]
        == "https://www.ci.oceanside.ca.us/Home/Components/Calendar/Event/3642/16"
    )


def test_links(parsed_items):
    # Agenda and minutes from the records archive, matched by date. Staff
    # reports ("PFC SR 5biv") from the same date are skipped.
    assert parsed_items[0]["links"] == [
        {
            "href": "https://records.ci.oceanside.ca.us/civica/filebank/blobdload.asp?blobid=63876",  # noqa
            "title": "Agenda",
        },
        {
            "href": "https://records.ci.oceanside.ca.us/civica/filebank/blobdload.asp?blobid=63899",  # noqa
            "title": "Minutes",
        },
    ]


def test_records_links(spider):
    links = spider._records_links
    # Row without a file ("blobid=") is skipped
    assert [link["href"][-5:] for link in links[(PFC, date(2025, 12, 9))]] == [
        "63245",
        "63217",
        "63230",
    ]
    assert links[(PFC, date(2025, 12, 9))][0]["title"] == "12-9-2025 Minutes"
    # Only meetings of the same body get records links
    assert spider._get_records_links(datetime(2026, 10, 13, 15), "Housing") == []


def test_records_links_cioc(spider):
    links = spider._records_links
    meeting_title = "Citizen Investment Oversight Committee Meeting"
    # Matched by the date in the title, not the archive date (8/20/2024).
    # "01 SR CIOC Item #1 - Minutes" (no date in title) is skipped.
    assert spider._get_records_links(datetime(2024, 8, 13, 13, 30), meeting_title) == [
        {
            "href": "https://records.ci.oceanside.ca.us/civica/filebank/blobdload.asp?blobid=62044",  # noqa
            "title": "CIOC Minutes 08/13/2024",
        }
    ]
    assert [link["title"] for link in links[(CIOC, date(2026, 5, 12))]] == [
        "CIOC Minutes - May 12,2026"
    ]
    assert not any(
        "Item #1 - Minutes" in link["title"]
        for key, day_links in links.items()
        if key[0] == CIOC
        for link in day_links
    )
    # Police and Fire Commission files are not attached to CIOC meetings
    assert (PFC, date(2026, 8, 11)) in links
    assert spider._get_records_links(datetime(2026, 8, 11, 13, 30), meeting_title) == [
        {
            "href": "https://records.ci.oceanside.ca.us/civica/filebank/blobdload.asp?blobid=63755",  # noqa
            "title": "CIOC Minutes - August 11, 2026",
        }
    ]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("CIOC Minutes - May 12,2026", date(2026, 5, 12)),
        ("CIOC Minutes - August 11, 2026", date(2026, 8, 11)),
        ("CIOC November 14, 2023 Minutes", date(2023, 11, 14)),
        ("Minutes CIOC May 11th 2021", date(2021, 5, 11)),
        ("Minutes February 9th, 2021", date(2021, 2, 9)),
        ("SR CIOC Minutes 11/18/25", date(2025, 11, 18)),
        ("SR CIOC Minutes 08/12/2025", date(2025, 8, 12)),
        ("01 SR CIOC Minutes 05.28.25", date(2025, 5, 28)),
        ("01 11-08-2022 SR CIOC November 8 2022 Minutes", date(2022, 11, 8)),
        ("01 SR CIOC Item #1 - Minutes", None),
        ("09-08-26 UC WS Minutes", date(2026, 9, 8)),
        ("04-07-26 UC WS Agenda", date(2026, 4, 7)),
        ("UC WS Agenda 5.10.2022", date(2022, 5, 10)),
    ],
)
def test_parse_title_date(title, expected, spider):
    assert spider._parse_title_date(title) == expected


def _link_ids(links):
    return [link["href"].split("=")[-1] for link in links]


@pytest.mark.parametrize(
    "title",
    [
        "Utilities Commission Water-Sewer Committee Meeting",
        "Water/Sewer Committee",
    ],
)
def test_records_links_water_sewer(title, spider):
    # Both calendar titles are the Water/Sewer Committee. Matched by the date
    # in the title: the agenda was posted 4/6 and one set of minutes 4/2.
    assert _link_ids(
        spider._get_records_links(datetime(2026, 4, 7, 15, 30), title)
    ) == [
        "63503",
        "63466",
        "63450",
    ]


def test_records_links_water_sewer_not_utilities_commission(spider):
    assert (
        spider._get_records_links(datetime(2026, 4, 7, 14, 30), "Utilities Commission")
        == []
    )
    # "Notice of Cancelled Meeting" has no agenda or minutes in the title
    assert (WATER_SEWER, date(2026, 7, 14)) not in spider._records_links


@pytest.mark.parametrize(
    "title",
    ["Utilities Commission", "Utilities Commission Meeting"],
)
def test_records_links_utilities_commission(title, spider):
    # Matched by the date in the title: "01/20/26 UC Minutes" was posted 1/30
    assert _link_ids(
        spider._get_records_links(datetime(2026, 1, 20, 15, 30), title)
    ) == ["63316", "63286", "63279"]
    # Water/Sewer Committee files are not attached to the Utilities Commission
    assert _link_ids(
        spider._get_records_links(datetime(2026, 9, 15, 15, 30), title)
    ) == ["63826", "63822"]


def test_records_links_utilities_commission_skips(spider):
    # "09-15-26 Agenda" has no file; "05-21-24 UC Agen" style titles (no
    # "agenda" or "minutes") are skipped
    assert not any(
        not re.search(r"agenda|minutes", link["title"], flags=re.IGNORECASE)
        for key, links in spider._records_links.items()
        if key[0] == UC
        for link in links
    )


def test_council_links(council_items):
    assert council_items[0]["title"] == (
        "Joint City Council/CDC/Harbor/OPFA Regular Meeting"
    )
    assert council_items[0]["classification"] == CITY_COUNCIL
    assert council_items[0]["links"] == COUNCIL_LINKS


def test_legistar_events(legistar_events):
    assert len(legistar_events) == 23
    assert legistar_events[1]["Name"] == "City Council"
    assert legistar_events[1]["Meeting Date"] == "10/7/2026"
    assert legistar_events[1]["Meeting Time"] == "3:30 PM"


def test_legistar_links_not_available(spider):
    # Future meeting: no minutes yet ("Not available" has no link)
    oct_21 = spider._get_legistar_links(datetime(2026, 10, 21, 15, 30), CITY_COUNCIL)
    assert [link["title"] for link in oct_21] == ["Agenda", "Video", "Español"]


def test_legistar_links_matching(spider):
    # Same day, different time: falls back to the only Legistar meeting that day
    assert (
        spider._get_legistar_links(datetime(2026, 10, 7, 17, 0), CITY_COUNCIL)
        == COUNCIL_LINKS
    )
    # No Legistar meeting that day
    assert spider._get_legistar_links(datetime(2026, 10, 8, 15, 30), CITY_COUNCIL) == []
    # Only City Council meetings get Legistar links
    assert spider._get_legistar_links(datetime(2026, 10, 7, 15, 30), COMMISSION) == []


def test_fetch_meeting_retries(detail):
    retry_spider = SandieOceansideSpider()
    pages = [
        "<html>No details</html>",
        open(join(dirname(__file__), "files", "sandie_oceanside_detail.html")).read(),
    ]
    retry_spider._fetch_html = lambda url, referer: pages.pop(0)
    meeting = retry_spider._fetch_meeting(detail, referer="")
    assert meeting["title"] == "Police and Fire Commission Meeting"
    assert pages == []


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == COMMISSION


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Joint City Council/CDC/Harbor/OPFA Regular Meeting", CITY_COUNCIL),
        ("Housing Commission", COMMISSION),
        ("Citizen Investment Oversight Committee Meeting", COMMITTEE),
    ],
)
def test_parse_classification(title, expected, spider):
    assert spider._parse_classification(title) == expected


def test_all_day(parsed_items):
    assert parsed_items[0]["all_day"] is False
