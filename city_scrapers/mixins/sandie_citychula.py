"""
A Mixin & Mixin Meta for San Diego City of Chula Vista scrapers.
Uses GetCalendarMeetings endpoint only.
Filters on client side.
"""

import html
import json
import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from pytz import timezone


class ChulaVistaMixinMeta(type):
    """
    Metaclass that enforces required static variables.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "meeting_view_id"]
        missing = [v for v in required_static_vars if v not in dct]
        if missing:
            raise NotImplementedError(f"{name} must define: {', '.join(missing)}")
        super().__init__(name, bases, dct)


class ChulaVistaMixin(CityScrapersSpider, metaclass=ChulaVistaMixinMeta):
    """
    Required class attributes:
    - name: Spider name
    - agency: Agency name
    - meeting_view_id: eScribe meeting view ID

    Optional class attributes:
    - meeting_id_param: URL parameter name ("MeetingviewId" or "MeetingtypeId")
                        Defaults to "MeetingviewId" if not specified
    - allowed_meeting_types: List/set of meeting type names to filter for
    """

    name = None
    agency = None
    meeting_view_id = None
    meeting_id_param = "MeetingviewId"  # DEFAULT VALUE
    time_notes = None
    allowed_meeting_types = None

    timezone = "America/Los_Angeles"

    base_url = "https://pub-chulavista.escribemeetings.com/"
    api_url_calendar = (
        "https://pub-chulavista.escribemeetings.com/"
        "MeetingsCalendarView.aspx/GetCalendarMeetings"
    )

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    def _make_absolute_url(self, url):
        """Convert relative URL to absolute."""
        if not url or url.startswith("<"):
            return None
        if url.startswith("http"):
            return url
        return self.base_url + url.lstrip("/")

    def _clean_html(self, text):
        """Remove HTML tags from text."""
        if not text:
            return ""
        text = re.sub(r"<br\s*/?>", ", ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def start_requests(self):
        yield from self._request_calendar_meetings()

    def _request_calendar_meetings(self):
        # # Use the meeting_id_param (defaults to "MeetingviewId")
        url = f"{self.api_url_calendar}?{self.meeting_id_param}={self.meeting_view_id}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url.rstrip("/"),
            "Referer": f"{self.base_url}?{self.meeting_id_param}={self.meeting_view_id}",
            "Cookie": "CurrentTab=calendar",
        }

        # Get timezone-aware date range
        tz = timezone(self.timezone)

        # Start from 2020
        start = tz.localize(datetime(2020, 1, 1, 0, 0, 0))

        # End in year 2099 (effectively unlimited)
        end = tz.localize(datetime(2099, 12, 31, 23, 59, 59))

        body = {
            "calendarStartDate": start.isoformat(),
            "calendarEndDate": end.isoformat(),
        }

        yield scrapy.Request(
            url=url,
            method="POST",
            headers=headers,
            body=json.dumps(body),
            callback=self.parse_calendar,
            dont_filter=True,
        )

    def parse_calendar(self, response):
        data = response.json()
        meetings = data.get("d", [])

        for item in meetings:
            meeting = self._create_meeting(item)
            if meeting:
                yield meeting

    def _create_meeting(self, item):
        # Filter by meeting type if allowed_meeting_types is set
        if self.allowed_meeting_types:
            meeting_type = (item.get("MeetingType") or "").strip()
            meeting_name = (item.get("MeetingName") or "").strip()

            if (
                meeting_type not in self.allowed_meeting_types
                and meeting_name not in self.allowed_meeting_types
            ):
                return None

        meeting = Meeting(
            title=self._parse_title(item),
            description="",
            classification=self._parse_classification(item),
            start=self._parse_start(item),
            end=self._parse_end(item),
            all_day=False,
            time_notes=self.time_notes,
            location=self._parse_location(item),
            links=self._parse_links(item),
            source=self.api_url_calendar,
        )

        if meeting["start"] is None:
            return None

        link_text = " ".join(link["title"] for link in meeting.get("links", []))
        meeting["status"] = self._get_status(meeting, text=link_text)
        meeting["id"] = self._get_id(meeting)

        return meeting

    def _parse_title(self, item):
        title = (item.get("MeetingName") or item.get("MeetingType", "")).strip()
        return html.unescape(title)

    def _parse_classification(self, item):
        title = item.get("MeetingType", "").lower()
        if "commission" in title:
            return COMMISSION
        if "committee" in title:
            return COMMITTEE
        if "board" in title:
            return BOARD
        return NOT_CLASSIFIED

    def _parse_datetime(self, date_str):
        """
        Parse datetime string and return datetime.

        :param date_str: Date string from API
        :return: Datetime or None
        """
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            return None

    def _parse_start(self, item):
        """Parse meeting start datetime."""
        return self._parse_datetime(item.get("StartDate"))

    def _parse_end(self, item):
        """Parse meeting end datetime."""
        return self._parse_datetime(item.get("EndDate"))

    def _parse_location(self, item):
        name = (item.get("Location") or "").strip()
        address = self._clean_html(item.get("Description", ""))

        if address.startswith(name):
            address = address[len(name) :].lstrip(", ").strip()

        if not address:
            address = name
        return {
            "name": name,
            "address": address,
        }

    def _normalize_link_title(self, title):
        if not title:
            return None

        title = title.strip()

        if title.lower() == "agenda en español":
            return "Agenda (Spanish)"

        return title

    def _parse_links(self, item):
        """
        Parse all links associated with a meeting.
        :param item: Raw meeting data
        :return: List of link dicts with 'href' and 'title' keys
        """
        links = []
        seen_urls = set()

        docs = item.get("MeetingDocumentLink", [])
        for doc in docs:
            url = self._make_absolute_url(doc.get("Url"))
            if not url or url in seen_urls:
                continue

            title = self._normalize_link_title(doc.get("Title"))
            if not title:
                continue

            links.append(
                {
                    "href": url,
                    "title": title,
                }
            )
            seen_urls.add(url)

        if item.get("HasVideo") and item.get("VideoUrl"):
            video_url = self._make_absolute_url(item.get("VideoUrl"))
            if video_url and video_url not in seen_urls:
                links.append({"href": video_url, "title": "Video"})
                seen_urls.add(video_url)

        return links
