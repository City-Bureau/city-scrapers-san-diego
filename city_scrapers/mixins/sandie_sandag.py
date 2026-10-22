"""
A Mixin & Mixin Meta for SANDAG (San Diego Association of Governments) scrapers.
Uses the eScribe GetCalendarMeetings endpoint, one request per meeting view ID.
"""

import html
import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    COMMITTEE,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class SandieSandagMixinMeta(type):
    """
    Metaclass that enforces required static variables.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "meeting_view_id"]
        missing = [v for v in required_static_vars if v not in dct]
        if missing:
            raise NotImplementedError(f"{name} must define: {', '.join(missing)}")
        super().__init__(name, bases, dct)


class SandieSandagMixin(CityScrapersSpider, metaclass=SandieSandagMixinMeta):
    """
    Required class attributes:
    - name: Spider name
    - agency: Agency name
    - meeting_view_id: Dict mapping each eScribe meeting view ID to scrape to the
                       sandag.org calendar page used as the meeting source

    Optional class attributes:
    - location: Fallback location used when a meeting has no location listed
    """

    name = None
    agency = None
    meeting_view_id = None

    timezone = "America/Los_Angeles"

    location = {"name": "TBD", "address": ""}

    base_url = "https://pub-sandag.escribemeetings.com/"
    api_url_calendar = (
        "https://pub-sandag.escribemeetings.com/"
        "MeetingsCalendarView.aspx/GetCalendarMeetings"
    )

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # HELPERS

    def _make_absolute_url(self, url):
        """Convert relative URL to absolute."""
        url = (url or "").strip()
        if not url or url.startswith("<"):
            return None
        return urljoin(self.base_url, url)

    def _clean_text(self, text):
        """Unescape HTML entities and collapse whitespace."""
        return re.sub(r"\s+", " ", html.unescape(text or "")).strip()

    def _shift_years(self, dt, years):
        """Shift a datetime by whole years, mapping Feb 29 to Feb 28 if needed."""
        try:
            return dt.replace(year=dt.year + years)
        except ValueError:
            return dt.replace(year=dt.year + years, day=28)

    # REQUESTS

    def start_requests(self):
        # Some meetings (e.g. joint committee meetings) are listed under more than
        # one meeting view, so track IDs to avoid yielding duplicates
        self._seen_meeting_ids = set()

        # Scrape meetings from 2 years ago through 1 year ahead
        today = datetime.now(ZoneInfo(self.timezone)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        body = json.dumps(
            {
                "calendarStartDate": self._shift_years(today, -2).isoformat(),
                "calendarEndDate": self._shift_years(today, 1).isoformat(),
            }
        )

        for view_id in self.meeting_view_id:
            yield scrapy.Request(
                url=f"{self.api_url_calendar}?FillWidth=1&MeetingviewId={view_id}",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": self.base_url.rstrip("/"),
                    "Referer": f"{self.base_url}?FillWidth=1&MeetingviewId={view_id}",
                    "Cookie": "CurrentTab=calendar",
                },
                body=body,
                callback=self.parse,
                dont_filter=True,
            )

    # PARSING

    def parse(self, response):
        if not hasattr(self, "_seen_meeting_ids"):
            self._seen_meeting_ids = set()

        source = self._parse_source(response)

        for item in response.json().get("d", []):
            meeting_id = item.get("ID")
            if meeting_id in self._seen_meeting_ids:
                continue

            meeting = self._create_meeting(item, source)
            if meeting:
                self._seen_meeting_ids.add(meeting_id)
                yield meeting

    def _create_meeting(self, item, source):
        start = self._parse_datetime(item.get("StartDate"))
        if start is None:
            return None

        meeting = Meeting(
            title=self._parse_title(item),
            description="",
            classification=self._parse_classification(item),
            start=start,
            end=self._parse_datetime(item.get("EndDate")),
            all_day=False,
            time_notes="",
            location=self._parse_location(item),
            links=self._parse_links(item),
            source=source,
        )

        # Cancelled meetings have a "Cancellation Notice" document attached
        link_text = " ".join(link["title"] for link in meeting["links"])
        meeting["status"] = self._get_status(meeting, text=link_text)
        meeting["id"] = self._get_id(meeting)

        return meeting

    def _parse_title(self, item):
        return self._clean_text(item.get("MeetingName") or item.get("MeetingType"))

    def _parse_classification(self, item):
        title = (item.get("MeetingType") or item.get("MeetingName") or "").lower()
        if "advisory" in title:
            return ADVISORY_COMMITTEE
        if "committee" in title:
            return COMMITTEE
        if "board" in title:
            return BOARD
        return NOT_CLASSIFIED

    def _parse_datetime(self, date_str):
        """Parse eScribe datetime string (e.g. "2026/09/11 09:00:00")."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            self.logger.warning("Could not parse datetime: %r", date_str)
            return None

    def _parse_location(self, item):
        """
        Description holds the location as "<name><br/><address lines...>",
        e.g. "SANDAG Boardroom <br/>1011 Union Street, First Floor<br/>San Diego, CA"
        """
        parts = [
            self._clean_text(part)
            for part in re.split(
                r"<br\s*/?>", item.get("Description") or "", flags=re.IGNORECASE
            )
        ]
        parts = [part for part in parts if part]
        if not parts:
            return self.location

        name = self._clean_text(item.get("Location")) or parts[0]
        address_parts = parts[1:] if parts[0] == name else parts
        return {
            "name": name,
            "address": ", ".join(address_parts),
        }

    def _parse_links(self, item):
        links = []
        seen_urls = set()

        for doc in item.get("MeetingDocumentLink") or []:
            url = self._make_absolute_url(doc.get("Url"))
            title = self._clean_text(doc.get("Title"))
            if not url or not title or url in seen_urls:
                continue
            links.append({"href": url, "title": title})
            seen_urls.add(url)

        return links

    def _parse_source(self, response):
        """Return the sandag.org calendar page for the response's meeting view."""
        view_id = parse_qs(urlparse(response.url).query).get("MeetingviewId", [""])[0]
        if view_id.isdigit() and int(view_id) in self.meeting_view_id:
            return self.meeting_view_id[int(view_id)]
        return response.url
