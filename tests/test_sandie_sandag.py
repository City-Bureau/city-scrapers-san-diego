from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CANCELLED,
    COMMITTEE,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_sandag import (
    SandagBoardOfDirectorsCommitteesSpider,
    SandagTransNetIndependentTaxpayerOversightCommitteeSpider,
)


def sandag_response(filename, view_id):
    return file_response(
        join(dirname(__file__), "files", filename),
        url=f"https://pub-sandag.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings?FillWidth=1&MeetingviewId={view_id}",  # noqa
    )


def parse_views(spider_cls, *responses):
    """Parse responses in order with a fresh spider, as one crawl would."""
    fresh_spider = spider_cls()
    with freeze_time("2026-10-19"):
        return [item for resp in responses for item in fresh_spider.parse(resp)]


test_response = sandag_response("sandie_sandag.json", 2)
spider = SandagBoardOfDirectorsCommitteesSpider()

freezer = freeze_time("2026-10-19")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 6


def test_title():
    assert parsed_items[0]["title"] == "Board of Directors"
    assert parsed_items[4]["title"] == "Board of Directors - Special Session"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 9, 11, 9, 0)


def test_end():
    assert parsed_items[0]["end"] == datetime(2026, 9, 11, 12, 30)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "sandie_sandag_board_of_directors_committees/202609110900/x/board_of_directors"  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == PASSED
    assert parsed_items[2]["status"] == CANCELLED
    assert parsed_items[5]["status"] == TENTATIVE


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "SANDAG Boardroom",
        "address": "1011 Union Street, First Floor, San Diego, CA 92101",
    }


def test_location_strips_html():
    item = {
        "Location": "<strong>SANDAG Boardroom</strong>",
        "Description": "<p><strong>SANDAG Boardroom</strong><br/>"
        "1011 Union Street &amp; First Floor</p>",
    }
    assert spider._parse_location(item) == {
        "name": "SANDAG Boardroom",
        "address": "1011 Union Street & First Floor",
    }


def test_location_fallback():
    assert parsed_items[3]["location"] == {"name": "TBD", "address": ""}


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://www.sandag.org/meetings-and-events/board-of-directors"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://pub-sandag.escribemeetings.com/FileStream.ashx?DocumentId=17441",  # noqa
            "title": "Agenda Cover Page (PDF)",
        },
        {
            "href": "https://pub-sandag.escribemeetings.com/FileStream.ashx?DocumentId=17658",  # noqa
            "title": "Agenda (PDF)",
        },
        {
            "href": "https://pub-sandag.escribemeetings.com/FileStream.ashx?DocumentId=18336",  # noqa
            "title": "Minutes (PDF)",
        },
        {
            "href": "https://pub-sandag.escribemeetings.com/Meeting.aspx?Id=866a4277-4f81-423c-a0cb-8fdb13bcced3&Agenda=PostMinutes&lang=English",  # noqa
            "title": "Minutes (HTML)",
        },
        {
            "href": "https://www.youtube.com/watch?v=Z-wrD15d6mg",
            "title": "Video",
        },
        {
            "href": "https://pub-sandag.escribemeetings.com/FileStream.ashx?DocumentId=17443",  # noqa
            "title": "Orden del dia - BOD_Sep11_2026",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False


# Joint meeting dd5b1476 is listed under both Transportation (7) and
# Regional Planning (6) views
transportation_response = sandag_response("sandie_sandag_transportation.json", 7)
regional_planning_response = sandag_response("sandie_sandag_regional_planning.json", 6)
JOINT_MEETING_START = datetime(2025, 9, 19, 9, 0)


def test_duplicates_across_views_skipped():
    items = parse_views(
        SandagBoardOfDirectorsCommitteesSpider,
        transportation_response,
        regional_planning_response,
    )
    assert [item["title"] for item in items] == [
        "Transportation Committee",
        "Joint Policy Advisory Committee",
        "Regional Planning Committee",
    ]


def test_duplicate_source_from_first_view():
    items = parse_views(
        SandagBoardOfDirectorsCommitteesSpider,
        regional_planning_response,
        transportation_response,
    )
    joint = [item for item in items if item["start"] == JOINT_MEETING_START]
    assert len(joint) == 1
    assert (
        joint[0]["source"]
        == "https://www.sandag.org/meetings-and-events/policy-advisory-committees/regional-planning"  # noqa
    )


def test_committee_classification():
    items = parse_views(SandagBoardOfDirectorsCommitteesSpider, transportation_response)
    assert items[0]["classification"] == COMMITTEE
    assert items[1]["classification"] == ADVISORY_COMMITTEE


def test_itoc():
    items = parse_views(
        SandagTransNetIndependentTaxpayerOversightCommitteeSpider,
        sandag_response("sandie_sandag_itoc.json", 15),
    )
    assert len(items) == 2
    assert items[0]["title"] == "TransNet Independent Taxpayer Oversight Committee"
    assert items[0]["start"] == datetime(2026, 9, 9, 9, 30)
    assert (
        items[0]["source"]
        == "https://www.sandag.org/meetings-and-events/transnet-independent-taxpayer-oversight"  # noqa
    )
    assert items[1]["title"] == (
        "TransNet Independent Taxpayer Oversight Committee Selection Committee"
    )
    assert all(item["classification"] == COMMITTEE for item in items)
