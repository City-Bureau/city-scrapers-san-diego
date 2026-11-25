"""
A Mixin & Mixin Meta for San Diego City of Chula Vista scrapers.
Uses the eScribe GetCalendarMeetings endpoint and the city's CivicPlus calendar.
"""

import html
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from datetime import time as dt_time
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests
from scrapy import signals
from scrapy.http import HtmlResponse
from twisted.python.failure import Failure


class ChulaVistaError(Exception):
    """eScribe or the city calendar could not be read as expected."""


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
    Required: name, agency, meeting_view_id
    Optional: meeting_id_param, allowed_meeting_types, calendar_id,
    calendar_keywords, calendar_exclude_keywords, location, time_notes
    """

    name = None
    agency = None
    meeting_view_id = None
    meeting_id_param = "MeetingviewId"  # DEFAULT VALUE
    time_notes = None
    allowed_meeting_types = None
    calendar_id = None
    calendar_keywords = None
    calendar_exclude_keywords = None
    location = {"name": "TBD", "address": ""}

    timezone = "America/Los_Angeles"

    city_base = "https://www.chulavistaca.gov"
    city_calendar_url = city_base + "/Calendar.aspx"
    # The city site responds with 403 to Scrapy requests, so it's fetched
    # with curl_cffi browser impersonation
    curl_impersonate = "chrome110"
    curl_timeout = 30
    # A one-off 403 on the calendar would drop the city-only meetings
    calendar_tries = 2
    retry_backoff = 3
    base_url = "https://pub-chulavista.escribemeetings.com/"
    api_url_calendar = base_url + "MeetingsCalendarView.aspx/GetCalendarMeetings"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # Dropped from titles by _meeting_key
    _NOISE_RE = re.compile(r"\b(special|regular|quarterly|meeting)\b")
    _SPECIAL_RE = re.compile(r"\bspecial\b")

    # Naming differences between the city calendar and eScribe
    _BODY_ALIASES = (
        (re.compile(r"\bparks and rec\b"), "parks and recreation"),
        (re.compile(r"^safety commission\b"), "traffic safety commission"),
        (re.compile(r"\bhomeless\b"), "homelessness"),
        (re.compile(r"^pd\b"), "police department"),
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
        self._calendar_events = []
        self._problems = []
        self._failed_requests = 0
        self._meetings_parsed = 0
        self._event_pages = 0
        self._failed_event_pages = 0
        self._event_pages_without_location = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider._on_spider_closed, signal=signals.spider_closed)
        return spider

    # Helpers

    @property
    def _escribe_query(self):
        """Query string identifying this agency's eScribe meeting view."""
        return f"?{self.meeting_id_param}={self.meeting_view_id}"

    def _now_local(self):
        return datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)

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

    def _clean_text(self, text):
        return " ".join((text or "").split())

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
        Whether a city calendar title matches any of calendar_keywords (or
        calendar_keywords is unset) and none of calendar_exclude_keywords.
        """
        normalized = self._normalize_calendar_text(title)
        return (
            not self.calendar_keywords
            or any(
                self._normalize_calendar_text(kw) in normalized
                for kw in self.calendar_keywords
            )
        ) and not any(
            self._normalize_calendar_text(kw) in normalized
            for kw in self.calendar_exclude_keywords or []
        )

    # Requests

    def start_requests(self):
        """
        The city calendar is fetched first, so that its events are known when
        the eScribe meetings are parsed and matched to them.
        """
        self._init_state()
        if self.calendar_id:
            self._load_city_calendar()
        yield self._escribe_request()

    def _city_calendar_url(self):
        """The agency's city calendar events over the scraped period."""
        start, end = self._date_range()
        params = {
            "Keywords": "",
            "startDate": start.strftime("%m/%d/%Y"),
            "enddate": end.strftime("%m/%d/%Y"),
            "CID": self.calendar_id,
            "showPastEvents": "true",
        }
        return f"{self.city_calendar_url}?{urlencode(params)}"

    def _city_get(self, url, tries=1):
        """
        GET a city site page with curl_cffi, up to `tries` times, waiting
        retry_backoff seconds between tries. Returns an HtmlResponse, or None
        if every try fails. Blocks the reactor, like the other curl_cffi
        spiders.
        """
        for attempt in range(1, tries + 1):
            try:
                response = curl_requests.get(
                    url, impersonate=self.curl_impersonate, timeout=self.curl_timeout
                )
            except curl_requests.RequestsError as e:
                error = e
            else:
                if response.status_code == 200:
                    return HtmlResponse(
                        url=url, body=response.content, encoding="utf-8"
                    )
                error = f"status {response.status_code}"
            self.logger.warning(
                f"curl_cffi request to {url} failed ({attempt}/{tries}): {error}"
            )
            if attempt < tries:
                time.sleep(self.retry_backoff)
        return None

    def _load_city_calendar(self):
        """
        Record the agency's city calendar events. If the calendar can't be
        fetched, eScribe is scraped alone and it's reported on spider close.
        """
        url = self._city_calendar_url()
        response = self._city_get(url, tries=self.calendar_tries)
        if response is None:
            self._failed_requests += 1
            self._add_problem(f"request to city calendar {url} failed")
            return
        self._parse_city_calendar(response)

    def _escribe_request(self):
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

        return scrapy.Request(
            url=self.api_url_calendar + self._escribe_query,
            method="POST",
            headers=headers,
            body=json.dumps(body),
            callback=self.parse_calendar,
            errback=self._escribe_failed,
            dont_filter=True,
        )

    # Parsing

    def _parse_city_calendar(self, response):
        if not response.css(f"#CID{self.calendar_id}"):
            # calendars with no events in range have no CID block
            self.logger.info(
                f"No events found on {response.url} for CID{self.calendar_id}"
            )
        self._calendar_events = list(self._parse_city_calendar_events(response))

    def parse_calendar(self, response):
        """
        Parse the eScribe meetings, match them to the city calendar events, and
        add the city calendar events that have no eScribe meeting.
        """
        try:
            meetings = response.json().get("d")
        except (ValueError, AttributeError):
            meetings = None
        if not isinstance(meetings, list):
            self._add_problem(
                f"Unexpected eScribe response from {response.url}; the API may "
                "have changed"
            )
            meetings = []
        escribe_meetings = [m for m in map(self._create_meeting, meetings) if m]
        self._meetings_parsed += len(escribe_meetings)

        # group escribe meetings by date to match them with city calendar events
        meetings_by_date = defaultdict(list)
        for meeting in escribe_meetings:
            meetings_by_date[meeting["start"].date()].append(meeting)
        matched_urls = set()
        for day, day_meetings in meetings_by_date.items():
            matched_urls |= self._parse_sources(day, day_meetings)

        yield from escribe_meetings
        yield from self._city_meetings(matched_urls)

    def _escribe_failed(self, failure):
        """Record the failure and still yield the city calendar meetings."""
        self._request_failed(failure)
        yield from self._city_meetings(set())

    def _city_meetings(self, matched_urls):
        """
        Yield a meeting for each city calendar event not matched to an eScribe
        meeting. These meetings have no eScribe attachments, so their links
        stay empty.
        """
        seen_urls = set()
        for event in self._calendar_events:
            if event["url"] in matched_urls or event["url"] in seen_urls:
                continue
            seen_urls.add(event["url"])
            yield self._city_meeting(event)

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
            # source is set in parse_calendar, once city calendar events are loaded
        )

        meeting["status"] = self._get_status(meeting, text=self._status_text(meeting))
        meeting["id"] = self._get_id(meeting)

        return meeting

    def _status_text(self, meeting, event_title=""):
        """
        Text passed to _get_status for an eScribe meeting: its link titles and,
        if matched, the city calendar event title. When eScribe has a
        cancellation notice next to other documents (e.g. an agenda), the
        meeting still took place, so cancellation wording is ignored.
        """
        titles = [link["title"] for link in meeting.get("links", [])]
        other_titles = [t for t in titles if not re.search(r"cancel", t, re.I)]
        if other_titles and len(other_titles) < len(titles):
            return " ".join(other_titles + [event_title])
        return " ".join(titles + [event_title])

    # City calendar parsing

    def _parse_city_calendar_events(self, response):
        """
        Parse the agency's events from the calendar's list view, past and
        upcoming. Each event is a list item with schema.org Event data, e.g.
        <span itemprop="startDate">2026-12-08T18:00:00</span>.
        """
        for item in response.css(f"#CID{self.calendar_id} ol > li"):
            title = self._clean_text(
                item.css("[itemscope] > [itemprop=name]::text").get()
            )
            if not title or not self._matches_keywords(title):
                continue
            start = self._parse_iso_datetime(
                item.css("[itemprop=startDate]::text").get()
            )
            if start is None:
                self.logger.warning(f"No start found for city event {title!r}")
                continue
            end = self._parse_iso_datetime(item.css("[itemprop=endDate]::text").get())
            yield {
                "title": title,
                "start": start,
                "end": end if end and end > start else None,
                "url": self._parse_city_event_url(item, response),
            }

    def _parse_iso_datetime(self, value):
        """Parse e.g. "2026-12-08T18:00:00" as a naive local datetime."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.strip()).replace(tzinfo=None)
        except ValueError:
            self.logger.warning(f"Failed to parse city calendar datetime {value!r}")
            return None

    def _parse_city_event_url(self, item, response):
        """
        The event's detail page, e.g. "/Calendar.aspx?EID=965". The link's
        other parameters are the date the calendar was viewed, so they're
        removed to keep the source the same from day to day.
        """
        href = item.css("h3 a::attr(href)").get() or ""
        match = re.search(r"\bEID=(\d+)", href)
        if not match:
            return response.url
        return f"{self.city_calendar_url}?EID={match.group(1)}"

    def _city_meeting(self, event):
        """
        A city calendar meeting, with the location from its detail page, or
        the default location if the page can't be fetched (reported on close
        only if every detail page failed).
        """
        self._event_pages += 1
        response = self._city_get(event["url"])
        if response is None:
            self._failed_event_pages += 1
            return self._create_city_meeting(event, self.location)
        location = self._parse_city_location(response)
        if location is None:
            self._event_pages_without_location += 1
            location = self.location
        return self._create_city_meeting(event, location)

    def _create_city_meeting(self, event, location):
        self._meetings_parsed += 1
        meeting = Meeting(
            title=event["title"],
            description="",
            classification=self._parse_classification({"MeetingType": event["title"]}),
            start=event["start"],
            end=event["end"],
            all_day=False,
            time_notes=self.time_notes,
            location=location,
            links=[],
            source=event["url"],
        )
        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _parse_city_location(self, response):
        """
        Parse the location from the event's detail page: its schema.org Place
        data, e.g. "Council Chambers" at "276 Fourth Avenue, Chula Vista, CA
        91910", or else the text of its "Location" detail. Returns None if
        neither is found.
        """
        place = response.css("[itemprop=location]")
        if place:
            name = self._clean_text(
                " ".join(place[0].css("[itemprop=name] ::text").getall())
            )
            parts = [
                self._clean_text(" ".join(place[0].css(f"{sel} ::text").getall()))
                for sel in (
                    "[itemprop=streetAddress]",
                    "[itemprop=addressLocality]",
                )
            ]
            region = " ".join(
                self._clean_text(" ".join(place[0].css(f"{sel} ::text").getall()))
                for sel in ("[itemprop=addressRegion]", "[itemprop=postalCode]")
            ).strip()
            address = ", ".join(p for p in parts + [region] if p)
            if name or address:
                return self._city_location(name, address)

        for header in response.css(".specificDetailHeader"):
            header_text = self._clean_text(" ".join(header.css("::text").getall()))
            if not header_text.lower().startswith("location"):
                continue
            detail = header.xpath(
                "following-sibling::*[contains(@class, 'specificDetailItem')][1]"
            )
            lines = [self._clean_text(t) for t in detail.css("::text").getall()]
            lines = [line for line in lines if line]
            if lines:
                # the address starts at the first line with a street number
                index = next(
                    (i for i, line in enumerate(lines) if re.match(r"\d", line)),
                    len(lines),
                )
                name = " ".join(lines[:index])
                address = ", ".join(lines[index:])
                return self._city_location(name, address)

        self.logger.info(f"No location found on {response.url}, using the default")
        return None

    def _city_location(self, name, address):
        """A detail page location, without a duplicated name or empty address."""
        if not address:
            return {"name": name, "address": self.location["address"]}
        return {"name": name or address, "address": address}

    def _parse_sources(self, day, meetings):
        """
        Set the source of each eScribe meeting on one date. Each city calendar
        event is used by at most one meeting:
        1. a meeting gets the event with the same meeting key
        2. any other meeting uses the agency's eScribe calendar for that year
        Returns the matched event URLs.
        """
        escribe_url = f"{self.base_url}{self._escribe_query}&Year={day.year}"
        events = [e for e in self._calendar_events if e["start"].date() == day]

        matched_urls = set()
        for meeting in meetings:
            key = self._meeting_key(meeting["title"])
            match = next(
                (e for e in events if self._meeting_key(e["title"]) == key), None
            )
            if match:
                events.remove(match)
                self._apply_event(meeting, match)
                matched_urls.add(match["url"])
            else:
                meeting["source"] = escribe_url

        return matched_urls

    def _apply_event(self, meeting, event):
        """
        Use a matched city calendar event's detail page as the eScribe meeting's
        source and its start time when they differ, as eScribe times can be
        wrong (e.g. 10:00 AM for a 6:00 PM meeting). The status is rechecked
        with the event title, since a meeting cancelled on the city calendar
        (e.g. "... Meeting - Cancelled") can still look scheduled in eScribe.
        The eScribe location is kept.
        """
        meeting["source"] = event["url"]
        # midnight means the event has no time
        if event["start"].time() != dt_time(0) and event["start"] != meeting["start"]:
            meeting["start"] = event["start"]
            # eScribe's end no longer fits; None unless the city event has one
            meeting["end"] = event["end"]
        meeting["status"] = self._get_status(
            meeting, text=self._status_text(meeting, event["title"])
        )
        if "id" in meeting:
            meeting["id"] = self._get_id(meeting)

    # Error reporting

    def _request_failed(self, failure):
        """
        Without an errback, HTTP errors and network failures are only logged
        by Scrapy and never reach Sentry; reported on spider close.
        """
        self._failed_requests += 1
        request = getattr(failure, "request", None)
        url = request.url if request else self.api_url_calendar
        self._add_problem(f"request to {url} failed: {failure.value!r}")

    def _add_problem(self, problem):
        self.logger.warning(problem)
        self._problems.append(problem)

    def _on_spider_closed(self, spider, reason):
        """Report one error per run for major breakages only."""
        problems = list(self._problems)
        if self._event_pages and self._failed_event_pages == self._event_pages:
            problems.append(
                f"all {self._event_pages} city calendar detail page(s) failed"
            )
        fetched_pages = self._event_pages - self._failed_event_pages
        if fetched_pages and self._event_pages_without_location == fetched_pages:
            problems.append(
                f"no location found on any of {fetched_pages} city calendar detail "
                "page(s); the page layout may have changed"
            )
        if reason == "finished" and self._meetings_parsed == 0:
            problems.append("0 meetings parsed")
        if not problems:
            return
        self._report_error(
            ChulaVistaError(
                f"{self.name}: {'; '.join(problems)} (finish_reason={reason}, "
                f"failed_requests={self._failed_requests}, "
                f"city_events={len(self._calendar_events)}, "
                f"meetings={self._meetings_parsed})"
            )
        )

    def _report_error(self, exc):
        """Log and send spider_error (forwarded to Sentry)."""
        self.logger.error(str(exc))
        self.crawler.stats.inc_value(f"spider_exceptions/{exc.__class__.__name__}")
        self.crawler.signals.send_catch_log(
            signal=signals.spider_error,
            failure=Failure(exc),
            response=None,
            spider=self,
        )

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
