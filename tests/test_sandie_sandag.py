from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_sandag import SandagBoardOfDirectorsCommitteesSpider

test_response = file_response(
    join(dirname(__file__), "files", "sandie_sandag.json"),
    url="https://pub-sandag.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings?FillWidth=1&MeetingviewId=2",  # noqa
)
spider = SandagBoardOfDirectorsCommitteesSpider()

freezer = freeze_time("2026-10-19")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 6


def test_duplicates_skipped():
    # Same meetings listed under another meeting view are not yielded twice
    assert list(spider.parse(test_response)) == []


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
        == "sandag_board_of_directors_committees/202609110900/x/board_of_directors"
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
