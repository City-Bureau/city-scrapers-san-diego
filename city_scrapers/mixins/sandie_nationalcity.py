"""
A Mixin & Mixin Meta for National City, California scrapers that share the same
table-based HTML structure on the boards-commissions-committees page.

Required class variables (enforced by metaclass):
    name (str): Spider name/slug (e.g., "sandie_citycouncil")
    agency (str): Full agency name (e.g., "Sandie City Council")
    event_type (str or list): Text to filter rows by to identify this specific agency
"""

import html
import re
from datetime import datetime

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
    start_year = 2022  # Only scrape meetings from this year onwards
    time_notes = ""

    timezone = "America/Los_Angeles"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    start_urls = "https://www.nationalcityca.gov/government/boards-commissions-committees/-toggle-all/-sortn-EDate/-sortd-desc"  # noqa

    location = {
        "name": "National City Council Chambers",
        "address": "1243 National City Boulevard, National City, CA 91950",
    }

    _MONTH_MAP = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }

    _DATE_PATTERNS = [
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",  # noqa
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})",  # noqa
    ]

    def _get_headers(self):
        """Return the request headers."""
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",  # noqa
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Priority": "u=0, i",
            "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',  # noqa
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",  # noqa
        }

    def _get_detail_headers(self, referer):
        """Headers for calendar event detail pages (avoid 403)."""
        headers = dict(self._get_headers())
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-User"] = "?1"
        return headers

    def start_requests(self):
        yield scrapy.Request(
            url=self.start_urls, headers=self._get_headers(), callback=self.parse
        )

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

                # Skip meetings before start_year
                if start_date and start_date.year < self.start_year:
                    continue

                title = self._parse_title(row)

                # Check if this is a combined meeting (multiple event types in title)
                combined_types = self._detect_combined_meeting(title)

                # Get detail page URL for accurate location
                detail_url = self._get_detail_url(row)

                # Build a list of meeting_data dicts (single or combined)
                meeting_data_list = []

                if combined_types:
                    for event_type in combined_types:
                        filtered_links = self._filter_links_by_event_type(
                            links, event_type
                        )
                        split_title = self._extract_title_for_event_type(
                            title, event_type
                        )

                        meeting_data_list.append(
                            {
                                "title": split_title,
                                "description": self._parse_description(row),
                                "classification": self._parse_classification_from_title(
                                    split_title
                                ),
                                "start": start_date,
                                "end": self._parse_end(row),
                                "all_day": self._parse_all_day(row),
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
                            "all_day": self._parse_all_day(row),
                            "time_notes": self.time_notes,
                            "links": clean_links,
                            "source": self._parse_source(response),
                        }
                    )

                # If we have a detail page, fetch it ONCE and apply location to all meetings from this row # noqa
                if detail_url:
                    yield scrapy.Request(
                        url=detail_url,
                        callback=self.parse_detail,
                        headers=self._get_detail_headers(response.url),
                        meta={"meeting_data_list": meeting_data_list},
                    )
                else:
                    # No detail page -> yield meetings with fallback location
                    for meeting_data in meeting_data_list:
                        meeting = Meeting(**meeting_data, location=self.location)
                        meeting["status"] = self._get_status(meeting)
                        meeting["id"] = self._get_id(meeting)
                        yield meeting

        # pagination (OUTSIDE the loop)
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
                yield scrapy.Request(
                    url=next_url,
                    callback=self.parse,
                    headers=self._get_headers(),
                )

    def _matches_event_type(self, text):
        """Check if row matches the event type filter."""
        text_lower = text.lower()

        if isinstance(self.event_type, str):
            return self.event_type.lower() in text_lower
        elif isinstance(self.event_type, list):
            return any(f.lower() in text_lower for f in self.event_type)

        return False

    def _get_detail_url(self, row):
        """Extract the calendar event detail page URL from a row."""
        for link in row.css("a"):
            href = (link.attrib.get("href") or "").strip()
            if not href:
                continue

            if "/Home/Components/Calendar/Event/" not in href:
                continue

            if href.startswith("/"):
                return f"https://www.nationalcityca.gov{href}"
            if not href.startswith("http"):
                return f"https://www.nationalcityca.gov/{href.lstrip('/')}"
            return href

        return None

    def parse_detail(self, response):
        """Parse the detail page to extract accurate location information."""
        meeting_data_list = response.meta.get("meeting_data_list", [])

        location = self._parse_detail_location(response)

        for meeting_data in meeting_data_list:
            meeting = Meeting(
                title=meeting_data["title"],
                description=meeting_data["description"],
                classification=meeting_data["classification"],
                start=meeting_data["start"],
                end=meeting_data["end"],
                all_day=meeting_data["all_day"],
                time_notes=meeting_data["time_notes"],
                location=location,
                links=meeting_data["links"],
                source=meeting_data["source"],
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)
            yield meeting

    def _parse_detail_location(self, response):
        """Parse location from the detail page HTML."""
        li = response.xpath(
            "//ul[contains(@class,'detail-list')]/li"
            "[span[contains(@class,'detail-list-label') and "
            "contains(normalize-space(.), 'Location')]]"
        )

        if not li:
            return self.location

        name = li.xpath(".//span[@itemprop='name']/text()").get()
        street = li.xpath(".//span[@itemprop='street-address']/text()").get()
        locality = li.xpath(".//span[@itemprop='locality']/text()").get()
        region = li.xpath(".//span[@itemprop='region']/text()").get()

        address_text = " ".join(
            li.xpath(".//span[@itemprop='address']//text()").getall()
        )
        address_text = re.sub(r"\s+", " ", address_text).strip()
        zip_match = re.search(r"\b\d{5}\b", address_text)
        zip_code = zip_match.group(0) if zip_match else ""

        parts = []
        if street:
            parts.append(street.strip().rstrip(","))
        if locality:
            parts.append(locality.strip().rstrip(","))
        if region:
            parts.append(region.strip().rstrip(","))

        address = ""
        if parts:
            address = ", ".join(parts)
            if zip_code:
                address = f"{address} {zip_code}"
        elif address_text:
            address = address_text

        if (name and name.strip()) or address:
            return {"name": (name or "").strip(), "address": address}

        return self.location

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
            # Use original_title if available, otherwise fall back to title
            search_text = link.get("original_title", link["title"]).lower()

            # Check if link text contains keywords from this event type
            if any(keyword in search_text for keyword in event_keywords):
                # Create clean link without original_title
                clean_link = {"href": link["href"], "title": link["title"]}
                filtered.append(clean_link)

        return filtered

    def _extract_title_for_event_type(self, title, event_type):
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

        if "commission" in title_lower:
            return COMMISSION
        elif "advisory" in title_lower:
            return ADVISORY_COMMITTEE
        elif "committee" in title_lower:
            return COMMITTEE
        elif "board" in title_lower:
            return BOARD
        elif "council" in title_lower:
            return CITY_COUNCIL

        return NOT_CLASSIFIED

    def _parse_start(self, row):
        """Parse start datetime as a naive datetime object."""
        cells = row.css("td")

        # First pass: look for datetime with time component
        for cell in cells:
            cell_text = " ".join(cell.css("::text").getall()).strip()
            dt = self._extract_datetime(cell_text)
            if dt and (dt.hour != 0 or dt.minute != 0):
                return dt

        # Second pass: accept any datetime (fallback to date-only)
        for cell in cells:
            cell_text = " ".join(cell.css("::text").getall()).strip()
            dt = self._extract_datetime(cell_text)
            if dt:
                return dt

        return None

    def _parse_end(self, row):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        cells = row.css("td")

        for cell in cells:
            cell_text = " ".join(cell.css("::text").getall()).strip()
            end_dt = self._extract_end_datetime(cell_text)
            if end_dt:
                return end_dt

        return None

    def _parse_all_day(self, row):
        """Parse or generate all-day status. Defaults to False."""
        return False

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

            title_lower = title.lower()

            if "agenda" in href_lower or "agenda" in title_lower:
                link_title = "Agenda"
            elif "minutes" in href_lower or "minutes" in title_lower:
                link_title = "Minutes"
            elif "packet" in href_lower or "packet" in title_lower:
                link_title = "Packet"
            else:
                link_title = title

            links.append(
                {
                    "href": href,
                    "title": link_title,
                    "original_title": original_title,  # Store for filtering
                }
            )

        return links

    def _parse_source(self, response):
        """Parse or generate source."""
        return response.url

    def _parse_date(self, text):
        """Parse date from text string. Returns datetime object or None."""
        for pattern in self._DATE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) != 3:
                        continue

                    if groups[0].isdigit() and groups[1].isdigit():
                        if len(groups[0]) == 4:
                            year, month, day = (
                                int(groups[0]),
                                int(groups[1]),
                                int(groups[2]),
                            )
                        else:
                            month, day, year = (
                                int(groups[0]),
                                int(groups[1]),
                                int(groups[2]),
                            )
                        return datetime(year, month, day)
                    else:
                        month_str = groups[0]
                        day = int(groups[1])
                        year = int(groups[2])
                        month = self._MONTH_MAP.get(month_str.lower())
                        if month:
                            return datetime(year, month, day)
                except (ValueError, AttributeError):
                    continue
        return None

    def _extract_datetime(self, text):
        """Extract datetime from text string."""
        time_patterns = [
            r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)",
            r"(\d{1,2})\s*(AM|PM|am|pm)",
        ]

        parsed_date = self._parse_date(text)
        if not parsed_date:
            return None

        try:
            for pattern in time_patterns:
                time_match = re.search(pattern, text, re.IGNORECASE)
                if time_match:
                    time_groups = time_match.groups()
                    hour = int(time_groups[0])
                    minute = (
                        int(time_groups[1])
                        if len(time_groups) > 2 and time_groups[1].isdigit()
                        else 0
                    )
                    period = time_groups[-1].upper()

                    if period == "PM" and hour != 12:
                        hour += 12
                    elif period == "AM" and hour == 12:
                        hour = 0

                    return parsed_date.replace(hour=hour, minute=minute)

            return parsed_date

        except (ValueError, AttributeError):
            return None

    def _extract_end_datetime(self, text):
        """Extract end datetime from text with time ranges like '5:30 PM - 6:30 PM'."""
        time_range_patterns = [
            r"-\s*(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)",
            r"to\s+(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)",
        ]

        parsed_date = self._parse_date(text)
        if not parsed_date:
            return None

        try:
            for pattern in time_range_patterns:
                time_match = re.search(pattern, text, re.IGNORECASE)
                if time_match:
                    time_groups = time_match.groups()
                    hour = int(time_groups[0])
                    minute = int(time_groups[1])
                    period = time_groups[2].upper()

                    if period == "PM" and hour != 12:
                        hour += 12
                    elif period == "AM" and hour == 12:
                        hour = 0

                    return parsed_date.replace(hour=hour, minute=minute)

            return None

        except (ValueError, AttributeError, IndexError):
            return None
