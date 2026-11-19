import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytz
import scrapy
from city_scrapers_core.constants import NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import ParserError
from dateutil.parser import parse as dateutil_parse


class SandieEscondidoCityMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from the "Mixin" class.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "microsite_id"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class SandieEscondidoCityMixin(
    CityScrapersSpider, metaclass=SandieEscondidoCityMixinMeta
):
    """
    Scrapes the Escondido meetings portal (a Drupal 7 site),
    which lists the meetings of every body in one table. Each spider requests
    the table filtered to its own body ("microsite") with the
    `field_microsite_tid` query parameter, e.g. 2 for the City Council.

    The portal only lists most bodies' meetings about a month ahead, so spiders
    with a `calendar_pattern` also scrape upcoming meetings whose titles match it
    from the "City Meetings" calendar of the city's CivicPlus site. Meetings
    already listed on the portal at the same time are skipped, since the portal
    has their agendas and other documents.
    """

    name = None
    agency = None
    microsite_id = None
    classification = NOT_CLASSIFIED
    timezone = "America/Los_Angeles"

    base_url = "https://escondido-ca.municodemeetings.com"
    list_url = base_url + "/?field_microsite_tid={}"

    calendar_url = "https://ca-escondido.civicplus.com/calendar.aspx"
    # The calendar responds with "404 Not Found" to the City Scrapers user agent
    calendar_user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )
    # The "City Meetings" calendar list meetings of boards and commissions.
    calendar_id = 30
    # Titles of the body's meetings in the calendar, e.g. r"planning\s+commission",
    # or None to not scrape the calendar
    calendar_pattern = None
    # Titles of other bodies' meetings that also match the pattern, e.g.
    # "Public Art Commission Subcommittee Meeting" for the Public Art Commission
    calendar_exclude_pattern = None
    city_hall_address = "201 N. Broadway"

    lookback_days = 365 * 2
    # By default the listing only shows meetings up to a month ahead, so the
    # end of its date range ("date_filter_1") is set to this far ahead. The
    # pager links keep the date range.
    lookahead_days = 365

    # Agenda packets list the room at City Hall where each body meets
    location = {
        "name": "Escondido City Hall, Council Chambers",
        "address": "201 N. Broadway, Escondido, CA 92025",
    }

    # A note about the closed session, e.g. "(Closed Session 4:00 PM)",
    # "(Closed Session 4:00 PM - Cancelled)" or "(Cancelled - Closed Session
    # 4:00 PM)". The whole note is used for the closed session's time and status.
    # "(No Closed Session)" isn't a closed session, so it's left in the title.
    closed_session_re = re.compile(
        r"\((?![^()]*\bno\s+closed\s+session\b)([^()]*\bclosed\s+session\b[^()]*)\)",
        re.IGNORECASE,
    )
    # Rows that are only a closed session, e.g. "Closed Session Council Meeting",
    # but not "Special Meeting (No Closed Session)"
    closed_session_title_re = re.compile(
        r"(?<!\bno\s)\bclosed\s+session\b", re.IGNORECASE
    )
    time_re = re.compile(r"\d{1,2}:\d{2}\s*[ap]\.?m\.?", re.IGNORECASE)
    # A time at the end of a title, e.g. " - 4pm" or " - 4:00 P.M."
    title_time_re = re.compile(
        r"\s*[-–]?\s*\b\d{1,2}(?::\d{2})?\s*[ap]\.?m\b\.?$", re.IGNORECASE
    )
    council_special_re = re.compile(r"\bcouncil\s+special\s+meeting\b", re.IGNORECASE)

    link_columns = [
        ("views-field-field-packets", "Agenda Packet"),
        ("views-field-field-minutes", "Minutes"),
        ("views-field-field-video-link", "Video"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # IDs of meetings already yielded, as the listing sometimes repeats a
        # meeting (e.g. two "Planning Commission Meeting" entries at the same time)
        self.seen_ids = set()
        # Start times of the meetings listed on the portal, which are skipped in
        # the calendar
        self.seen_starts = set()

    def start_requests(self):
        now = datetime.now(pytz.timezone(self.timezone)).replace(tzinfo=None)
        end = now + timedelta(days=self.lookahead_days)
        params = {
            "date_filter_1[value][month]": end.month,
            "date_filter_1[value][day]": end.day,
            "date_filter_1[value][year]": end.year,
        }
        url = self.list_url.format(self.microsite_id) + "&" + urlencode(params)
        yield scrapy.Request(url)

    def parse(self, response):
        now = datetime.now(pytz.timezone(self.timezone)).replace(tzinfo=None)
        cutoff = now - timedelta(days=self.lookback_days)
        reached_cutoff = False

        for row in response.css("table tbody tr"):
            start = self._parse_start(row)
            if start is None:
                continue
            if start < cutoff:
                reached_cutoff = True
                continue

            raw_title = self._clean_text(
                " ".join(row.css("td.views-field-title ::text").getall())
            )
            meetings = []
            for meeting in self._create_meetings(row, response, raw_title, start):
                self.seen_starts.add(meeting["start"])
                if meeting["id"] not in self.seen_ids:
                    self.seen_ids.add(meeting["id"])
                    meetings.append(meeting)
            if not meetings:
                continue

            # The video column links to the meeting's details page, which has
            # the link to the video itself
            video_page = row.css("td.views-field-field-video-link a::attr(href)").get()
            if video_page:
                yield scrapy.Request(
                    response.urljoin(video_page),
                    callback=self._parse_video,
                    errback=self._handle_video_error,
                    cb_kwargs={"meetings": meetings},
                    dont_filter=True,
                )
            else:
                yield from meetings

        next_page = response.css(".pager a::attr(href)").get()
        if next_page and not reached_cutoff:
            yield response.follow(next_page, callback=self.parse)
        elif self.calendar_pattern:
            # The calendar is requested once all of the portal's pages are parsed,
            # so that the meetings listed on both can be skipped
            yield self._calendar_request()

    def _calendar_request(self):
        """Request the calendar's meetings from today up to the lookahead"""
        now = datetime.now(pytz.timezone(self.timezone)).replace(tzinfo=None)
        end = now + timedelta(days=self.lookahead_days)
        params = {
            "Keywords": "",
            "startDate": now.strftime("%m/%d/%Y"),
            "enddate": end.strftime("%m/%d/%Y"),
            "CID": self.calendar_id,
            "showPastEvents": "false",
        }
        return scrapy.Request(
            f"{self.calendar_url}?{urlencode(params)}",
            callback=self._parse_calendar,
            headers={"User-Agent": self.calendar_user_agent},
            dont_filter=True,
        )

    def _parse_calendar(self, response):
        """Parse the body's upcoming meetings that aren't listed on the portal"""
        for event in response.css(f"#CID{self.calendar_id} ol > li"):
            raw_title = self._clean_text(
                event.css("[itemscope] > [itemprop=name]::text").get()
            )
            if not re.search(self.calendar_pattern, raw_title, re.IGNORECASE):
                continue
            if self.calendar_exclude_pattern and re.search(
                self.calendar_exclude_pattern, raw_title, re.IGNORECASE
            ):
                continue
            start = self._parse_calendar_start(event)
            if start is None or start in self.seen_starts:
                continue

            title = self._parse_title(raw_title)
            meeting = Meeting(
                title=title,
                description="",
                classification=self.classification,
                start=start,
                end=None,
                all_day=False,
                closed_to_public=bool(self.closed_session_title_re.search(title)),
                time_notes="",
                location=self._parse_calendar_location(event),
                links=[],
                source=self._parse_calendar_source(event, response),
            )
            meeting["status"] = self._get_status(meeting, text=raw_title)
            meeting["id"] = self._get_id(meeting)
            if meeting["id"] in self.seen_ids:
                continue
            self.seen_ids.add(meeting["id"])
            yield meeting

    def _parse_calendar_start(self, event):
        """Parse the start from the event's data, e.g. "2026-12-08T19:00:00" """
        start_str = event.css("[itemprop=startDate]::text").get()
        try:
            return datetime.fromisoformat(start_str.strip()).replace(tzinfo=None)
        except (AttributeError, ValueError):
            self.logger.warning(f"Failed to parse calendar start from {start_str!r}")
            return None

    def _parse_calendar_location(self, event):
        """
        Parse the location from the event's data, e.g. "Council Chambers" at
        "201 N. Broadway"
        """
        location = event.css("[itemprop=location]")
        name = self._clean_text(location.css("[itemprop=name]::text").get())
        street = self._clean_text(location.css("[itemprop=streetAddress]::text").get())
        if not name and not street:
            return self.location
        if street.lower() == self.city_hall_address.lower():
            return {
                "name": (
                    f"Escondido City Hall, {name}" if name else "Escondido City Hall"
                ),
                "address": self.location["address"],
            }
        return {
            "name": name,
            "address": f"{street}, Escondido, CA" if street else "",
        }

    def _parse_calendar_source(self, event, response):
        """
        The event's details page, e.g. "/Calendar.aspx?EID=965". The link's
        other parameters are the date the calendar was viewed, so they're removed
        to keep the source the same from day to day.
        """
        href = event.css("h3 a::attr(href)").get() or ""
        match = re.search(r"\bEID=(\d+)", href)
        if not match:
            return response.url
        return response.urljoin(f"/Calendar.aspx?EID={match.group(1)}")

    def _parse_video(self, response, meetings):
        """
        The video link from the details page with the link to the video,
        e.g. "https://escondido.12milesout.com/Video/Meeting/<id>"
        """
        video_url = response.css(".field-name-field-video-link a::attr(href)").get()
        for meeting in meetings:
            for link in meeting["links"]:
                if link["title"] != "Video":
                    continue
                if video_url:
                    link["href"] = response.urljoin(video_url)
                else:
                    self.logger.warning(f"No video link found on {response.url}")
            yield meeting

    def _handle_video_error(self, failure):
        """Keep the video link to the details page if it can't be fetched"""
        self.logger.warning(
            f"Failed to fetch details page {failure.request.url}: {failure.value!r}"
        )
        yield from failure.request.cb_kwargs["meetings"]

    def _create_meetings(self, row, response, raw_title, start):
        """
        Create the meetings listed in a row. A row with a closed session note,
        e.g. "Council Meeting (Closed Session 4:00 PM)", lists two meetings: the
        regular meeting at the row's time and a closed session before it. Either
        one can be cancelled on its own:
        - "Cancelled - Council Meeting (Closed Session 4:00 PM)": the regular
          meeting is cancelled
        - "Council Meeting (Closed Session 4:00 PM - Cancelled)": the closed
          session is cancelled
        """
        title = self._parse_title(raw_title)
        closed_session = self.closed_session_re.search(raw_title)
        # The regular meeting's part of the title, e.g. "Cancelled - Council Meeting"
        regular_text = self.closed_session_re.sub("", raw_title)
        meetings = [
            self._create_meeting(
                row,
                response,
                title=title,
                start=start,
                status_text=regular_text,
                # e.g. "Closed Session Council Meeting"
                closed_to_public=bool(self.closed_session_title_re.search(title)),
            )
        ]
        if closed_session:
            note = closed_session.group(1)
            meetings.append(
                self._create_meeting(
                    row,
                    response,
                    title=f"{title} (Closed Session)",
                    start=self._parse_closed_session_start(start, note),
                    status_text=note,
                    closed_to_public=True,
                )
            )
        return meetings

    def _create_meeting(
        self, row, response, title, start, status_text, closed_to_public
    ):
        meeting = Meeting(
            title=title,
            description="",
            classification=self.classification,
            start=start,
            end=None,
            all_day=False,
            closed_to_public=closed_to_public,
            time_notes="",
            location=self.location,
            links=self._parse_links(row, response),
            source=self._parse_source(row, response),
        )
        meeting["status"] = self._get_status(meeting, text=status_text)
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _parse_closed_session_start(self, start, note):
        """
        Take the closed session's time from its note, e.g. " 4:00 PM - Cancelled",
        or the regular meeting's time if it isn't listed
        """
        time_match = self.time_re.search(note)
        if not time_match:
            return start
        try:
            time = dateutil_parse(time_match.group(0).lower().replace(".", ""))
        except (ParserError, ValueError, OverflowError):
            self.logger.warning(f"Failed to parse time from {note!r}")
            return start
        return start.replace(hour=time.hour, minute=time.minute)

    def _parse_start(self, row):
        """
        Parse the start from the ISO datetime in the date column, e.g.
        "2026-12-16T17:00:00-08:00", falling back to its text, e.g.
        "12/16/2026 - 5:00pm"
        """
        date_cell = row.css(".date-display-single")
        iso_date = date_cell.attrib.get("content") if date_cell else None
        if iso_date:
            try:
                return datetime.fromisoformat(iso_date).replace(tzinfo=None)
            except ValueError:
                self.logger.warning(
                    f"Failed to parse ISO start {iso_date!r}, falling back to text"
                )
        date_text = self._clean_text(
            " ".join(row.css("td:first-child ::text").getall())
        )
        if not date_text:
            return None
        try:
            return dateutil_parse(date_text.replace(" - ", " "))
        except (ParserError, ValueError, OverflowError):
            self.logger.warning(f"Failed to parse start from {date_text!r}")
            return None

    def _parse_title(self, raw_title):
        """Remove cancellation, closed session and time notes from the title"""
        title = self._clean_text(self.closed_session_re.sub("", raw_title))
        title = self._clean_title(title)
        # The start time is in the date column, e.g. "Council Special Meeting - 4pm"
        title = self.title_time_re.sub("", title)
        # e.g. "Council Special Meeting", like the other "Special Council Meeting"s
        return self.council_special_re.sub("Special Council Meeting", title)

    def _parse_links(self, row, response):
        links = []
        for column, title in self.link_columns:
            for href in row.css(f"td.{column} a::attr(href)").getall():
                links.append({"href": response.urljoin(href), "title": title})
        return links

    def _parse_source(self, row, response):
        """The meeting's details page, or the listing if there isn't one"""
        href = row.css("td.views-field-view-node a::attr(href)").get()
        return response.urljoin(href) if href else response.url

    def _clean_text(self, text):
        return " ".join((text or "").split())
