import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, urljoin

import pytz
from city_scrapers_core.constants import (
    CANCELLED,
    CITY_COUNCIL,
    COMMITTEE,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from scrapy import Request, Selector


class SandieCityCouncilSpider(CityScrapersSpider):
    name = "sandie_city_council"
    agency = "San Diego City Council"
    timezone = "America/Los_Angeles"
    location = {
        "address": "202 C Street, San Diego",
        "name": "San Diego City Administration Center",
    }
    base_url = "https://www.sandiego.gov/city-clerk/officialdocs/meetings-calendar"
    ajax_url = (
        "https://www.sandiego.gov/views/ajax?_wrapper_format=drupal_ajax"
        "&view_name=legis_calendar&view_display_id=default"
        "&view_args=&view_path=%2Fnode%2F226394"
    )
    video_base_url = "https://sandiego.granicus.com/"
    # Granicus archived video view_ids for the City Council and its committees,
    # from the Active Meetings table at
    # https://www.sandiego.gov/city-clerk/officialdocs/webcasts
    # Keys are lowercase with "&" spelled out, to match against meeting titles.
    video_view_ids = {
        "city council": 3,
        "active transportation and infrastructure committee": 47,
        "ad hoc committee on the recruitment of the executive director of the commission on police practices": 67,  # noqa: E501
        "audit committee": 24,
        "budget and government efficiency committee": 53,
        "budget review committee": 54,
        "community and neighborhood services committee": 64,
        "economic development and intergovernmental relations committee": 49,
        "environment committee": 51,
        "land use and housing committee": 12,
        "public safety committee": 52,
        "rules committee": 11,
    }
    # Bodies on the calendar and documents search that have no archived videos
    other_bodies = [
        "closed session",
        "housing authority",
        "public facilities financing authority",
    ]
    documents_url = (
        "https://sandiego.hylandcloud.com/211agendaonlinecomm/Meetings/Search"
    )
    # Meeting type ids for the City Council committees on the documents search
    documents_mtids = (
        "131,135,114,119,102,116,115,127,133,122,120,121,132,123,117,134,118"
    )
    council_documents_url = (
        "https://sandiego.hylandcloud.com/211agendaonlinecouncil/Meetings/Search"
    )
    # Meeting type ids for City Council, Closed Session, Housing Authority and
    # the other bodies on the City Council documents search
    council_documents_mtids = "101,103,106,105,107,108,109,110,113,129,130"

    # sandiego.granicus.com/robots.txt disallows all paths for generic crawlers
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # (view_id, date, is_special) -> MediaPlayer URL
        self.video_links = {}
        # (body, date, is_special) -> list of agenda, actions, summary and
        # comment links
        self.document_links = {}

    def start_requests(self):
        """
        Fetch each body's archived videos page one after another, then the
        committee and City Council documents, then the calendar months, so
        video and document links are known when meetings are built.
        """
        yield self._video_request(list(self.video_view_ids.values()))

    def _video_request(self, view_ids):
        return Request(
            url=f"{self.video_base_url}ViewPublisher.php?view_id={view_ids[0]}",
            callback=self.parse_videos,
            errback=self._video_errback,
            cb_kwargs={"view_id": view_ids[0], "remaining": view_ids[1:]},
            dont_filter=True,
        )

    def _video_errback(self, failure):
        """Keep going without this body's videos if its page fails."""
        self.logger.warning(f"Failed to fetch videos: {failure.request.url}")
        yield from self._next_requests(failure.request.cb_kwargs["remaining"])

    def _next_requests(self, remaining):
        if remaining:
            yield self._video_request(remaining)
        else:
            yield self._documents_request(
                [
                    (self.documents_url, self.documents_mtids),
                    (self.council_documents_url, self.council_documents_mtids),
                ]
            )

    def _documents_request(self, searches):
        """Search documents over the same months as the calendar."""
        url, mtids = searches[0]
        start, end = self._date_range()
        params = {
            "dropid": 11,
            "mtids": mtids,
            "dropsv": start.strftime("%m/%d/%Y %H:%M:%S"),
            "dropev": end.strftime("%m/%d/%Y %H:%M:%S"),
        }
        return Request(
            url=f"{url}?{urlencode(params)}",
            callback=self.parse_documents,
            errback=self._documents_errback,
            cb_kwargs={"remaining": searches[1:]},
            dont_filter=True,
        )

    def _documents_errback(self, failure):
        """Keep going without these documents if the search fails."""
        self.logger.warning(f"Failed to fetch documents: {failure.request.url}")
        yield from self._next_documents_requests(failure.request.cb_kwargs["remaining"])

    def _next_documents_requests(self, remaining):
        if remaining:
            yield self._documents_request(remaining)
        else:
            yield from self._calendar_requests()

    def parse_documents(self, response, remaining=()):
        """
        Collect agenda, actions, summary and public comment links from a
        documents search. Public comments are listed as their own meeting, so
        links are grouped by body and date.
        """
        links_found = response.css("#meetings-list a[href][title]")
        if not links_found:
            self.logger.warning(f"No documents found, check the page: {response.url}")
        for link in links_found:
            # The title names the body and date, e.g. "View Agenda for ...
            # Land Use and Housing Committee on 10/16/2026 1:00:00 PM". Only the
            # first meeting on a date has a visible date, so use the title's.
            title = link.attrib["title"]
            date_match = re.search(r" on (\d{1,2}/\d{1,2}/\d{4}) ", title)
            if not date_match:
                self.logger.warning(f"Skipping document with no date: {title}")
                continue
            body = self._parse_body(title)
            if body is None:
                # A body missing from video_view_ids or other_bodies
                self.logger.warning(f"Skipping document for unknown body: {title}")
                continue
            date_obj = datetime.strptime(date_match.group(1), "%m/%d/%Y").date()
            # Documents with "special" in the title belong to the special meeting
            key = (body, date_obj, self._is_special_meeting(title))
            links = self.document_links.setdefault(key, [])
            href = response.urljoin(link.attrib["href"])
            # Meetings can be listed under both the upcoming and recent tabs
            if href in [existing["href"] for existing in links]:
                continue
            links.append(
                {
                    "href": href,
                    "title": " ".join(link.css("::text").get("").split()),
                }
            )
        yield from self._next_documents_requests(list(remaining))

    def _date_range(self):
        """Start of the previous month and start of the month after next."""
        now = datetime.now(pytz.timezone(self.timezone))
        start = (datetime(now.year, now.month, 1) - timedelta(days=1)).replace(day=1)
        end = (datetime(now.year, now.month, 1) + timedelta(days=62)).replace(day=1)
        return start, end

    def parse_videos(self, response, view_id, remaining):
        """
        Collect clip links from a Granicus archived videos page. Clips only list
        a date, so they're keyed by body, date and whether it's a special meeting.
        """
        rows = response.css("table#nosearch tbody tr")
        if not rows:
            self.logger.warning(f"No videos found, check the page: {response.url}")
        for row in rows:
            cells = row.css("td")
            onclick = row.css("a::attr(onclick)").get() or ""
            clip = re.search(r"MediaPlayer\.php\?view_id=\d+&clip_id=\d+", onclick)
            if len(cells) < 2 or not clip:
                continue
            title = " ".join(cells[0].xpath("string()").get().split())
            date_str = " ".join(cells[1].xpath("string()").get().split())
            try:
                date_obj = datetime.strptime(date_str, "%b %d, %Y").date()
            except ValueError:
                self.logger.warning(
                    f"Skipping video with unparsable date {date_str!r}: {title}"
                )
                continue
            key = (view_id, date_obj, self._is_special_meeting(title))
            # Rows are newest first; keep the first clip for a key
            self.video_links.setdefault(key, urljoin(self.video_base_url, clip.group()))
        yield from self._next_requests(remaining)

    def _calendar_requests(self):
        """
        Generate URLs for the previous, current and next month pages
        and yield scrapy Requests for them, with timestamps
        adjusted to 1am on the first of the month in Los Angeles time.
        """
        # Local timezone
        tz = pytz.timezone(self.timezone)

        # Get start of current month at 1 AM
        now = datetime.now(tz)
        start_of_current_month = datetime(now.year, now.month, 1, 1, 0)

        # Get start of previous month at 1 AM
        prev_month = start_of_current_month - timedelta(days=1)
        start_of_prev_month = datetime(prev_month.year, prev_month.month, 1, 1, 0)

        # Get start of next month at 1 AM
        next_month = start_of_current_month + timedelta(days=31)
        start_of_next_month = datetime(next_month.year, next_month.month, 1, 1, 0)

        for month_start in [
            start_of_prev_month,
            start_of_current_month,
            start_of_next_month,
        ]:
            # Generate timestamp for URL. The calendar page itself now redirects
            # away any calendar_timestamp param, so request the month through
            # the Drupal Views AJAX endpoint that the page's prev/next links use.
            month_ts = int(tz.localize(month_start).timestamp())
            url = f"{self.ajax_url}&calendar_timestamp={month_ts}"
            # Without this header Drupal wraps the JSON in a <textarea>
            yield Request(
                url=url,
                headers={"Accept": "application/json"},
                callback=self.parse_ajax_calendar,
            )

    def parse_ajax_calendar(self, response):
        """
        Pull the calendar HTML out of the Views AJAX JSON response and parse it.
        """
        try:
            commands = response.json()
        except ValueError:
            self.logger.warning(f"Calendar response is not JSON: {response.url}")
            return
        found = False
        for command in commands:
            html = command.get("data")
            if isinstance(html, str) and "calendar-view-month" in html:
                found = True
                yield from self._parse_calendar(Selector(text=html), self.base_url)
        if not found:
            self.logger.warning(f"No calendar found in response: {response.url}")

    def parse(self, response):
        """
        Parse a calendar HTML page.
        """
        yield from self._parse_calendar(response, self._parse_source(response))

    def _parse_calendar(self, selector, source):
        """
        Parse the calendar and extract the events if there are any for a given day.
        """
        calendar = selector.css(".calendar-view-table.calendar-view-month")
        if not calendar:
            self.logger.warning(f"No calendar table found, check the page: {source}")
        for day in calendar.css("tbody tr td.current-month"):
            # skip if no events
            events = day.css("ul li")
            if len(events) == 0:
                continue

            # get date
            date_obj = self._parse_date(day)
            if date_obj is None:
                self.logger.warning(
                    f"Skipping {len(events)} meeting(s) on a day with no date: {source}"
                )
                continue

            # loop through events
            for event in events:
                title = " ".join((event.css("a::text").get() or "").split())
                if not title:
                    self.logger.warning(f"Skipping meeting with no title on {date_obj}")
                    continue
                if "legislative recess" in title.lower():
                    continue
                start = self._parse_start(date_obj, event)
                if start is None:
                    self.logger.warning(
                        f"Skipping meeting with no start time: {title} on {date_obj}"
                    )
                    continue
                meeting = Meeting(
                    title=title,
                    description="",
                    classification=self._parse_classification(title),
                    start=start,
                    end=None,
                    all_day=False,
                    closed_to_public="closed session" in title.lower(),
                    time_notes="",
                    location=self.location,
                    links=self._parse_links(date_obj, title),
                    source=source,
                )
                meeting["status"] = self._parse_status(meeting)
                meeting["id"] = self._get_id(meeting)
                yield meeting

    def _parse_status(self, meeting):
        """
        "Adjourned" in a calendar title means the meeting was called off, with an
        adjournment memo in place of an agenda, so it's cancelled.
        """
        if "adjourned" in meeting["title"].lower():
            return CANCELLED
        return self._get_status(meeting)

    def _parse_date(self, day):
        """Parse the calendar date from the day element, or None if it's missing."""
        date_str = day.css(".calendar-view-day__number::attr('datetime')").get("")
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _parse_classification(self, title):
        """Parse classification from title."""
        clean_title = title.lower()
        if "council" in clean_title:
            return CITY_COUNCIL
        if "committee" in clean_title or "authority" in clean_title:
            return COMMITTEE
        return NOT_CLASSIFIED

    def _parse_start(self, date_obj, event):
        """Parse start datetime as a naive datetime object, or None if the time is
        missing."""
        time_str = event.css("span.fine-print::text").get("").strip()
        try:
            time_obj = datetime.strptime(time_str, "%I:%M %p").time()
        except ValueError:
            return None
        return datetime.combine(date_obj, time_obj)

    def _parse_location(self, item):
        """Parse or generate location."""
        return

    def _normalize_title(self, title):
        return " ".join(title.lower().replace("&", "and").split())

    def _is_special_meeting(self, title):
        return "special" in title.lower()

    def _parse_body(self, title):
        """Find the body a meeting or document title belongs to."""
        clean_title = self._normalize_title(title)
        bodies = list(self.video_view_ids) + self.other_bodies
        matches = [name for name in bodies if name in clean_title]
        if not matches:
            return None
        # Prefer the most specific body, e.g. a committee over "city council".
        # City Council documents name every body as "... City Council", e.g.
        # "Housing Authority City Council".
        return max(matches, key=len)

    def _parse_view_id(self, title):
        """Find the Granicus view_id of the body a meeting title belongs to."""
        return self.video_view_ids.get(self._parse_body(title))

    def _parse_links(self, date_obj, title):
        """
        Parse document and video links. The calendar's own links aren't used:
        they're mostly general pages, like the OnBase home page, and the ones
        to a single meeting are also found by the documents search.
        """
        body = self._parse_body(title)
        view_id = self._parse_view_id(title)
        is_special = self._is_special_meeting(title)
        links = list(self.document_links.get((body, date_obj, is_special), []))
        # City Council can meet twice on the same day under one clip, so all
        # meetings of a body on a date share it
        video_link = self.video_links.get((view_id, date_obj, is_special))
        if video_link:
            links.append({"href": video_link, "title": "Video"})
        return links

    def _parse_source(self, response):
        """Parse or generate source."""
        return response.url
