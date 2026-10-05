"""
A Mixin & Mixin Meta for National City, California scrapers that share the same
table-based HTML structure on the boards-commissions-committees page.

Required class variables (enforced by metaclass):
    name (str): Spider name/slug (e.g., "sandie_citycouncil")
    agency (str): Full agency name (e.g., "Sandie City Council")
    event_type (str or list): Text to filter rows by to identify this specific agency
"""

import html
import random
import re
import time
from datetime import datetime, timedelta

import pytz
import scrapy
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CITY_COUNCIL,
    COMMISSION,
    COMMITTEE,
    NOT_CLASSIFIED,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as cffi_requests
from scrapy.http import HtmlResponse

REAL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

# Akamai blocks Scrapy/requests/Playwright based on TLS + HTTP/2 fingerprint.
# curl-cffi with Chrome impersonation gives us a browser-like network fingerprint.
# Only the User-Agent is overridden: passing a full custom header set replaces
# curl-cffi's Chrome headers (and their order), which Akamai rejects with 403.
IMPERSONATE = "chrome131"
AKAMAI_TIMEOUT = 30
ESCRIBE_CALENDAR_PATH = "/MeetingsCalendarView.aspx/GetCalendarMeetings"


class SandieNationalCityMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from the "Mixin" class.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "event_type"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class SandieNationalCityMixin(
    CityScrapersSpider, metaclass=SandieNationalCityMixinMeta
):
    """Mixin for National City meeting spiders using table-based HTML parsing."""

    name = None
    agency = None
    event_type = None
    # Only scrape meetings from this many years before today onwards (plus all
    # future meetings). Rolling, so the window moves forward every run.
    lookback_years = 2
    time_notes = ""

    timezone = "America/Los_Angeles"

    # Seconds to wait between curl-cffi requests (plus up to 1s of jitter).
    # Bursts of requests get the IP blocked by Akamai.
    request_delay = 8
    # Akamai intermittently 403s individual requests; retry these with backoff
    akamai_retries = 3
    akamai_retry_backoff = 30

    # Optional eSCRIBE portal (not behind Akamai) used as a fallback when a
    # website listing page can't be fetched. Only City Council publishes there.
    escribe_url = None

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": REAL_UA,
    }

    start_url = "https://www.nationalcityca.gov/government/boards-commissions-committees/-toggle-all/-sortn-EDate/-sortd-desc"  # noqa

    location = {
        "name": "National City Council Chambers",
        "address": "1243 National City Boulevard, National City, CA 91950",
    }

    _CLASSIFICATION_MAP = [
        ("commission", COMMISSION),
        ("advisory", ADVISORY_COMMITTEE),
        ("committee", COMMITTEE),
        ("board", BOARD),
        ("council", CITY_COUNCIL),
    ]

    def __init__(self, *args, **kwargs):
        self._last_akamai_request = None
        super().__init__(*args, **kwargs)

    def _start_cutoff(self):
        """Earliest meeting start to scrape: today minus lookback_years."""
        now = datetime.now(pytz.timezone(self.timezone)).replace(tzinfo=None)
        try:
            cutoff = now.replace(year=now.year - self.lookback_years)
        except ValueError:  # today is Feb 29 and the cutoff year has none
            cutoff = now.replace(year=now.year - self.lookback_years, day=28)
        return cutoff.replace(hour=0, minute=0, second=0, microsecond=0)

    def start_requests(self):
        """
        Kick off the spider without touching the protected site.

        The real pages are fetched inside _run_crawl() using curl-cffi; a
        data: URL avoids a Scrapy-fingerprinted request that Akamai would 403.
        """
        yield scrapy.Request("data:,", callback=self._run_crawl, dont_filter=True)

    def _run_crawl(self, response):
        """Fetch listing pages via curl-cffi, following pagination.

        parse() still yields a scrapy.Request for the next page; it is fetched
        here instead of being scheduled through Scrapy. If a listing page can't
        be fetched, the meetings the website didn't cover come from eSCRIBE
        (when escribe_url is set).
        """
        next_url = self.start_url
        oldest_listed = None  # oldest date on any listing page fetched so far
        yielded_starts = set()

        while next_url:
            listing = self._akamai_get(next_url)
            if listing is None:
                self.logger.warning("Could not fetch listing page: %s", next_url)
                yield from self._escribe_fallback(oldest_listed, yielded_starts)
                return

            for row in listing.css("table tbody tr"):
                start = self._parse_start(row)
                if start and (oldest_listed is None or start < oldest_listed):
                    oldest_listed = start

            next_url = None
            for result in self.parse(listing):
                if isinstance(result, scrapy.Request):
                    next_url = result.url
                else:
                    yielded_starts.add(result["start"])
                    yield result

    def _escribe_fallback(self, before, yielded_starts):
        """Yield eSCRIBE meetings from the start cutoff up to `before` (the oldest
        date the website listing reached; everything if it reached nothing),
        skipping any start time the website already produced."""
        if not self.escribe_url:
            return

        start = self._start_cutoff()
        # Website pages cover `before` onwards; include that day in case its
        # meetings continue on the page that failed.
        end = before or datetime.now() + timedelta(days=730)
        self.logger.info(
            "Falling back to eSCRIBE for meetings %s to %s", start.date(), end.date()
        )

        meetings = self._fetch_escribe_meetings(start, end)
        if meetings is None:
            return
        for meeting in self._parse_escribe_meetings(meetings):
            if meeting["start"] in yielded_starts:
                continue
            if before and meeting["start"].date() > before.date():
                continue
            yield meeting

    def _fetch_escribe_meetings(self, start, end):
        """POST to eSCRIBE's calendar endpoint; returns its list of meetings."""
        try:
            response = cffi_requests.post(
                self.escribe_url + ESCRIBE_CALENDAR_PATH,
                impersonate=IMPERSONATE,
                timeout=AKAMAI_TIMEOUT,
                json={
                    "calendarStartDate": start.strftime("%Y-%m-%d"),
                    "calendarEndDate": end.strftime("%Y-%m-%d"),
                },
            )
            response.raise_for_status()
            return response.json()["d"]
        except Exception as e:
            self.logger.warning("eSCRIBE fallback failed: %s", e)
            return None

    def _parse_escribe_meetings(self, meetings):
        """Turn eSCRIBE calendar entries into Meeting items."""
        for item in meetings:
            start = datetime.strptime(item["StartDate"], "%Y/%m/%d %H:%M:%S")
            if start < self._start_cutoff():
                continue
            name = self._normalize_title(item["MeetingName"])
            # Match the website's titles so meeting ids agree across sources
            title = re.sub(r"^Cancellation Notice of an? ", "", name, flags=re.I)
            title = re.sub(r"^Regular ", "", title)

            meeting = Meeting(
                title=title,
                description="",
                classification=self._parse_classification_from_title(title),
                start=start,
                # eSCRIBE's EndDate is a scheduled block (often 11pm), not a
                # published end time; leave it empty like the website does so
                # the pipeline fills it in
                end=None,
                all_day=False,
                time_notes=self.time_notes,
                location=self._parse_escribe_location(item.get("Location", "")),
                links=[
                    {"href": self.escribe_url + link["Url"], "title": link["Title"]}
                    for link in item.get("MeetingDocumentLink", [])
                ],
                # Same source as website meetings: the main listing page
                source=self.start_url,
            )
            meeting["status"] = self._get_status(meeting, text=name)
            meeting["id"] = self._get_id(meeting)
            yield meeting

    def _parse_escribe_location(self, location):
        """Map eSCRIBE's location text to a location dict."""
        if not location or "1243 National City" in location:
            return self.location
        return {"name": location.strip(), "address": ""}

    def _akamai_get(self, url):
        """GET an Akamai-protected URL with curl-cffi Chrome impersonation.

        Akamai intermittently rejects individual requests with 403, so these are
        retried with an increasing backoff. Returns a Scrapy HtmlResponse so
        existing .css()/.xpath() parsing can stay the same, or None if every
        attempt failed. Blocks the Twisted reactor; callers run sequentially.
        """
        for attempt in range(1, self.akamai_retries + 1):
            self._wait_before_request()
            try:
                response = cffi_requests.get(
                    url,
                    impersonate=IMPERSONATE,
                    timeout=AKAMAI_TIMEOUT,
                    headers={"User-Agent": REAL_UA},
                )
            except Exception as e:
                self.logger.warning("Akamai fetch error for %s: %s", url, e)
                return None

            # Akamai sometimes answers 200 with its JavaScript challenge page
            # (bm-verify) instead of the real page; curl-cffi can't run it
            challenge = response.status_code == 200 and self._is_akamai_challenge(
                response.content
            )
            if response.status_code == 200 and not challenge:
                self.logger.info("Akamai fetch 200 for %s", url)
                return HtmlResponse(url=url, body=response.content, encoding="utf-8")

            self.logger.warning(
                "Akamai fetch returned %s for %s (attempt %s/%s)",
                "a challenge page" if challenge else response.status_code,
                url,
                attempt,
                self.akamai_retries,
            )
            if response.status_code != 403 and not challenge:
                return None
            if attempt < self.akamai_retries:
                time.sleep(self.akamai_retry_backoff * attempt)

        return None

    def _is_akamai_challenge(self, body):
        """True if the body is Akamai's JavaScript challenge page."""
        return b"bm-verify" in body and b"<table" not in body

    def _wait_before_request(self):
        """Keep at least request_delay (+ jitter) seconds between requests."""
        if self._last_akamai_request is not None:
            elapsed = time.monotonic() - self._last_akamai_request
            time.sleep(max(0, self.request_delay + random.random() - elapsed))
        self._last_akamai_request = time.monotonic()

    def parse(self, response):
        """
        Parse the table rows and yield Meeting items.
        Filters rows based on the event_type to get meetings for this agency.
        """
        for table in response.css("table"):
            for row in table.css("tbody tr"):
                cells = row.css("td")
                if not cells:
                    continue

                row_text = " ".join(row.css("::text").getall())

                if not self._matches_event_type(row_text):
                    continue

                links = self._parse_links(row)
                start_date = self._parse_start(row)

                if not start_date:
                    self.logger.warning(
                        "Skipping row with no parseable start date on %s: %r",
                        response.url,
                        re.sub(r"\s+", " ", row_text).strip()[:200],
                    )
                    continue

                # Skip meetings before the start cutoff (today - lookback_years)
                if start_date < self._start_cutoff():
                    continue

                title = self._parse_title(row)

                # Check if this is a combined meeting (multiple event types in title)
                combined_types = self._detect_combined_meeting(title)

                # Build a list of meeting_data dicts (single or combined)
                meeting_data_list = []

                if combined_types:
                    for event_type in combined_types:
                        filtered_links = self._filter_links_by_event_type(
                            links, event_type
                        )
                        split_title = self._extract_title_for_event_type(event_type)

                        meeting_data_list.append(
                            {
                                "title": split_title,
                                "description": self._parse_description(row),
                                "classification": self._parse_classification_from_title(
                                    split_title
                                ),
                                "start": start_date,
                                "end": self._parse_end(row),
                                "all_day": False,
                                "time_notes": self.time_notes,
                                "links": filtered_links,
                                "source": self._parse_source(response),
                            }
                        )
                else:
                    # Single event type meeting - clean up links
                    clean_links = [
                        {"href": link["href"], "title": link["title"]} for link in links
                    ]

                    meeting_data_list.append(
                        {
                            "title": title,
                            "description": self._parse_description(row),
                            "classification": self._parse_classification(row),
                            "start": start_date,
                            "end": self._parse_end(row),
                            "all_day": False,
                            "time_notes": self.time_notes,
                            "links": clean_links,
                            "source": self._parse_source(response),
                        }
                    )

                yield from self._build_meetings(meeting_data_list, self.location)

        # pagination (OUTSIDE the loop)
        # The listing is sorted newest first: once this page reaches meetings
        # before the start cutoff, every later page is older too, so stop here.
        if self._page_reaches_before_cutoff(response):
            self.logger.info(
                "Reached meetings before %s on %s, stopping pagination",
                self._start_cutoff().date(),
                response.url,
            )
            return

        # Look for the "Next »" button specifically - it contains the text "Next" and has -npage- in URL # noqa
        # We need to be more specific to avoid sort/filter links
        next_links = response.xpath(
            "//a[contains(normalize-space(.), 'Next') and contains(@href, '-npage-')]"
        )

        if next_links:
            # Get the link that increments the page number
            next_href = next_links[0].xpath("@href").get()

            if next_href and not next_href.startswith("javascript:"):
                # Clean the URL - remove sort parameters and fragments to avoid loops
                next_url = response.urljoin(next_href)
                # Remove the fragment/anchor part
                next_url = next_url.split("#")[0]
                yield scrapy.Request(url=next_url, callback=self.parse)

    def _page_reaches_before_cutoff(self, response):
        """True if any row on the page (any agency) is before the start cutoff."""
        cutoff = self._start_cutoff()
        for row in response.css("table tbody tr"):
            start = self._parse_start(row)
            if start and start < cutoff:
                return True
        return False

    def _matches_event_type(self, text):
        """Check if row matches the event type filter."""
        text_lower = text.lower()

        if isinstance(self.event_type, str):
            return self.event_type.lower() in text_lower
        elif isinstance(self.event_type, list):
            return any(f.lower() in text_lower for f in self.event_type)

        return False

    def _build_meetings(self, meeting_data_list, location):
        """Create Meeting items from parsed row data and a location."""
        for meeting_data in meeting_data_list:
            meeting = Meeting(**meeting_data, location=location)
            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)
            yield meeting

    def _detect_combined_meeting(self, title):
        """
        Detect if a meeting title contains multiple event types.
        Returns a list of event types found, or None if single type.
        """
        if not isinstance(self.event_type, list):
            return None

        title_lower = title.lower()
        found_types = []

        # Common combined meeting patterns
        combined_indicators = [" and ", " & ", "/"]
        has_indicator = any(ind in title_lower for ind in combined_indicators)

        if not has_indicator:
            return None

        # Check which event types are in the title
        for event in self.event_type:
            if event.lower() in title_lower:
                found_types.append(event)

        # Only return if we found multiple types
        return found_types if len(found_types) > 1 else None

    def _filter_links_by_event_type(self, links, event_type):
        """Filter links to only include those relevant to the specific event type."""
        filtered = []
        event_keywords = event_type.lower().split()

        for link in links:
            search_text = link.get("original_title", link["title"]).lower()

            # Check if link text contains keywords from this event type
            if any(keyword in search_text for keyword in event_keywords):
                # Create clean link without original_title
                clean_link = {"href": link["href"], "title": link["title"]}
                filtered.append(clean_link)

        return filtered

    def _extract_title_for_event_type(self, event_type):
        """Extract the appropriate title for a specific event type from a combined title."""  # noqa
        # For combined meetings, use just the event type name as the title
        return f"{event_type} Meeting"

    def _normalize_title(self, text):
        """Normalize title text (remove/replace smart punctuation)."""
        if not text:
            return ""

        # Decode any HTML entities first
        text = html.unescape(text)

        # Replace "smart" punctuation with plain ASCII equivalents
        replacements = {
            "\u2013": "-",  # en dash
            "\u2014": "-",  # em dash
            "\u2019": "'",  # right single quote / apostrophe
            "\u2018": "'",  # left single quote
            "\u201c": '"',  # left double quote
            "\u201d": '"',  # right double quote
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        # Collapse whitespace
        return re.sub(r"\s+", " ", text).strip()

    def _parse_title(self, row):
        """Parse meeting title from table row."""
        cells = row.css("td")
        if not cells:
            return self.agency

        title_text = cells[0].css("::text").get()
        title_text = self._normalize_title(title_text)

        if title_text:
            return title_text

        all_text = self._normalize_title(" ".join(row.css("::text").getall()))
        if all_text:
            return all_text.split("\n")[0].strip() or self.agency

        return self.agency

    def _parse_description(self, row):
        """Parse meeting description from table row."""
        cells = row.css("td")
        if len(cells) > 1:
            desc = " ".join(cells[1].css("::text").getall()).strip()
            desc = self._filter_datetime_from_description(desc)
            return desc
        return ""

    def _filter_datetime_from_description(self, text):
        """Remove date/time patterns from description text."""
        if not text:
            return ""

        datetime_patterns = [
            r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)",
            r"\d{1,2}/\d{1,2}/\d{4}",
            r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)",
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",  # noqa
            r"-\s*\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)",
        ]

        filtered = text
        for pattern in datetime_patterns:
            filtered = re.sub(pattern, "", filtered, flags=re.IGNORECASE)

        filtered = re.sub(r"\s+", " ", filtered).strip()
        filtered = re.sub(r"^[-\s]+|[-\s]+$", "", filtered).strip()

        return filtered

    def _parse_classification(self, row):
        """Parse or generate classification from allowed options."""
        title = self._parse_title(row)
        return self._parse_classification_from_title(title)

    def _parse_classification_from_title(self, title):
        """Determine classification based on title text."""
        title_lower = title.lower()
        for keyword, classification in self._CLASSIFICATION_MAP:
            if keyword in title_lower:
                return classification
        return NOT_CLASSIFIED

    _DATE_RE = r"(\d{1,2}/\d{1,2}/\d{4})"
    _TIME_RE = r"(\d{1,2}:\d{2}\s*[AaPp][Mm])"

    def _date_cell(self, row):
        """Return the Date/Time cell (td.event_datetime, else the 2nd cell)."""
        cell = row.css("td.event_datetime")
        if cell:
            return cell[0]
        cells = row.css("td")
        return cells[1] if len(cells) > 1 else None

    def _parse_start(self, row):
        """Parse start datetime as a naive datetime object.

        Uses the hidden <time itemprop="startDate"> text when present, otherwise
        the first date (and time) in the Date/Time cell. Only that cell is read,
        so dates in link titles can't be mistaken for the meeting date.
        """
        cell = self._date_cell(row)
        if cell is None:
            return None
        text = cell.css("time[itemprop='startDate']::text").get() or " ".join(
            cell.css("::text").getall()
        )
        match = re.search(rf"{self._DATE_RE}(?:\s+{self._TIME_RE})?", text)
        if not match:
            return None
        return self._to_datetime(match.group(1), match.group(2))

    def _parse_end(self, row):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        cell = self._date_cell(row)
        if cell is None:
            return None

        # Hidden endDate only counts if it has a time (it's date-only otherwise)
        end_text = cell.css("time[itemprop='endDate']::text").get() or ""
        match = re.search(rf"{self._DATE_RE}\s+{self._TIME_RE}", end_text)
        if match:
            return self._to_datetime(match.group(1), match.group(2))

        # Otherwise look for a range like "6/13/2024 6:00 PM - 8:00 PM"
        text = " ".join(cell.xpath("./text()").getall())
        match = re.search(
            rf"{self._DATE_RE}\s+{self._TIME_RE}\s*-\s*{self._TIME_RE}", text
        )
        if match:
            return self._to_datetime(match.group(1), match.group(3))
        return None

    def _to_datetime(self, date_str, time_str=None):
        """Combine "M/D/YYYY" and optional "H:MM PM" into a naive datetime."""
        try:
            if time_str:
                time_str = re.sub(r"\s+", "", time_str).upper()
                return datetime.strptime(f"{date_str} {time_str}", "%m/%d/%Y %I:%M%p")
            return datetime.strptime(date_str, "%m/%d/%Y")
        except ValueError:
            return None

    def _parse_links(self, row):
        """Parse or generate links."""
        links = []

        for link in row.css("a"):
            href = link.attrib.get("href", "").strip()
            if not href:
                continue

            if href.startswith("/"):
                href = f"https://www.nationalcityca.gov{href}"
            elif not href.startswith("http"):
                href = f"https://www.nationalcityca.gov/{href}"

            # Skip calendar event detail pages, only keep document links
            href_lower = href.lower()
            if (
                "/calendar/event/" in href_lower
                or "/components/calendar/" in href_lower
            ):
                continue

            title = link.css("::text").get()
            if not title:
                title = "Document"
            else:
                title = self._normalize_title(title.strip())

            # Preserve original title for filtering
            original_title = title

            links.append(
                {
                    "href": href,
                    "title": title,
                    "original_title": original_title,  # Store for filtering
                }
            )

        return links

    def _parse_source(self, response):
        """Main listing URL: page URLs (-npage-N) shift as new meetings are added,
        so a meeting's page number doesn't stay accurate."""
        return self.start_url
