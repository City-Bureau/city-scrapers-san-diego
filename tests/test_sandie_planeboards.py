from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_planeboards import ClairemontMesaSpider

test_response = file_response(
    join(dirname(__file__), "files", "sandie_clairemont_mesa.html"),
    url="https://www.sandiego.gov/planning/community-plans/clairemont-mesa/planning-group",  # noqa
)


@pytest.fixture
def parsed_items():
    spider = ClairemontMesaSpider()
    with freeze_time("2026-03-04"):
        return [item for item in spider.parse(test_response)]


def test_count(parsed_items):
    assert len(parsed_items) == 108


def test_title(parsed_items):
    assert parsed_items[0]["title"] == "Regular Meeting"


def test_description(parsed_items):
    assert parsed_items[0]["description"] == ""


def test_start(parsed_items):
    assert parsed_items[0]["start"] == datetime(2026, 2, 17, 18, 0)


def test_end(parsed_items):
    assert parsed_items[0]["end"] is None


def test_time_notes(parsed_items):
    assert (
        parsed_items[0]["time_notes"]
        == "Please refer to the meeting attachments for more accurate meeting time and location."  # noqa
    )


def test_status(parsed_items):
    assert parsed_items[0]["status"] == PASSED


def test_location(parsed_items):
    assert parsed_items[0]["location"] == {
        "name": "Cathy Hopper Clairemont Friendship Center",
        "address": "4425 Bannock Ave, San Diego, CA 92117",
    }


def test_links(parsed_items):
    assert parsed_items[0]["links"] == [
        {
            "href": "https://www.sandiego.gov/sites/default/files/2026-02/ccpg-02.17.2026-agenda.pdf",  # noqa
            "title": "Agenda",
        },
    ]


def test_classification(parsed_items):
    assert parsed_items[0]["classification"] == BOARD


def test_all_day(parsed_items):
    assert parsed_items[0]["all_day"] is False
