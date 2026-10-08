"""
A Mixin & Mixin Meta for San Diego City of Chula Vista scrapers.
Uses GetCalendarMeetings endpoint only.
Filters on client side.
"""

import calendar as cal
import html
import json
import re
from collections import defaultdict
from datetime import date, datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests
from parsel import Selector


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
    - calendar_keywords: List of keywords used to find this agency's events on
                         the city calendar (city calendar is skipped if unset)
    - calendar_exclude_keywords: List of keywords for city calendar events that
                                 match calendar_keywords but aren't meetings
    - location: Default location dict used when eScribe has no address
    """

    name = None
    agency = None
    meeting_view_id = None
    meeting_id_param = "MeetingviewId"  # DEFAULT VALUE
    time_notes = None
    allowed_meeting_types = None
    calendar_keywords = None
    calendar_exclude_keywords = None
    location = {"name": "TBD", "address": ""}

    timezone = "America/Los_Angeles"

    city_base = "https://www.chulavistaca.gov"
    base_url = "https://pub-chulavista.escribemeetings.com/"
    api_url_calendar = base_url + "MeetingsCalendarView.aspx/GetCalendarMeetings"
    city_calendar_base = (
        city_base + "/residents/advanced-components/site-content/city-calendar"
    )

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # City calendar and eScribe titles are compared through _meeting_key, which
    # drops these words from the title and records "special" vs "regular" instead
    _NOISE_RE = re.compile(r"\b(special|regular|quarterly|meeting)\b")
    _SPECIAL_RE = re.compile(r"\bspecial\b")

    # Genuine naming differences between the city calendar and eScribe,
    # applied to the normalized title body
    _BODY_ALIASES = (
        (re.compile(r"\bparks and rec\b"), "parks and recreation"),
        (re.compile(r"^safety commission\b"), "traffic safety commission"),
        (re.compile(r"\bhomeless\b"), "homelessness"),
        (
            re.compile(r"^community advisory committee\b"),
            "police department community advisory committee",
        ),
    )

    # Checked in order against the lowercased meeting type
    _CLASSIFICATIONS = (
        ("commission", COMMISSION),
        ("committee", COMMITTEE),
        ("board", BOARD),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_state()

    def _init_state(self):
        """Reset per-run state (also called from start_requests)."""
        # Calendar meetings to yield later
        self._calendar_meetings = []
        # City calendar (title, event URL) pairs keyed by date,
        # used as eScribe meeting sources
        self._calendar_event_urls = {}
        self._fetched_calendar_months = set()

    # HELPERS

    @property
    def _escribe_query(self):
        """Query string identifying this agency's eScribe meeting view."""
        return f"?{self.meeting_id_param}={self.meeting_view_id}"

    def _now_local(self):
        return datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)

    def _shift_month(self, year, month, offset):
        """Return (year, month) shifted by offset months."""
        years, month_index = divmod(month - 1 + offset, 12)
        return year + years, month_index + 1

    def _shift_years(self, dt, years):
        """Shift a datetime by whole years, clamping Feb 29 to Feb 28."""
        try:
            return dt.replace(year=dt.year + years)
        except ValueError:
            return dt.replace(year=dt.year + years, day=28)

    def _date_range(self):
        """Scraped period, shared by eScribe and the city calendar:
        3 years back, 1 year ahead."""
        now = self._now_local()
        start = self._shift_years(now, -3).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = self._shift_years(now, 1).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
        return start, end

    def _make_absolute_url(self, url):
        """Convert relative URL to absolute."""
        if not url or url.startswith("<"):
            return None
        return urljoin(self.base_url, url)

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

        if title.lower().startswith("agenda en español"):
            return "Agenda (Spanish)"

        return title

    def _normalize_calendar_text(self, text):
        """
        Lowercase, treat "&" as "and", and drop punctuation and extra spaces,
        so "Health, Wellness,  and Aging" matches "Health Wellness and Aging".
        """
        text = text.lower().replace("&", " and ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return text.strip()

    def _title_key(self, title):
        """
        Normalized title without cancellation words, used to compare titles,
        so "CANCELLED- Human Relations Commission" matches
        "Human Relations Commission".
        """
        text = self._normalize_calendar_text(title)
        # canceled, cancelled, cancellled
        text = re.sub(r"\bcancel+ed\b", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _meeting_key(self, title):
        """
        Key identifying a meeting, e.g. ("board of ethics", "regular"), that is
        the same for a city calendar title and its eScribe title.
        """
        text = self._title_key(title)
        kind = "special" if self._SPECIAL_RE.search(text) else "regular"
        body = " ".join(self._NOISE_RE.sub(" ", text).split())
        for pattern, replacement in self._BODY_ALIASES:
            body = pattern.sub(replacement, body)
        return " ".join(body.split()), kind

    def _matches_keywords(self, title):
        """
        Whether a city calendar title matches any of calendar_keywords
        and none of calendar_exclude_keywords.
        """
        normalized = self._normalize_calendar_text(title)
        return any(
            self._normalize_calendar_text(kw) in normalized
            for kw in self.calendar_keywords or []
        ) and not any(
            self._normalize_calendar_text(kw) in normalized
            for kw in self.calendar_exclude_keywords or []
        )

    # REQUESTS

    def start_requests(self):
        self._init_state()

        # fetch every city calendar month in the eScribe period
        if self.calendar_keywords:
            start, end = self._date_range()
            year, month = start.year, start.month
            while (year, month) <= (end.year, end.month):
                self._load_city_calendar_month(year, month)
                year, month = self._shift_month(year, month, 1)

        yield from self._request_calendar_meetings()

    def _load_city_calendar_month(self, year, month):
        """Fetch and parse one month of the city calendar, once per month."""
        if (year, month) in self._fetched_calendar_months:
            return
        self._fetched_calendar_months.add((year, month))

        prev_year, prev_month = self._shift_month(year, month, -1)
        url = f"{self.city_calendar_base}/-curm-{month}/-cury-{year}"
        referer = f"{self.city_calendar_base}/-curm-{prev_month}/-cury-{prev_year}"
        calendar_html = self._fetch_city_calendar(url, referer)
        if calendar_html:
            self._calendar_meetings.extend(
                self._parse_city_calendar_html(calendar_html, url, month, year)
            )

    def _fetch_city_calendar(self, url, referer):
        """Fetch city calendar page using curl_cffi to bypass Akamai."""
        try:
            response = curl_requests.get(
                url,
                impersonate="chrome110",
                headers={
                    "Referer": referer,
                    "Upgrade-Insecure-Requests": "1",
                },
            )
        except curl_requests.RequestsError as e:
            self.logger.warning(f"Failed to fetch city calendar {url}: {e}")
            return None
        return response.text if response.status_code == 200 else None

    def _request_calendar_meetings(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url.rstrip("/"),
            "Referer": self.base_url + self._escribe_query,
            "Cookie": "CurrentTab=calendar",
        }

        # Timezone-aware date range
        tz = ZoneInfo(self.timezone)
        start, end = (dt.replace(tzinfo=tz) for dt in self._date_range())

        body = {
            "calendarStartDate": start.isoformat(),
            "calendarEndDate": end.isoformat(),
        }

        yield scrapy.Request(
            url=self.api_url_calendar + self._escribe_query,
            method="POST",
            headers=headers,
            body=json.dumps(body),
            callback=self.parse_calendar,
            dont_filter=True,
        )

    # PARSING

    def parse_calendar(self, response):
        meetings = response.json().get("d", [])
        escribe_meetings = [m for m in map(self._create_meeting, meetings) if m]

        # group escribe meetings by date to match them with city calendar events
        meetings_by_date = defaultdict(list)
        for meeting in escribe_meetings:
            meetings_by_date[meeting["start"].date()].append(meeting)
        matched_paths = set()
        for day, day_meetings in meetings_by_date.items():
            matched_paths |= self._parse_sources(day, day_meetings)

        yield from escribe_meetings

        # yield city calendar meetings not matched to any eScribe meeting;
        # they have no eScribe attachments, so their links stay empty
        seen_ids = set()
        for meeting in self._calendar_meetings:
            if (
                meeting["source"].split("?")[0] in matched_paths
                or meeting["id"] in seen_ids
            ):
                continue
            seen_ids.add(meeting["id"])
            yield meeting

    def _create_meeting(self, item):
        # Filter by meeting type if allowed_meeting_types is set
        if self.allowed_meeting_types:
            # API returns HTML-escaped names, e.g. "Citizens&#39;"
            meeting_type = html.unescape(item.get("MeetingType") or "").strip()
            meeting_name = html.unescape(item.get("MeetingName") or "").strip()

            if (
                meeting_type not in self.allowed_meeting_types
                and meeting_name not in self.allowed_meeting_types
            ):
                return None

        meeting_start = self._parse_datetime(item.get("StartDate"))
        if meeting_start is None:
            return None

        meeting = Meeting(
            title=self._parse_title(item),
            description="",
            classification=self._parse_classification(item),
            start=meeting_start,
            end=self._parse_datetime(item.get("EndDate")),
            all_day=False,
            time_notes=self.time_notes,
            location=self._parse_location(item),
            links=self._parse_links(item),
            # source is set in parse_calendar, once city calendar URLs are loaded
        )

        link_text = " ".join(link["title"] for link in meeting["links"])
        meeting["status"] = self._get_status(meeting, text=link_text)
        meeting["id"] = self._get_id(meeting)

        return meeting

    # City calendar parsing

    def _parse_city_calendar_html(self, calendar_html, source_url, month, year):
        """
        Parse city calendar HTML and yield meetings, past and upcoming.
        parse_calendar only keeps those not matched to an eScribe meeting.
        """
        selector = Selector(text=calendar_html)

        for td in selector.css("td"):
            cell_date = self._parse_cell_date(td, year, month)
            if cell_date is None:
                continue

            for event_link in td.css("a"):
                calendar_title = event_link.attrib.get("title", "").strip()
                if not self._matches_keywords(calendar_title):
                    continue

                time_text = (
                    event_link.xpath("./parent::div")
                    .css("span.calendar_eventtime::text")
                    .get("")
                    .strip()
                )
                start = self._parse_event_start(cell_date, time_text)

                href = event_link.attrib.get("href", "").strip()
                event_url = urljoin(self.city_base, href) if href else source_url

                self._record_event_url(start.date(), calendar_title, event_url)

                meeting = Meeting(
                    title=calendar_title,
                    description="",
                    classification=self._parse_classification(
                        {"MeetingType": calendar_title}
                    ),
                    start=start,
                    end=None,
                    all_day=False,
                    time_notes=self.time_notes,
                    location=self.location,
                    links=[],
                    source=event_url,
                )
                meeting["status"] = self._get_status(meeting)
                meeting["id"] = self._get_id(meeting)
                yield meeting

    def _parse_cell_date(self, td, year, month):
        """
        Return the date of a calendar cell, or None if the cell isn't a day.
        The site sometimes returns a different month than requested, so the
        real date from the cell's aria-label is preferred.
        """
        day_text = td.css("span.calendar_day_value::text").get()
        if day_text is None:
            # fall back to the first non-empty text in the cell
            texts = [t.strip() for t in td.css("::text").getall() if t.strip()]
            if not texts:
                return None
            day_text = texts[0]

        day_match = re.match(r"^(\d{1,2})$", day_text.strip())
        if not day_match:
            return None

        aria_date = self._parse_aria_date(td.attrib.get("aria-label", ""))
        if aria_date:
            return aria_date

        day = int(day_match.group(1))
        _, days_in_month = cal.monthrange(year, month)
        if not 1 <= day <= days_in_month:
            return None
        return date(year, month, day)

    def _parse_aria_date(self, label):
        """Parse date from aria-label like '..., Wednesday, October 14, 2026'."""
        match = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})\s*$", label)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").date()
        except ValueError:
            self.logger.warning(f"Failed to parse aria-label date: {label}")
            return None

    def _parse_event_start(self, day, time_text):
        """Return the start datetime of an event on a given date."""
        time_match = re.match(r"(\d{1,2}:\d{2}\s*[AP]M)", time_text, re.IGNORECASE)
        if time_match:
            try:
                return datetime.strptime(
                    f"{day.isoformat()} {time_match.group(1).strip()}",
                    "%Y-%m-%d %I:%M %p",
                )
            except ValueError:
                self.logger.warning(
                    f"Failed to parse event time '{time_text}' on {day}; "
                    "falling back to midnight"
                )
        return datetime(day.year, day.month, day.day)

    def _record_event_url(self, day, title, event_url):
        """
        Remember a city calendar event for a date. The same event can be listed
        on several fetched pages with a different ?curm/cury query, so events
        are compared without the query.
        """
        day_events = self._calendar_event_urls.setdefault(day, [])
        event_path = event_url.split("?")[0]
        if all(url.split("?")[0] != event_path for _, url in day_events):
            day_events.append((title, event_url))

    def _parse_sources(self, day, meetings):
        """
        Set the source of each eScribe meeting on one date. Each city calendar
        event is used by at most one meeting:
        1. a meeting gets the event with the same meeting key
        2. if exactly one meeting and one event are left unmatched (e.g. a
           "CANCELLED ..." calendar title), they are paired
        3. any other meeting uses the agency's eScribe calendar for that year
        Returns the matched event URLs, without their query.
        """
        escribe_url = f"{self.base_url}{self._escribe_query}&Year={day.year}"
        events = list(self._calendar_event_urls.get(day, []))

        matched_urls = []
        unmatched = []
        for meeting in meetings:
            key = self._meeting_key(meeting["title"])
            match = next((e for e in events if self._meeting_key(e[0]) == key), None)
            if match:
                events.remove(match)
                matched_urls.append(self._apply_event(meeting, *match))
            else:
                unmatched.append(meeting)

        if len(unmatched) == 1 and len(events) == 1:
            matched_urls.append(self._apply_event(unmatched[0], *events[0]))
        else:
            for meeting in unmatched:
                meeting["source"] = escribe_url

        return {url.split("?")[0] for url in matched_urls}

    def _apply_event(self, meeting, event_title, event_url):
        """
        Use a matched city calendar event as the eScribe meeting's source, and
        recheck its status with the event title, since a meeting cancelled on
        the city calendar (e.g. "... Meeting - Cancelled") can still look
        scheduled in eScribe.
        """
        meeting["source"] = event_url
        link_text = " ".join(link["title"] for link in meeting.get("links", []))
        meeting["status"] = self._get_status(meeting, text=f"{link_text} {event_title}")
        return event_url

    # eScribe item parsing

    def _parse_title(self, item):
        title = (item.get("MeetingName") or item.get("MeetingType", "")).strip()
        return html.unescape(title)

    def _parse_classification(self, item):
        title = (item.get("MeetingType") or "").lower()
        return next(
            (c for kw, c in self._CLASSIFICATIONS if kw in title), NOT_CLASSIFIED
        )

    def _parse_datetime(self, date_str):
        """
        Parse datetime string and return a naive datetime (agency local time).

        :param date_str: Date string from API
        :return: Datetime or None
        """
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            self.logger.warning(f"Failed to parse datetime: {date_str}")
            return None

    def _parse_location(self, item):
        name = (item.get("Location") or "").strip()
        address = self._clean_html(item.get("Description", ""))

        if address.startswith(name):
            address = address[len(name) :].lstrip(", ").strip()

        if not address:
            return self.location

        return {"name": name, "address": address}

    def _parse_links(self, item):
        """
        Parse all links associated with a meeting.
        :param item: Raw meeting data
        :return: List of link dicts with 'href' and 'title' keys
        """
        candidates = [
            (
                self._make_absolute_url(doc.get("Url")),
                self._normalize_link_title(doc.get("Title")),
            )
            for doc in item.get("MeetingDocumentLink") or []
        ]
        if item.get("HasVideo") and item.get("VideoUrl"):
            candidates.append((self._make_absolute_url(item["VideoUrl"]), "Video"))

        links, seen_urls = [], set()
        for url, title in candidates:
            if url and title and url not in seen_urls:
                seen_urls.add(url)
                links.append({"href": url, "title": title})
        return links
