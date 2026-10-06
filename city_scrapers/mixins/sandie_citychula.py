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
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import BOARD, COMMISSION, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests
from dateutil.relativedelta import relativedelta
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
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # Maps city calendar titles to their eScribe equivalents
    calendar_title_map = {
        # Board of Ethics
        "Board of Ethics - Regular Meeting": "Board of Ethics Regular Meeting",
        "Board of Ethics - Special Meeting": "Board of Ethics Special Meeting",
        "Board of Ethics": "Board of Ethics Regular Meeting",
        "Board of Ethics - Subcommittee Interview Panel": (
            "Board of Ethics Subcommittee Interview Panel"
        ),
        # Board of Appeals and Advisors
        "Board of Appeals and Advisors Meeting": (
            "Board of Appeals and Advisors Regular Meeting"
        ),
        # Cultural Arts Commission
        "Cultural Arts Commission Meeting": "Cultural Arts Commission- Regular Meeting",
        "Cultural Arts Commission Special Meeting": (
            "Cultural Arts Commission - Special Meeting"
        ),
        # Health, Wellness, and Aging Commission
        "Health Wellness and Aging Commission Meeting": (
            "Health, Wellness, and Aging Commission Regular Meeting"
        ),
        "Health, Wellness, and Aging Commission Meeting": (
            "Health, Wellness, and Aging Commission Regular Meeting"
        ),
        "Health Wellness and Aging Commission Special Meeting": (
            "Health, Wellness, and Aging Commission Special Meeting"
        ),
        # Housing and Homelessness Advisory Commission
        "Housing and Homelessness Advisory Commission": (
            "Housing and Homelessness Advisory Commission Regular"
        ),
        "Housing & Homelessness Advisory Commission Regular Meeting": (
            "Housing and Homelessness Advisory Commission Regular"
        ),
        "Housing & Homelessness Advisory Commission Meeting": (
            "Housing and Homelessness Advisory Commission Regular"
        ),
        "Housing & Homelessness Advisory Commission - Special Meeting": (
            "Housing and Homelessness Advisory Commission Special Meeting"
        ),
        "Housing & Homelessness Advisory Commission Special Meeting": (
            "Housing and Homelessness Advisory Commission Special Meeting"
        ),
        "Housing and Homeless Advisory Commission Special Meeting": (
            "Housing and Homelessness Advisory Commission Special Meeting"
        ),
        # Human Relations Commission
        "Human Relations Commission": "Human Relations Commission Regular Meeting",
        # Measure A Citizens' Oversight Committee
        "Measure A Citizens' Oversight Committee Meeting": (
            "Measure A Citizens' Oversight Committee Regular Meeting"
        ),
        # Measure P Citizens' Oversight Committee
        "Measure P Citizens' Oversight Committee": (
            "Measure P Citizens' Oversight Committee- Regular Meeting"
        ),
        "Measure P - Citizens' Oversight Committee": (
            "Measure P Citizens' Oversight Committee- Regular Meeting"
        ),
        "Measure P - Citizens' Oversight Committee Special Meeting": (
            "Measure P Citizens' Oversight Committee Special Meeting"
        ),
        # Planning Commission
        "Planning Commission Meeting": "Planning Commission - Regular Meeting",
        # Privacy Protection and Technology Advisory Commission
        "Privacy Protection and Technology Advisory Commission": (
            "Privacy Protection and Technology Advisory Commission Meeting"
        ),
        "Privacy Protection and Technology Advisory Commission Special Meeting": (
            "Privacy Protection and Technology Advisory Commission Meeting - Special"
        ),
        # Sustainability Commission
        "Sustainability Commission Meeting": (
            "Sustainability Commission- Regular Meeting"
        ),
        "Sustainability Commission Special Meeting": (
            "Sustainability Commission - Special Meeting"
        ),
        # Traffic Safety Commission
        "Traffic Safety Commission": "Traffic Safety Commission Regular Meeting",
        "Traffic Safety Commission Meeting": (
            "Traffic Safety Commission Regular Meeting"
        ),
        # Veterans Advisory Commission
        "Veterans Advisory Commission - Regular Meeting": (
            "Veterans Advisory Commission Regular Meeting"
        ),
        "Veterans Advisory Commission Meeting": (
            "Veterans Advisory Commission Regular Meeting"
        ),
        "Veterans Advisory Commission - Special Meeting": (
            "Veterans Advisory Commission Special Meeting"
        ),
        # Charter Review Commission
        "Charter Review Commission": "Charter Review Commission - Regular Meeting",
        "Charter Review Commission Regular Meeting": (
            "Charter Review Commission - Regular Meeting"
        ),
        "Charter Review Commission Special Meeting": (
            "Charter Review Commission - Special Meeting"
        ),
        # Parks and Recreation Commission
        "Parks and Rec Commission Regular Meeting": "Parks and Recreation Commission Regular Meeting",  # noqa
        # Police Department Community Advisory Committee
        "SPECIAL MEETING - Police Department Community Advisory Committee": (
            "Police Department Community Advisory Committee Special Meeting"
        ),
        "Police Department Community Advisory Committee - Special Meeting": (
            "Police Department Community Advisory Committee Special Meeting"
        ),
        "Police Department Community Advisory Committee (Regular, Quarterly Meeting)": (
            "Police Department Community Advisory Committee- Regular Meeting"
        ),
        "Police Department Community Advisory Committee": (
            "Police Department Community Advisory Committee- Regular Meeting"
        ),
        "Community Advisory Committee - SPECIAL MEETING Regular, Quarterly Meeting": (
            "Police Department Community Advisory Committee Special Meeting"
        ),
        # Traffic Safety Commission
        "Safety Commission - Regular": ("Traffic Safety Commission Regular Meeting"),
        "Traffic Safety Commission Special Meeting": (
            "Traffic Safety Commission Special Meeting"
        ),
        "Traffic Safety Commission Meeting": (
            "Traffic Safety Commission Regular Meeting"
        ),
    }

    # HELPERS
    def _now_local(self):
        return datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)

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

    def _map_calendar_title(self, title):
        """Map a city calendar title to its eScribe equivalent, if known."""
        key = self._title_key(title)
        for calendar_title, escribe_title in self.calendar_title_map.items():
            if self._title_key(calendar_title) == key:
                return escribe_title
        return title

    # REQUESTS

    def start_requests(self):
        # Store calendar meetings to yield later
        self._calendar_meetings = []
        # City calendar (title, event URL) pairs keyed by date,
        # used as eScribe meeting sources
        self._calendar_event_urls = {}
        self._fetched_calendar_months = set()

        if getattr(self, "calendar_keywords", None):
            this_month = self._now_local().replace(day=1)
            for i in range(13):
                target = this_month + relativedelta(months=i)
                self._load_city_calendar_month(target.year, target.month)

        yield from self._request_calendar_meetings()

    def _load_city_calendar_month(self, year, month):
        """Fetch and parse one month of the city calendar, once per month."""
        if not hasattr(self, "_fetched_calendar_months"):
            self._fetched_calendar_months = set()
        if not hasattr(self, "_calendar_event_urls"):
            self._calendar_event_urls = {}
        if not hasattr(self, "_calendar_meetings"):
            self._calendar_meetings = []
        if (year, month) in self._fetched_calendar_months:
            return
        self._fetched_calendar_months.add((year, month))

        prev = datetime(year, month, 1) - relativedelta(months=1)
        url = f"{self.city_calendar_base}/-curm-{month}/-cury-{year}"
        referer = f"{self.city_calendar_base}/-curm-{prev.month}/-cury-{prev.year}"
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
        # Use the meeting_id_param (defaults to "MeetingviewId")
        url = f"{self.api_url_calendar}?{self.meeting_id_param}={self.meeting_view_id}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.base_url.rstrip("/"),
            "Referer": f"{self.base_url}?{self.meeting_id_param}={self.meeting_view_id}",  # noqa
            "Cookie": "CurrentTab=calendar",
        }

        # Timezone-aware date range (zoneinfo handles the correct DST offset)
        tz = ZoneInfo(self.timezone)

        now = self._now_local()

        # Start 3 years before today
        start = (now - relativedelta(years=3)).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
        )

        # End 1 year after today
        end = (now + relativedelta(years=1)).replace(
            hour=23, minute=59, second=59, microsecond=0, tzinfo=tz
        )

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

        escribe_meetings = [m for m in map(self._create_meeting, meetings) if m]

        # fetch city calendar months covering the eScribe meetings (2020 onward)
        # to find event page URLs for their sources
        if getattr(self, "calendar_keywords", None):
            for year, month in sorted(
                {(m["start"].year, m["start"].month) for m in escribe_meetings}
            ):
                self._load_city_calendar_month(year, month)

        # group escribe meetings by date to match them with city calendar events
        meetings_by_date = {}
        for meeting in escribe_meetings:
            meetings_by_date.setdefault(meeting["start"].date(), []).append(meeting)
        for day, day_meetings in meetings_by_date.items():
            self._parse_sources(day, day_meetings)

        escribe_dates = set(meetings_by_date)
        yield from escribe_meetings

        # yield city calendar meetings only if date not already in eScribe
        seen_ids = set()
        for meeting in getattr(self, "_calendar_meetings", []):
            if meeting["start"].date() in escribe_dates or meeting["id"] in seen_ids:
                continue
            seen_ids.add(meeting["id"])
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

        meeting_start = self._parse_datetime(item.get("StartDate"))
        meeting_end = self._parse_datetime(item.get("EndDate"))

        if meeting_start is None:
            return None

        meeting = Meeting(
            title=self._parse_title(item),
            description="",
            classification=self._parse_classification(item),
            start=meeting_start,
            end=meeting_end,
            all_day=False,
            time_notes=self.time_notes,
            location=self._parse_location(item),
            links=self._parse_links(item),
            # source is set in parse_calendar, once city calendar URLs are loaded
        )

        link_text = " ".join(link["title"] for link in meeting.get("links", []))
        meeting["status"] = self._get_status(meeting, text=link_text)
        meeting["id"] = self._get_id(meeting)

        return meeting

    def _parse_city_calendar_html(self, calendar_html, source_url, month, year):
        """Parse city calendar HTML and yield meetings."""

        selector = Selector(text=calendar_html)
        keywords = getattr(self, "calendar_keywords", [])

        # Naive Pacific "now", comparable with the naive start datetimes below
        now = self._now_local()
        # Get number of days in the month to filter out invalid dates
        _, days_in_month = cal.monthrange(year, month)

        for td in selector.css("td"):
            day_text = td.css("span.calendar_day_value::text").get()
            if day_text is None:
                # fall back to the first non-empty text in the cell
                all_text = [t.strip() for t in td.css("::text").getall() if t.strip()]
                if not all_text:
                    continue
                day_text = all_text[0]
            day_match = re.match(r"^(\d{1,2})$", day_text.strip())
            if not day_match:
                continue

            # The site sometimes returns a different month than requested,
            # so prefer the real date from the cell's aria-label
            day_date = self._parse_aria_date(td.attrib.get("aria-label", ""))
            if day_date:
                cell_year, cell_month, day = (
                    day_date.year,
                    day_date.month,
                    day_date.day,
                )
            else:
                cell_year, cell_month = year, month
                day = int(day_match.group(1))
                if day > days_in_month:
                    continue

            for event_link in td.css("a"):
                title = event_link.attrib.get("title", "").strip()
                normalized_title = self._normalize_calendar_text(title)
                if not any(
                    self._normalize_calendar_text(kw) in normalized_title
                    for kw in keywords
                ):
                    continue

                div = event_link.xpath("./parent::div")
                time_text = div.css("span.calendar_eventtime::text").get("").strip()
                time_match = re.match(
                    r"(\d{1,2}:\d{2}\s*[AP]M)", time_text, re.IGNORECASE
                )

                has_time = False
                try:
                    if time_match:
                        start = datetime.strptime(
                            f"{cell_year}-{cell_month:02d}-{day:02d} {time_match.group(1).strip()}",  # noqa
                            "%Y-%m-%d %I:%M %p",
                        )
                        has_time = True
                    else:
                        start = datetime(cell_year, cell_month, day)
                except ValueError:
                    start = datetime(cell_year, cell_month, day)

                href = event_link.attrib.get("href", "").strip()
                event_url = (
                    "https://www.chulavistaca.gov" + href
                    if href.startswith("/")
                    else href or source_url
                )
                calendar_title = title
                title = self._map_calendar_title(title)

                if hasattr(self, "_calendar_event_urls"):
                    # the same event can be listed on several fetched pages with
                    # a different ?curm/cury query, so compare without the query
                    day_events = self._calendar_event_urls.setdefault(start.date(), [])
                    event_path = event_url.split("?")[0]
                    if all(url.split("?")[0] != event_path for _, url in day_events):
                        day_events.append((title, event_url))

                # Timed events: skip if already started.
                # Untimed events (midnight placeholder): keep through today.
                if has_time:
                    if start < now:
                        continue
                elif start.date() < now.date():
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
                    source=event_url,
                )
                # check the original calendar title, since mapping drops "CANCELLED"
                meeting["status"] = self._get_status(meeting, text=calendar_title)
                meeting["id"] = self._get_id(meeting)
                yield meeting

    def _parse_aria_date(self, label):
        """Parse date from aria-label like 'Scheduled events, Wednesday, October 14, 2026'."""  # noqa
        match = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})\s*$", label)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").date()
        except ValueError:
            return None

    def _parse_sources(self, day, meetings):
        """
        Set the source of each eScribe meeting on one date. Each city calendar
        event is used by at most one meeting:
        1. a meeting gets the event with the same (mapped) title
        2. if exactly one meeting and one event are left unmatched (e.g. a
           "CANCELLED ..." calendar title), they are paired
        3. any other meeting uses the agency's eScribe calendar
        """
        escribe_url = f"{self.base_url}?MeetingviewId={self.meeting_view_id}"
        events = list(getattr(self, "_calendar_event_urls", {}).get(day, []))

        unmatched = []
        for meeting in meetings:
            key = self._title_key(meeting["title"])
            match = next((e for e in events if self._title_key(e[0]) == key), None)
            if match:
                events.remove(match)
                meeting["source"] = match[1]
            else:
                unmatched.append(meeting)

        if len(unmatched) == 1 and len(events) == 1:
            unmatched[0]["source"] = events[0][1]
            return

        for meeting in unmatched:
            meeting["source"] = escribe_url

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
        Parse datetime string and return a naive datetime (agency local time).

        :param date_str: Date string from API
        :return: Datetime or None
        """
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            return None

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
