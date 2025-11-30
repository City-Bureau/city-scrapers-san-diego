import re
from datetime import datetime, timedelta

from city_scrapers_core.constants import CITY_COUNCIL, COMMITTEE, NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from scrapy import FormRequest, Request, Selector


class TulokCityCouncilSpider(CityScrapersSpider):
    name = "tulok_citycouncil"
    agency = "Tulsa City Council"
    timezone = "America/Chicago"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,  # Required for Granicus - public government data
    }

    def start_requests(self):
        """
        Generate requests for multiple data sources:
        1. Granicus video archive (historical meetings with videos)
        2. City of Tulsa Council Archive (comprehensive meeting data with agendas)
        """
        # Request Granicus archive
        yield Request(
            url="https://tulsa-ok.granicus.com/ViewPublisher.php?view_id=4",
            callback=self.parse_granicus,
        )

        # Request council archive for recent and upcoming meetings
        # Meetings typically happen on Wednesdays, so we'll check all Wednesdays
        # for the last 6 months and next 6 months
        today = datetime.now()
        start_date = today - timedelta(days=180)
        end_date = today + timedelta(days=180)

        # Generate list of Wednesdays to check
        current_date = start_date
        while current_date <= end_date:
            # Check if it's a Wednesday (weekday 2)
            if current_date.weekday() == 2:
                search_date = current_date.strftime("%m/%d/%Y")
                yield Request(
                    url=f"https://www.cityoftulsa.org/apps/TulsaCouncilArchive/Home/Search?Meeting_Date={search_date}&Council_Meeting_Type=-1&btnMeetingSearch=Search",
                    callback=self.parse_archive,
                    meta={"search_date": search_date},
                )
            current_date += timedelta(days=1)

    def parse_granicus(self, response):
        """
        Parse the Granicus ViewPublisher page for Tulsa City Council meetings.
        This source provides video recordings and historical meeting data.
        """
        for item in response.css(".listingRow"):
            title = self._parse_title_granicus(item)
            start_time = self._parse_start_granicus(item)

            # Only skip if we absolutely cannot parse the date
            if not start_time:
                date_str = item.css(".Date::text").get()
                self.logger.warning(
                    f"Skipping Granicus meeting '{title}' - "
                    f"could not parse date from '{date_str}'"
                )
                continue

            meeting = Meeting(
                title=title,
                description=self._parse_description(item),
                classification=self._parse_classification(title),
                start=start_time,
                end=self._parse_end(item),
                all_day=self._parse_all_day(item),
                time_notes=self._parse_time_notes(item),
                location=self._parse_location(item),
                links=self._parse_links_granicus(item),
                source=self._parse_source(response),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def parse_archive(self, response):
        """
        Parse the City of Tulsa Council Archive search results.
        This source provides comprehensive meeting data with agendas and minutes.
        """
        # Parse the results table
        for row in response.css("#tblMeetings tbody tr"):
            # Extract meeting data from table row
            cells = row.css("td")
            if len(cells) < 2:
                continue

            # Parse date and time from first cell (format: "11/20/2024<br />10:30 AM")
            # Note: there's a hidden span with timestamp that we need to skip
            date_texts = cells[0].css("::text").getall()
            date_texts = [t.strip() for t in date_texts if t.strip() and not t.strip().isdigit()]
            if not date_texts:
                continue

            # Combine date and time if separated by <br>
            date_time_text = " ".join(date_texts)

            # Parse meeting type and links from second cell
            meeting_type = cells[1].css("a::text").get()
            if not meeting_type:
                meeting_type = cells[1].css("::text").get()
            if not meeting_type:
                continue
            meeting_type = meeting_type.strip()

            # Get document links
            doc_link = cells[1].css("a::attr(href)").get()

            start_time = self._parse_start_archive(date_time_text)

            # Try to infer date from search parameters if parsing failed
            if not start_time and "search_date" in response.meta:
                try:
                    # Use the search date as fallback
                    search_date = response.meta["search_date"]
                    start_time = datetime.strptime(search_date, "%m/%d/%Y")
                    self.logger.warning(
                        f"Could not parse date from '{date_time_text}', "
                        f"using search date {search_date} as fallback"
                    )
                except ValueError:
                    self.logger.exception(
                        f"Failed to parse date '{date_time_text}' and fallback failed"
                    )

            # Only skip if we absolutely cannot determine a date
            if not start_time:
                self.logger.warning(
                    f"Skipping meeting '{meeting_type}' - no valid date found"
                )
                continue

            meeting = Meeting(
                title=meeting_type,
                description=self._parse_description(None),
                classification=self._parse_classification(meeting_type),
                start=start_time,
                end=self._parse_end(None),
                all_day=self._parse_all_day(None),
                time_notes=self._parse_time_notes(None),
                location=self._parse_location(None),
                links=self._parse_links_archive(row),
                source=self._parse_source(response),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_title_granicus(self, item):
        """Parse meeting title from Granicus listing."""
        title = item.css(".Name::text").get()
        if title:
            return title.strip()
        return "City Council Meeting"

    def _parse_description(self, item):
        """Parse or generate meeting description."""
        return ""

    def _parse_classification(self, title):
        """Parse or generate classification from meeting title."""
        if not title:
            return NOT_CLASSIFIED

        title_lower = title.lower()

        # Check for committee meetings
        if any(
            term in title_lower
            for term in [
                "committee",
                "budget and special projects",
                "public works",
                "urban and economic development",
            ]
        ):
            return COMMITTEE

        # Check for council meetings
        if any(term in title_lower for term in ["council", "regular", "special"]):
            return CITY_COUNCIL

        return NOT_CLASSIFIED

    def _parse_start_granicus(self, item):
        """Parse start datetime from Granicus listing."""
        # Try both possible CSS selectors
        date_cell = item.css("td[headers='Date']").get()
        if not date_cell:
            date_str = item.css(".Date::text").get()
        else:
            # Parse from the HTML cell content
            cell_selector = Selector(text=date_cell)
            # Get all text and join, handling nbsp and line breaks
            text_parts = cell_selector.css("::text").getall()
            date_str = " ".join([t.strip() for t in text_parts if t.strip()])

        if not date_str:
            return None

        # Clean up the date string (remove extra spaces, nbsp entities)
        date_str = re.sub(r'\s+', ' ', date_str).strip()
        date_str = date_str.replace('\xa0', ' ')  # Replace nbsp

        # Try multiple date formats
        formats = [
            "%B %d, %Y - %I:%M %p",  # November 19, 2025 - 5:00 PM
            "%B %d, %Y - %I:%M%p",  # November 19, 2025 - 5:00PM
            "%B %d, %Y",  # November 19, 2025
            "%B %d , %Y - %I:%M %p",  # December 2, 2025 - 3:30 PM (with space before comma)
            "%B %d , %Y - %I:%M%p",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _parse_start_archive(self, date_time_text):
        """Parse start datetime from Council Archive listing."""
        if not date_time_text:
            return None

        date_time_text = date_time_text.strip()

        # Try multiple date/time formats from the archive
        formats = [
            "%m/%d/%Y %I:%M %p",  # 11/20/2024 10:30 AM
            "%m/%d/%Y %I:%M%p",  # 11/20/2024 10:30AM (no space)
            "%m/%d/%Y",  # 11/20/2024 (no time)
            "%-m/%-d/%Y %I:%M %p",  # 6/4/2025 10:30 AM (no leading zeros)
            "%-m/%-d/%Y",  # 6/4/2025 (no leading zeros, no time)
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_time_text, fmt)
            except ValueError:
                continue

        # Last resort: try to extract date components manually
        try:
            # Match M/D/YYYY or MM/DD/YYYY with optional time
            match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})\s*(AM|PM))?', date_time_text)
            if match:
                month, day, year, hour, minute, ampm = match.groups()
                hour = int(hour) if hour else 0
                minute = int(minute) if minute else 0

                # Convert to 24-hour format
                if ampm == 'PM' and hour != 12:
                    hour += 12
                elif ampm == 'AM' and hour == 12:
                    hour = 0

                return datetime(int(year), int(month), int(day), hour, minute)
        except (ValueError, AttributeError) as e:
            self.logger.debug(f"Regex date parsing failed for '{date_time_text}': {e}")

        return None

    def _parse_end(self, item):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        return None

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        return ""

    def _parse_all_day(self, item):
        """Parse or generate all-day status. Defaults to False."""
        return False

    def _parse_location(self, item):
        """Parse or generate location."""
        return {
            "address": "175 East 2nd Street, Tulsa, OK 74103",
            "name": "City Hall",
        }

    def _parse_links_granicus(self, item):
        """Parse links from Granicus listing."""
        links = []

        # Add agenda link if available
        agenda_href = item.css(".Agenda a::attr(href)").get()
        if agenda_href:
            # Ensure full URL
            if agenda_href.startswith("//"):
                agenda_href = "https:" + agenda_href
            links.append({"href": agenda_href, "title": "Agenda"})

        # Add video link if available and not a placeholder
        video_href = item.css(".Video a::attr(href)").get()
        if video_href and "javascript:void(0)" not in video_href:
            # Ensure full URL
            if video_href.startswith("//"):
                video_href = "https:" + video_href
            links.append({"href": video_href, "title": "Video"})

        return links

    def _parse_links_archive(self, row):
        """Parse links from Council Archive listing."""
        links = []

        # Parse all links in the row (agenda, minutes, etc.)
        for link in row.css("a"):
            href = link.css("::attr(href)").get()
            text = link.css("::text").get()

            if not href or not text:
                continue

            text = text.strip()

            # Ensure full URL
            if href.startswith("/"):
                href = "https://www.cityoftulsa.org" + href
            elif not href.startswith("http"):
                href = "https://www.cityoftulsa.org/apps/" + href

            # Categorize link by text
            if "agenda" in text.lower():
                links.append({"href": href, "title": "Agenda"})
            elif "minute" in text.lower():
                links.append({"href": href, "title": "Minutes"})
            elif "video" in text.lower():
                links.append({"href": href, "title": "Video"})
            else:
                links.append({"href": href, "title": text})

        return links

    def _parse_source(self, response):
        """Parse or generate source."""
        return response.url
