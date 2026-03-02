from datetime import datetime
from os.path import dirname, join

from city_scrapers_core.constants import BOARD, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_planeboards import ClairemontMesaSpider

test_response = file_response(
    join(dirname(__file__), "files", "sandie_clairemont_mesa.html"),
    url="https://www.sandiego.gov/planning/community-plans/clairemont-mesa/planning-group",  # noqa
)

spider = ClairemontMesaSpider()

freezer = freeze_time("2026-02-27")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_title():
    assert parsed_items[0]["title"] == "Regular Meeting"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2026, 2, 17, 18, 0)


def test_end():
    assert parsed_items[0]["end"] is None


def test_time_notes():
    assert (
        parsed_items[0]["time_notes"]
        == "Please refer to the meeting attachments for more accurate meeting time and location."  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == PASSED


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "Cathy Hopper Clairemont Friendship Center",
        "address": "4425 Bannock Ave San Diego, CA 92117",
    }


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://www.sandiego.gov/sites/default/files/2026-02/ccpg-02.17.2026-agenda.pdf", # noqa
            "title": "Agenda",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


def test_all_day():
    assert parsed_items[0]["all_day"] is False
