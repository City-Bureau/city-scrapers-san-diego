"""
A Mixin & Mixin Meta for San Diego City of Chula Vista scrapers.
Uses GetCalendarMeetings endpoint only.
Filters on client side.
"""

import calendar as cal
import html
import json
import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests
from parsel import Selector
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
    city_calendar_base = "https://www.chulavistaca.gov/residents/advanced-components/site-content/city-calendar"  # noqa

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    # HELPERS
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

    def _normalize_link_title(self, title):
        if not title:
            return None

        title = title.strip()

        if title.lower() == "agenda en español":
            return "Agenda (Spanish)"

        return title

    # REQUESTS

    def start_requests(self):
        # Store calendar meetings to yield later
        self._calendar_meetings = []

        if getattr(self, "calendar_keywords", None):
            now = datetime.now()
            for i in range(13):
                month = (now.month + i - 1) % 12 + 1
                year = now.year + (now.month + i - 1) // 12
                prev_month = (now.month + i - 2) % 12 + 1
                prev_year = now.year + (now.month + i - 2) // 12
                url = f"{self.city_calendar_base}/-curm-{month}/-cury-{year}"
                referer = (
                    f"{self.city_calendar_base}/-curm-{prev_month}/-cury-{prev_year}"
                )
                html = self._fetch_city_calendar(url, referer)
                if html:
                    self._calendar_meetings.extend(
                        self._parse_city_calendar_html(html, url, month, year)
                    )

        yield from self._request_calendar_meetings()

    def _fetch_city_calendar(self, url, referer):
        """Fetch city calendar page using curl_cffi to bypass Akamai."""
        response = curl_requests.get(
            url,
            impersonate="chrome110",
            headers={
                "Referer": referer,
                "Upgrade-Insecure-Requests": "1",
            },
        )
        return response.text if response.status_code == 200 else None

    def _request_calendar_meetings(self):
        # # Use the meeting_id_param (defaults to "MeetingviewId")
        url = f"{self.api_url_calendar}?{self.meeting_id_param}={self.meeting_view_id}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url.rstrip("/"),
            "Referer": f"{self.base_url}?{self.meeting_id_param}={self.meeting_view_id}",  # noqa
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

    # PARSING

    def parse_calendar(self, response):
        data = response.json()
        meetings = data.get("d", [])

        # collect escribe meeting dates
        escribe_dates = set()
        for item in meetings:
            meeting = self._create_meeting(item)
            if meeting:
                escribe_dates.add(meeting["start"].date())
                yield meeting

        # yield city calendar meetings only if date not already in eScribe
        for meeting in getattr(self, "_calendar_meetings", []):
            if meeting["start"].date() not in escribe_dates:
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
            end=self._parse_datetime(item.get("EndDate")),
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

    def _parse_city_calendar_html(self, html, source_url, month, year):
        """Parse city calendar HTML and yield meetings."""

        selector = Selector(text=html)
        keywords = getattr(self, "calendar_keywords", [])

        now = datetime.now()
        # Get number of days in the month to filter out invalid dates
        _, days_in_month = cal.monthrange(year, month)

        for td in selector.css("td"):
            all_text = td.css("::text").getall()
            if not all_text:
                continue
            day_match = re.match(r"^(\d{1,2})$", all_text[0].strip())
            if not day_match:
                continue
            day = int(day_match.group(1))
            if day > days_in_month:
                continue

            for event_link in td.css("a"):
                title = event_link.attrib.get("title", "").strip()
                if not any(kw.lower() in title.lower() for kw in keywords):
                    continue

                # href = event_link.attrib.get("href", "")
                div = event_link.xpath("./parent::div")
                time_text = div.css("span.calendar_eventtime::text").get("").strip()
                time_match = re.match(
                    r"(\d{1,2}:\d{2}\s*[AP]M)", time_text, re.IGNORECASE
                )

                try:
                    if time_match:
                        start = datetime.strptime(
                            f"{year}-{month:02d}-{day:02d} {time_match.group(1).strip()}",  # noqa
                            "%Y-%m-%d %I:%M %p",
                        )
                    else:
                        start = datetime(year, month, day)
                except ValueError:
                    start = datetime(year, month, day)

                if start < now:
                    continue

                meeting = Meeting(
                    title=title,
                    description="",
                    classification=self._parse_classification({"MeetingType": title}),
                    start=start,
                    end=None,
                    all_day=False,
                    time_notes=self.time_notes,
                    location=getattr(self, "location", {"name": "", "address": ""}),
                    links=[],
                    source=source_url,
                )
                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)
                yield meeting

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

    def _parse_location(self, item):
        name = (item.get("Location") or "").strip()
        address = self._clean_html(item.get("Description", ""))

        if address.startswith(name):
            address = address[len(name) :].lstrip(", ").strip()

        if not address:

            return getattr(self, "location", {"name": "", "address": ""})

        return {
            "name": name,
            "address": address,
        }

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
