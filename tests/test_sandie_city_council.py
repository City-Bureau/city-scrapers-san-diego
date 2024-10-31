from datetime import datetime
from os.path import dirname, join

import pytest  # noqa
from city_scrapers_core.constants import CITY_COUNCIL, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.sandie_city_council import SandieCityCouncilSpider

test_response = file_response(
    join(dirname(__file__), "files", "sandie_city_council.html"),
    url="https://www.sandiego.gov/city-clerk/officialdocs/meetings-calendar?calendar_timestamp=1706778000",  # noqa: E501
)
spider = SandieCityCouncilSpider()

freezer = freeze_time("2024-01-30")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


def test_count():
    assert len(parsed_items) == 25


def test_title():
    assert parsed_items[20]["title"] == "City Council"


def test_description():
    assert parsed_items[20]["description"] == ""


def test_start():
    assert parsed_items[20]["start"] == datetime(2024, 2, 26, 10, 0)


def test_end():
    assert parsed_items[20]["end"] is None


def test_time_notes():
    assert parsed_items[20]["time_notes"] == ""


def test_id():
    assert parsed_items[20]["id"] == "sandie_city_council/202402261000/x/city_council"


def test_status():
    assert parsed_items[20]["status"] == TENTATIVE


def test_location():
    assert parsed_items[20]["location"] == {
        "name": "San Diego City Administration Center",
        "address": "202 C Street, San Diego",
    }


def test_source():
    assert (
        parsed_items[20]["source"]
        == "https://www.sandiego.gov/city-clerk/officialdocs/meetings-calendar?calendar_timestamp=1706778000"  # noqa: E501
    )


def test_links():
    assert parsed_items[20]["links"] == [
        {
            "href": "https://sandiego.granicus.com/ViewPublisher.php?view_id=31",
            "title": "Webcasts",
        },
        {
            "href": "https://sandiego.hylandcloud.com/211agendaonlinecouncil",
            "title": "Meeting materials",
        },
    ]


def test_classification():
    assert parsed_items[20]["classification"] == CITY_COUNCIL


def test_all_day():
    assert parsed_items[20]["all_day"] is False
