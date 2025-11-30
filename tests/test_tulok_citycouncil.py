from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import CITY_COUNCIL, COMMITTEE, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.tulok_citycouncil import TulokCityCouncilSpider

# Test Granicus parser
test_response_granicus = file_response(
    join(dirname(__file__), "files", "tulok_citycouncil.html"),
    url="https://tulsa-ok.granicus.com/ViewPublisher.php?view_id=4",
)

# Test Archive parser
test_response_archive = file_response(
    join(dirname(__file__), "files", "tulok_citycouncil_archive.html"),
    url="https://www.cityoftulsa.org/apps/TulsaCouncilArchive/Home/Search",
)

spider = TulokCityCouncilSpider()

freezer = freeze_time("2025-11-01")
freezer.start()

parsed_items = [item for item in spider.parse_granicus(test_response_granicus)]
archive_items = [item for item in spider.parse_archive(test_response_archive)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 3


def test_title():
    assert parsed_items[0]["title"] == "Regular Council Meeting"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2025, 11, 19, 17, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "tulok_citycouncil/202511191700/x/regular_council_meeting"
    )


def test_status():
    assert parsed_items[0]["status"] == TENTATIVE


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "City Hall",
        "address": "175 East 2nd Street, Tulsa, OK 74103",
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "https://tulsa-ok.granicus.com/ViewPublisher.php?view_id=4"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://tulsa-ok.granicus.com/AgendaViewer.php?view_id=4&clip_id=7169",
            "title": "Agenda",
        }
    ]


def test_links_with_video():
    # Second item has a valid video link
    assert parsed_items[1]["links"] == [
        {
            "href": "https://tulsa-ok.granicus.com/AgendaViewer.php?view_id=4&clip_id=7168",
            "title": "Agenda",
        },
        {
            "href": "https://tulsa-ok.granicus.com/MediaPlayer.php?view_id=4&clip_id=7168",
            "title": "Video",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == CITY_COUNCIL


def test_all_day():
    assert parsed_items[0]["all_day"] is False


# Archive parser tests
def test_archive_count():
    assert len(archive_items) == 5


def test_archive_title():
    assert archive_items[0]["title"] == "Urban And Economic Development Committee"


def test_archive_committee_classification():
    assert archive_items[0]["classification"] == COMMITTEE
    assert archive_items[1]["classification"] == COMMITTEE
    assert archive_items[2]["classification"] == COMMITTEE


def test_archive_council_classification():
    assert archive_items[3]["classification"] == CITY_COUNCIL
    assert archive_items[4]["classification"] == CITY_COUNCIL


def test_archive_start():
    assert archive_items[0]["start"] == datetime(2024, 11, 20, 10, 30)
    assert archive_items[1]["start"] == datetime(2024, 11, 20, 13, 0)


def test_archive_links():
    # Check that agenda links are properly formed
    assert any(
        "DocumentType=Agenda" in link["href"] and link["href"].startswith("https://")
        for link in archive_items[0]["links"]
    )


def test_archive_location():
    assert archive_items[0]["location"] == {
        "name": "City Hall",
        "address": "175 East 2nd Street, Tulsa, OK 74103",
    }
