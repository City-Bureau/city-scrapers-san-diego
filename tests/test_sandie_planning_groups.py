from datetime import datetime, time
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED, COMMITTEE, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy import Request, signals
from scrapy.http import HtmlResponse
from scrapy.utils.test import get_crawler
from twisted.python.failure import Failure

from city_scrapers.spiders.sandie_planning_groups import (
    SandiePlanningGroupsError,
    SandiePlanningGroupsSpider,
)

BASE = "https://www.sandiego.gov"
CLAIREMONT_URL = f"{BASE}/planning/community-plans/clairemont-mesa/planning-group"
LJ_URL = f"{BASE}/planning/community-plans/la-jolla/planning-group"
GROUP = "Clairemont Mesa Community Planning Group"


def make_spider():
    """Spider wired to a test crawler, recording errors sent as spider_error."""
    crawler = get_crawler(SandiePlanningGroupsSpider)
    spider = SandiePlanningGroupsSpider.from_crawler(crawler)
    errors = []

    def on_spider_error(failure, response, spider):
        errors.append(failure.value)

    crawler.signals.connect(on_spider_error, signal=signals.spider_error, weak=False)
    return spider, crawler, errors


def close(spider, crawler, reason="finished"):
    crawler.signals.send_catch_log(
        signal=signals.spider_closed, spider=spider, reason=reason
    )


def html_response(url, body):
    return HtmlResponse(url=url, body=body.encode(), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Saved planning group page (Clairemont Mesa)
# --------------------------------------------------------------------------- #

test_response = file_response(
    join(dirname(__file__), "files", "sandie_clairemont_mesa.html"),
    url=CLAIREMONT_URL,
)


@pytest.fixture
def parsed_items():
    spider, _, _ = make_spider()
    with freeze_time("2026-03-04 12:00"):
        return list(spider.parse_group(test_response))


def test_count(parsed_items):
    # Meetings since 2024-03-04 (two years before the frozen date), including
    # 3 only listed under "Minutes"
    assert len(parsed_items) == 33


def test_lookback(parsed_items):
    assert min(i["start"] for i in parsed_items) == datetime(2024, 3, 19, 18, 0)


def test_title(parsed_items):
    assert parsed_items[0]["title"] == GROUP


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    # Time from the page's "Meeting Info" box: "6:00 p.m."
    assert parsed_items[0]["start"] == datetime(2026, 2, 17, 18, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] is None


def test_time_notes(parsed_items):
    assert (
        parsed_items[0]["time_notes"]
        == "Please refer to the meeting attachments for more accurate meeting time and location."  # noqa
    )


def test_id(parsed_items):
    assert (
        parsed_items[0]["id"]
        == "sandie_planning_groups/202602171800/x/clairemont_mesa_community_planning_group"  # noqa
    )
    assert len({item["id"] for item in parsed_items}) == len(parsed_items)


def test_status(parsed_items):
    assert parsed_items[0]["status"] == PASSED


def test_location(parsed_items):
    # From the page's "Meeting Info" box
    assert parsed_items[0]["location"] == {
        "name": "Cathy Hopper Clairemont Friendship Center",
        "address": "4425 Bannock Ave, San Diego, CA 92117",
    }


def test_source(parsed_items):
    assert parsed_items[0]["source"] == CLAIREMONT_URL


def test_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "href": "https://www.sandiego.gov/sites/default/files/2026-02/ccpg-02.17.2026-agenda.pdf",  # noqa
            "title": "Agenda",
        },
    ]


def test_links_with_minutes(parsed_items):
    item = next(i for i in parsed_items if i["start"] == datetime(2025, 11, 18, 18))
    assert [link["title"] for link in item["links"]] == ["Agenda", "Minutes"]


def test_minutes_only_meeting(parsed_items):
    item = next(i for i in parsed_items if i["start"] == datetime(2025, 7, 15, 18))
    assert item["title"] == GROUP
    assert [link["title"] for link in item["links"]] == ["Minutes"]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == BOARD
    committee = next(
        i
        for i in parsed_items
        if i["title"] == f"{GROUP} - Project Review Subcommittee"
    )
    assert committee["classification"] == COMMITTEE


def test_cancelled(parsed_items):
    # "October 15, 2024 - meeting adjourned"
    item = next(i for i in parsed_items if i["start"] == datetime(2024, 10, 15, 18))
    assert item["title"] == GROUP
    assert item["status"] == CANCELLED


def test_all_day(parsed_items):
    assert parsed_items[0]["all_day"] is False


# --------------------------------------------------------------------------- #
# Discovery: index -> community pages -> planning group pages
# --------------------------------------------------------------------------- #

INDEX = """<html><body><main>
<div id="tab-item-1"><div class="l-container"><ul>
  <li><a href="/planning/community-plans/clairemont-mesa">Clairemont Mesa</a></li>
  <li><a href="/planning/community-plans/black-mountain-ranch">BMR</a></li>
  <li><a href="/planning/community/profiles/downtown">Downtown</a></li>
  <li><a href="/planning/community-plans/east-elliott">East Elliott</a></li>
</ul></div></div>
</main></body></html>"""


def test_index_follows_every_community_and_extra_groups():
    spider, _, _ = make_spider()
    requests = list(spider.parse(html_response(spider.index_url, INDEX)))
    urls = [r.url for r in requests]
    assert urls == [
        f"{BASE}/planning/community-plans/clairemont-mesa",
        f"{BASE}/planning/community-plans/black-mountain-ranch",
        f"{BASE}/planning/community/profiles/downtown",
        f"{BASE}/planning/community-plans/east-elliott",
        f"{BASE}/planning/community-plans/community-planners-committee",
    ]
    assert requests[0].callback == spider.parse_community
    assert requests[-1].callback == spider.parse_group
    assert all(r.errback == spider._request_failed for r in requests)


def test_community_page_links_to_group_pages():
    spider, _, _ = make_spider()
    own = html_response(
        f"{BASE}/planning/community-plans/clairemont-mesa",
        '<a href="/planning/community-plans/clairemont-mesa/planning-group">Group</a>'
        '<a href="/planning/community-plans/planning-group-resources">Resources</a>',
    )
    # Black Mountain Ranch is covered by Rancho Penasquitos' group; the
    # downtown profile redirects to a page with an absolute link
    shared = html_response(
        f"{BASE}/planning/community-plans/black-mountain-ranch",
        f'<a href="{BASE}/planning/community-plans/rancho-penasquitos/planning-group">'
        "Group</a>",
    )
    torrey = html_response(
        f"{BASE}/planning/community-plans/torrey-highlands",
        f'<a href="{BASE}/planning/community-plans/rancho-penasquitos/planning-group/">'
        "Group</a>",
    )
    none = html_response(
        f"{BASE}/planning/community-plans/east-elliott",
        "<p>No active community planning group at this time.</p>",
    )
    urls = [
        r.url
        for page in (own, shared, torrey, none)
        for r in spider.parse_community(page)
    ]
    # Each group page is requested once, however many communities link to it
    assert urls == [
        CLAIREMONT_URL,
        f"{BASE}/planning/community-plans/rancho-penasquitos/planning-group",
    ]


def test_archived_group_pages_are_skipped():
    spider, _, _ = make_spider()
    page = html_response(
        f"{BASE}/planning/community-plans/sabre-springs",
        '<a href="/planning/community-plans/sabre-springs/planning-group">Group</a>',
    )
    assert list(spider.parse_community(page)) == []


def test_group_page_reached_twice_is_parsed_once():
    spider, _, _ = make_spider()
    with freeze_time("2026-03-04 12:00"):
        first = list(spider.parse_group(test_response))
        second = list(spider.parse_group(test_response))
    assert len(first) == 33
    assert second == []


# --------------------------------------------------------------------------- #
# Synthetic group pages: Meeting Info and agenda parsing edge cases
# --------------------------------------------------------------------------- #

LJ_INFO = "La Jolla Recreation Center<br>615 Prospect Street<br>La Jolla, CA 92037"


def build_page(
    agendas,
    minutes="",
    time_text="6:00 p.m.",
    location=LJ_INFO,
    include_info=True,
    heading="La Jolla Community Planning Group",
):
    info = ""
    if include_info:
        info = f"""<h2 class="heading--snug">Meeting Info</h2>
        <div class="grid-x">
          <div class="cell small-2"><p><i class="icon-clock3"></i></p></div>
          <div class="cell auto"><p>1<sup>st</sup> Thursday<br>{time_text}</p></div>
        </div>
        <div class="grid-x">
          <div class="cell small-2"><p><i class="icon-map-marker"></i></p></div>
          <div class="cell auto"><p>{location}</p></div>
        </div>"""
    body = f"""<html><body><main><h1>{heading}</h1>{info}
    <div id="tab-item-1"><div class="accordions">{agendas}</div></div>
    <div id="tab-item-2"><div class="accordions">{minutes}</div></div>
    </main></body></html>"""
    return html_response(LJ_URL, body)


def year_block(year, inner):
    return f"""<div class="accordion">
      <h3 class="accordion__heading"><a class="accordion__link">{year}</a></h3>
      <div class="accordion__drawer">{inner}</div></div>"""


ONE_MEETING = year_block(
    2026, '<ul><li><a href="/a/1.pdf">November 5, 2026</a></li></ul>'
)


def parse_page(response, now="2026-11-13 12:00"):
    """
    Parse one group page, then close the spider like Scrapy does. Returns the
    items and the error reported through spider_error on close (or None).
    """
    spider, crawler, errors = make_spider()
    with freeze_time(now):
        items = list(spider.parse_group(response))
    close(spider, crawler)
    assert len(errors) <= 1, "at most one error is reported per run"
    return items, (errors[0] if errors else None)


def find(items, start, title=None):
    return [
        i
        for i in items
        if i["start"] == start and (title is None or i["title"] == title)
    ]


@pytest.mark.parametrize(
    "time_text,location,expected_time,expected_location,expected_description",
    [
        (
            "6:00 p.m.",
            LJ_INFO,
            time(18, 0),
            {
                "name": "La Jolla Recreation Center",
                "address": "615 Prospect Street, La Jolla, CA 92037",
            },
            "",
        ),
        (
            "11:30 a.m.",
            "Virtual Meetings &#8211; See Agenda for Link",
            time(11, 30),
            {"name": "TBD", "address": ""},
            "Virtual Meetings \u2013 See Agenda for Link",
        ),
        (
            "12:00 p.m.",
            "Check the agenda for the meeting location",
            time(12, 0),
            {"name": "TBD", "address": ""},
            "Check the agenda for the meeting location",
        ),
        (
            "3:00 p.m.",
            "Virtual Meetings<br>&#8211; See Agenda for Link",
            time(15, 0),
            {"name": "TBD", "address": ""},
            "Virtual Meetings \u2013 See Agenda for Link",
        ),
        (
            "7:00 p.m.<br>Virtual Meetings - see agenda for Zoom link",
            "",
            time(19, 0),
            {"name": "TBD", "address": ""},
            "Virtual Meetings - see agenda for Zoom link",
        ),
        (
            "(Except August and December)<br>6:30 p.m.",
            "4772 Alvarado Canyon Rd<br>San Diego, CA 92120",
            time(18, 30),
            {"name": "", "address": "4772 Alvarado Canyon Rd, San Diego, CA 92120"},
            "",
        ),
        (
            "5:30 p.m.",
            'City Administration Building<br><a href="#">202 C Street, 12th Floor</a>'
            "<br>San Diego, CA 92101.",
            time(17, 30),
            {
                "name": "City Administration Building",
                "address": "202 C Street, 12th Floor, San Diego, CA 92101",
            },
            "",
        ),
        (
            "6:30 p.m.",
            "Earl &amp; Birdie Taylor Library<br>4275 Cass Street"
            "<br>San Diego, CA 92109",
            time(18, 30),
            {
                "name": "Earl & Birdie Taylor Library",
                "address": "4275 Cass Street, San Diego, CA 92109",
            },
            "",
        ),
    ],
)
def test_meeting_info(
    time_text, location, expected_time, expected_location, expected_description
):
    items, error = parse_page(
        build_page(ONE_MEETING, time_text=time_text, location=location)
    )
    assert items[0]["start"].time() == expected_time
    assert items[0]["location"] == expected_location
    assert items[0]["description"] == expected_description
    if location:
        assert error is None


def test_committee_group_classification():
    items, error = parse_page(
        build_page(
            year_block(
                2026,
                """<ul><li><a href="/a/1.pdf">October 27, 2026</a></li>
                <li><a href="/a/2.pdf">October 6, 2026 - Special Meeting</a></li>
                </ul>""",
            ),
            heading="Community Planners Committee (CPC)",
        )
    )
    assert error is None
    assert {(i["title"], i["classification"]) for i in items} == {
        ("Community Planners Committee (CPC)", COMMITTEE),
        ("Community Planners Committee (CPC) - Special Meeting", COMMITTEE),
    }


def test_group_name_override():
    spider, _, _ = make_spider()
    url = f"{BASE}/planning/community-plans/miramar-ranch-north/planning-group"
    page = build_page(ONE_MEETING, heading="Scripps Ranch Community Planning Group")
    with freeze_time("2026-11-13 12:00"):
        items = list(spider.parse_group(page.replace(url=url)))
    assert items[0]["title"] == (
        "Scripps Ranch Community Planning Group (Miramar Ranch North)"
    )


def test_date_variants():
    agendas = year_block(
        2026,
        """<ul>
        <li><a href="/a/1.pdf">February 10, &amp; 11 2026 - Subcommittee</a></li>
        <li><a href="/a/2.pdf">October 13 , 2026</a></li>
        <li>J<a href="/a/3.pdf">anuary 6, 2026 - Communications Subcommittee</a></li>
        <li><a href="/a/4.pdf">March 17 - Affordable Housing Task Force</a></li>
        <li><a href="/a/5.pdf">December 2, 202 - Traffic Subcommittee</a></li>
        <li><a href="/a/6.pdf">January 20, 2025</a></li>
        </ul>""",
    )
    items, error = parse_page(build_page(agendas))
    assert error is None
    assert {i["start"].date() for i in items} == {
        # "February 10, & 11"
        datetime(2026, 2, 10).date(),
        datetime(2026, 2, 11).date(),
        datetime(2026, 10, 13).date(),
        # "J" outside the link
        datetime(2026, 1, 6).date(),
        # Year taken from the accordion heading
        datetime(2026, 3, 17).date(),
        # Truncated year ("202") filled from the heading
        datetime(2026, 12, 2).date(),
        # January typo ("2025" under the 2026 heading) corrected
        datetime(2026, 1, 20).date(),
    }
    group = "La Jolla Community Planning Group"
    task_force = find(items, datetime(2026, 3, 17, 18))[0]
    assert task_force["title"] == f"{group} - Affordable Housing Task Force"
    assert task_force["classification"] == COMMITTEE
    assert find(items, datetime(2026, 12, 2, 18))[0]["title"] == (
        f"{group} - Traffic Subcommittee"
    )


def test_spanish_translation_attached_to_meeting():
    agendas = year_block(
        2025,
        """<ul>
        <li><a href="/a/en.pdf">September 8, 2025</a></li>
        <li> <ul><li><a href="/a/es.pdf">8 de septiembre de 2025</a></li></ul></li>
        </ul>""",
    )
    items, error = parse_page(build_page(agendas))
    assert error is None
    assert len(items) == 1
    assert [link["title"] for link in items[0]["links"]] == [
        "Agenda",
        "Agenda (Spanish)",
    ]


def test_titles_and_status():
    agendas = year_block(
        2025,
        """<ul>
        <li><a href="/a/1.pdf">October 15, 2025 - meeting adjourned</a></li>
        <li><a href="/a/2.pdf">September 11, 2025 - Project Review Subcommittee - Meeting Cancelled</a></li>
        <li><a href="/a/3.pdf">August 20, 2025 - Amended Agenda</a></li>
        <li><a href="/a/4.pdf">July 16, 2025 - Postponed</a></li>
        <li><a href="/a/5.pdf">June 18, 2025</a> with May minutes</li>
        <li><a href="/a/6_cancellation_notice.pdf">May 21, 2025</a></li>
        <li><a href="/a/7.pdf">April 16, 2025 - Special Meeting</a></li>
        <li><a href="/a/8.pdf">March 12, 2025 - English and Spanish</a></li>
        <li><a href="/a/9.pdf">February 10, 2025</a></li>
        <li> <ul><li><a href="/a/9es.pdf">10 de febrero de 2025 - Reunion Aplazada</a></li></ul></li>
        </ul>""",  # noqa
    )
    items, error = parse_page(build_page(agendas))
    assert error is None
    by_day = {i["start"].date(): i for i in items}
    group = "La Jolla Community Planning Group"

    def check(month, day, title, status):
        item = by_day[datetime(2025, month, day).date()]
        assert (item["title"], item["status"]) == (title, status)

    check(10, 15, group, CANCELLED)
    check(9, 11, f"{group} - Project Review Subcommittee", CANCELLED)
    check(8, 20, group, PASSED)
    check(7, 16, group, CANCELLED)
    check(6, 18, group, PASSED)
    check(5, 21, group, CANCELLED)
    check(4, 16, f"{group} - Special Meeting", PASSED)
    check(3, 12, group, PASSED)
    check(2, 10, group, CANCELLED)


# --------------------------------------------------------------------------- #
# Matching minutes (and translations) to the agenda of the same meeting
# --------------------------------------------------------------------------- #

LJ = "La Jolla Community Planning Group"


def links_by_meeting(items):
    """{meeting title (without group): [linked file names]} for one date."""
    return {
        i["title"]
        .replace(f"{LJ} - ", "")
        .replace(LJ, "Regular"): sorted(
            link["href"].rsplit("/", 1)[-1] for link in i["links"]
        )
        for i in items
    }


def ul(*items):
    return (
        "<ul>"
        + "".join(f'<li><a href="/f/{f}">{t}</a></li>' for t, f in items)
        + "</ul>"
    )


def test_minutes_matched_by_title_words():
    # "&" vs "and"; "Elections" vs "Annual Elections Meeting"
    agendas = year_block(
        2026,
        ul(
            ("July 21, 2026 - Traffic &amp; Transportation Board", "ljt-t-agenda.pdf"),
            ("July 21, 2026 - Development Permit Review Committee", "dpr-agenda.pdf"),
            ("March 9, 2026", "monthly-meeting-agenda.pdf"),
            ("March 9, 2026 - Annual Elections Meeting", "elections-agenda.pdf"),
        ),
    )
    minutes = year_block(
        2026,
        ul(
            ("July 21, 2026 - Traffic and Transportation Board", "ljttminutes.pdf"),
            ("March 9, 2026 - Elections", "x-minutes.pdf"),
        ),
    )
    items, error = parse_page(build_page(agendas, minutes))
    assert error is None
    assert links_by_meeting(items) == {
        "Traffic & Transportation Board": ["ljt-t-agenda.pdf", "ljttminutes.pdf"],
        "Development Permit Review Committee": ["dpr-agenda.pdf"],
        "Regular": ["monthly-meeting-agenda.pdf"],
        "Annual Elections Meeting": ["elections-agenda.pdf", "x-minutes.pdf"],
    }


def test_minutes_posted_in_agendas_tab_are_minutes():
    # CPC, 2026-04-28: the minutes file is listed in the Agendas tab
    agendas = year_block(
        2026,
        ul(
            ("April 28, 2026", "cpc-agenda-2026-april-28.pdf"),
            ("April 28, 2026", "cpc_approved-2026-april-28-meeting-minutes_0.pdf"),
        ),
    )
    items, error = parse_page(build_page(agendas))
    assert error is None
    assert len(items) == 1
    assert [link["title"] for link in items[0]["links"]] == ["Agenda", "Minutes"]


def test_different_committees_on_the_same_day_stay_apart():
    agendas = year_block(
        2025,
        ul(
            (
                "July 1, 2025 - Urban Design-Project Review Subcommittee",
                "udpr-agenda.pdf",
            )
        ),  # noqa
    )
    minutes = year_block(
        2025,
        ul(
            ("July 1, 2025 - Communications Subcommittee", "communications-minutes.pdf")
        ),  # noqa
    )
    items, error = parse_page(build_page(agendas, minutes))
    assert error is None
    assert links_by_meeting(items) == {
        "Urban Design-Project Review Subcommittee": ["udpr-agenda.pdf"],
        "Communications Subcommittee": ["communications-minutes.pdf"],
    }


def test_only_meeting_of_the_day_takes_generic_minutes():
    agendas = year_block(2025, ul(("October 8, 2025 - Special Meeting", "agenda.pdf")))
    minutes = year_block(2025, ul(("October 8, 2025", "minutes.pdf")))
    items, error = parse_page(build_page(agendas, minutes))
    assert error is None
    assert links_by_meeting(items) == {"Special Meeting": ["agenda.pdf", "minutes.pdf"]}


def test_main_board_aliases_are_the_regular_meeting():
    agendas = year_block(
        2026,
        ul(
            ("September 3, 2026 - LJCPA", "trustees_agenda.pdf"),
            ("November 5, 2026 - Trustee Meeting", "agenda_nov.pdf"),
            ("November 5, 2026 - Traffic &amp; Transportation Board", "ljtt.pdf"),
        ),
    )
    minutes = year_block(
        2026, ul(("September 3, 2026 - Trustee Meeting", "minutes.pdf"))
    )
    items, error = parse_page(build_page(agendas, minutes))
    assert error is None
    # "LJCPA" and "Trustee Meeting" are both the group's regular meeting
    assert sorted(i["title"] for i in items) == [
        LJ,
        LJ,
        f"{LJ} - Traffic & Transportation Board",
    ]
    september = find(items, datetime(2026, 9, 3, 18))[0]
    assert [link["href"].rsplit("/", 1)[-1] for link in september["links"]] == [
        "trustees_agenda.pdf",
        "minutes.pdf",
    ]


def test_non_meeting_entries_are_skipped_quietly():
    agendas = year_block(
        2026,
        """<ul>
        <li><a href="/a/1.pdf">November 5, 2026</a></li>
        <li>None posted</li>
        <li><a href="/a/2.pdf">June 2026 - Meeting Adjourned</a></li>
        <li><a href="/a/3.pdf">Press Release</a></li>
        </ul>""",
    )
    items, error = parse_page(build_page(agendas))
    assert error is None
    assert len(items) == 1


# --------------------------------------------------------------------------- #
# Fail loudly: major breakages are reported once, on spider_closed, through the
# `spider_error` signal (forwarded to Sentry); smaller problems are only logged
# --------------------------------------------------------------------------- #


def test_no_problems_reports_nothing():
    items, error = parse_page(build_page(ONE_MEETING))
    assert len(items) == 1
    assert error is None


def test_missing_community_list_reported():
    spider, crawler, errors = make_spider()
    requests = list(
        spider.parse(html_response(spider.index_url, "<html><body></body></html>"))
    )
    # The extra group pages are still requested
    assert [r.callback for r in requests] == [spider.parse_group]
    close(spider, crawler)
    assert len(errors) == 1
    assert "community list" in str(errors[0])
    assert "0 meetings parsed" in str(errors[0])


def test_missing_agenda_tab_on_one_page_only_logged(caplog):
    spider, crawler, errors = make_spider()
    other = LJ_URL.replace("la-jolla", "navajo")
    with freeze_time("2026-11-13 12:00"):
        broken = list(
            spider.parse_group(html_response(other, "<html><body></body></html>"))
        )
        items = list(spider.parse_group(build_page(ONE_MEETING)))
    close(spider, crawler)
    assert broken == [] and len(items) == 1
    assert "Agendas tab not found" in caplog.text
    assert errors == []


def test_missing_agenda_tab_everywhere_reported():
    items, error = parse_page(html_response(LJ_URL, "<html><body></body></html>"))
    assert items == []
    assert isinstance(error, SandiePlanningGroupsError)
    assert "0 meetings parsed" in str(error)


def test_missing_meeting_info_on_one_page_only_logged(caplog):
    spider, crawler, errors = make_spider()
    other = LJ_URL.replace("la-jolla", "navajo")
    with freeze_time("2026-11-13 12:00"):
        no_info = list(
            spider.parse_group(
                build_page(ONE_MEETING, include_info=False).replace(url=other)
            )
        )
        list(spider.parse_group(build_page(ONE_MEETING)))
    close(spider, crawler)
    # Still exported, at midnight with an unknown location
    assert no_info[0]["start"] == datetime(2026, 11, 5, 0, 0)
    assert no_info[0]["location"] == {"name": "TBD", "address": ""}
    assert "Could not read the meeting time" in caplog.text
    assert errors == []


def test_missing_meeting_info_everywhere_reported():
    items, error = parse_page(build_page(ONE_MEETING, include_info=False))
    assert len(items) == 1
    assert "'Meeting Info' time unreadable on every group page" in str(error)


def test_unparseable_dates_are_not_reported(caplog):
    agendas = year_block(
        2026,
        """<ul><li><a href="/a/1.pdf">November 5, 2026</a></li>
        <li><a href="/a/2.pdf">Octobr 1, 2026</a></li>
        <li><a href="/a/3.pdf">February 30, 2026</a></li></ul>""",
    )
    items, error = parse_page(build_page(agendas))
    assert len(items) == 1
    assert error is None
    assert "Invalid date: 2026-2-30" in caplog.text


def test_only_the_last_two_years_are_published():
    # Frozen at 2026-11-13 in San Diego: the cutoff is 2024-11-13
    agendas = (
        year_block(2026, ul(("November 5, 2026", "a.pdf")))
        + year_block(
            2024,
            ul(("December 10, 2024", "b.pdf"), ("November 12, 2024", "c.pdf")),
        )
        + year_block(2023, ul(("December 12, 2023", "d.pdf")))
    )
    items, error = parse_page(build_page(agendas))
    assert error is None
    assert sorted(i["start"].date() for i in items) == [
        datetime(2024, 12, 10).date(),
        datetime(2026, 11, 5).date(),
    ]


def test_failed_request_reported_once_on_close():
    spider, crawler, errors = make_spider()
    request = next(iter(spider.start_requests()))
    assert request.url == spider.index_url
    assert request.errback == spider._request_failed

    failure = Failure(ValueError("404"))
    failure.request = Request(LJ_URL)
    spider._request_failed(failure)
    spider._request_failed(failure)
    # Nothing is sent until the spider closes
    assert errors == []

    close(spider, crawler)
    assert len(errors) == 1
    assert str(errors[0]).count("request to") == 2
    assert "failed_requests=2" in str(errors[0])
    assert crawler.stats.get_value("spider_exceptions/SandiePlanningGroupsError") == 1


def test_lookback_uses_the_san_diego_date():
    # 2026-11-13 03:00 UTC is still 2026-11-12 in San Diego: cutoff 2024-11-12
    spider, _, _ = make_spider()
    with freeze_time("2026-11-13 03:00"):
        assert str(spider._lookback_cutoff()) == "2024-11-12"
    with freeze_time("2026-11-13 12:00"):
        assert str(spider._lookback_cutoff()) == "2024-11-13"
