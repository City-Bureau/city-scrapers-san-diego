from datetime import datetime, timedelta

import pytz
from city_scrapers_core.constants import CITY_COUNCIL, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from scrapy import Request


class SandieCityCouncilSpider(CityScrapersSpider):
    name = "sandie_city_council"
    agency = "San Diego City Council"
    timezone = "America/Los_Angeles"
    location = {
        "address": "202 C Street, San Diego",
        "name": "San Diego County Administration Center",
    }
    base_url = "https://www.sandiego.gov/city-clerk/officialdocs/meetings-calendar"

    def start_requests(self):
        """
        Generate URLs for the current and next month pages
        and yield scrapy Requests for them, with timestamps
        adjusted to 1am on the first of the month in Los Angeles time.
        """
        # Local timezone
        tz = pytz.timezone(self.timezone)

        # Get start of current month at 1 AM
        now = datetime.now(tz)
        start_of_current_month = datetime(now.year, now.month, 1, 1, 0)
        start_of_current_month = tz.localize(start_of_current_month)

        # Get start of next month at 1 AM
        next_month = start_of_current_month + timedelta(days=31)
        start_of_next_month = datetime(next_month.year, next_month.month, 1, 1, 0)
        start_of_next_month = tz.localize(start_of_next_month)

        # Generate timestamps for URLs
        current_month_ts = int(start_of_current_month.timestamp())
        next_month_ts = int(start_of_next_month.timestamp())

        # Generate URLs
        current_month_url = f"{self.base_url}?calendar_timestamp={current_month_ts}"
        next_month_url = f"{self.base_url}?calendar_timestamp={next_month_ts}"

        yield Request(url=current_month_url, callback=self.parse)
        yield Request(url=next_month_url, callback=self.parse)

    def parse(self, response):
        """
        Parse the calendar page and extract the events if there are any for a given day.
        """
        calendar = response.css(".calendar-view-table.calendar-view-month")
        for day in calendar.css("tbody tr td.current-month"):
            # get date
            date_obj = self._parse_date(day)

            # skip if no events
            events = day.css("ul li")
            if len(events) == 0:
                continue

            # loop through events
            for event in events:
                title = event.css("a::text").get()
                if "legislative recess" in title.lower():
                    continue
                meeting = Meeting(
                    title=title,
                    description="",
                    classification=self._parse_classification(title),
                    start=self._parse_start(date_obj, event),
                    end=None,
                    all_day=False,
                    time_notes="",
                    location=self.location,
                    links=self._parse_links(event),
                    source=self._parse_source(response),
                )
                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)
                yield meeting

    def _parse_date(self, day):
        """Parse the calendar date from the day element."""
        date_str = day.css(".calendar-view-day__number::attr('datetime')").get()
        date_part = date_str[:10]
        date_obj = datetime.strptime(date_part, "%Y-%m-%d").date()
        return date_obj

    def _parse_classification(self, title):
        """Parse classification from title."""
        clean_title = title.lower()
        if "council" in clean_title:
            return CITY_COUNCIL
        if "committee" in clean_title or "authority" in clean_title:
            return COMMITTEE
        return NOT_CLASSIFIED

    def _parse_start(self, date_obj, event):
        """Parse start datetime as a naive datetime object."""
        time_str = event.css("span.fine-print::text").get()
        time_obj = datetime.strptime(time_str, "%I:%M %p").time()
        return datetime.combine(date_obj, time_obj)

    def _parse_location(self, item):
        """Parse or generate location."""
        return

    def _parse_links(self, event):
        """Parse links."""
        links = [
            {
                "href": "https://sandiego.granicus.com/ViewPublisher.php?view_id=31",
                "title": "Webcasts",
            }
        ]
        agenda_link = event.css("a::attr('href')").get()
        if agenda_link:
            links.append({"href": agenda_link, "title": "Meeting materials"})
        return links

    def _parse_source(self, response):
        """Parse or generate source."""
        return response.url
