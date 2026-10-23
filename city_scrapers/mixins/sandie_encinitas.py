import re
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
import scrapy
from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import ParserError
from dateutil.parser import parse as dateutil_parse


class SandieEncinitasMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from the "Mixin" class.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "bodies"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class SandieEncinitasMixin(CityScrapersSpider, metaclass=SandieEncinitasMixinMeta):
    name = None
    agency = None
    bodies = None
    exclude_pattern = None
    timezone = "America/Los_Angeles"

    base_url = "https://www.encinitasca.gov/government/agendas-webcasts"
    granicus_url = "https://encinitas.granicus.com/ViewPublisher.php?view_id=7"
    agenda_url = (
        "https://encinitas.granicus.com/GeneratedAgendaViewer.php?view_id=7&{}"  # noqa
    )

    # Rolling window: meetings older than this are skipped. All upcoming
    # meetings are always included.
    lookback_days = 365 * 2

    # Agenda pages for meetings whose agenda is a PDF attachment only have a
    # header (~40 words) whose date, time and location are template defaults,
    # while the shortest real agendas have ~90 words.
    agenda_min_words = 75
    # Agenda header times outside of these hours are data entry errors
    # (e.g. a Parks and Recreation Commission meeting at "11:30 PM")
    agenda_earliest_hour = 7
    agenda_latest_hour = 21

    default_location = {
        "name": "Encinitas City Hall, Council Chambers",
        "address": "505 S. Vulcan Avenue, Encinitas, CA 92024",
    }
    time_notes = "Please refer to the meeting agenda for the most accurate start time and location."  # noqa

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # e.g. "6:00 p.m.", "4:00 P.M.", "9:00 a.m", "4:00PM"
    time_re = re.compile(r"\b\d{1,2}:\d{2}\s*[ap]\.?\s*m\b\.?", re.IGNORECASE)
    # Notes about amendments to the agenda, e.g. "(Item 8I added 9/19/2025)",
    # "(10D(i) and 10D(ii) Added 6/18/2025)" or "Item #3 Added"
    amendment_note_re = re.compile(
        r"\((?:[^()]|\([^()]*\))*?"
        r"\b(?:added|updated|removed|corrected|rescheduled|amended)\b"
        r"(?:[^()]|\([^()]*\))*\)"
        r"|\bitems?\s+#?\S+\s+added\b",
        re.IGNORECASE,
    )
    # "AMENDED" markers plus any trailing description of the amendment, e.g.
    # "AMENDED to remove Item 12B", "AMENDED 2-15-24 Item 8H", "POSTED 08-07-25"
    amended_re = re.compile(
        r"^amended\s+(?:\d{1,2}-\d{1,2}-\d{2,4}\s+)?|\s+(?:amended|posted)\b.*$",
        re.IGNORECASE,
    )
    cancelled_re = re.compile(r"\bcancel+ed\b", re.IGNORECASE)
    closed_session_re = re.compile(r"\bclosed\s+session", re.IGNORECASE)
    onclick_url_re = re.compile(r"window\.open\('([^']+)'")
    clip_id_re = re.compile(r"clip_id=(\d+)")
    event_id_re = re.compile(r"event_id=(\d+)")
    date_re = re.compile(
        r"(?:january|february|march|april|may|june|july|august|september|october|"
        r"november|december)\s+\d{1,2},\s+\d{4}",
        re.IGNORECASE,
    )

    def start_requests(self):
        yield scrapy.Request(self.granicus_url, callback=self.parse)

    def parse(self, response):
        now = datetime.now(pytz.timezone(self.timezone)).replace(tzinfo=None)
        cutoff = now - timedelta(days=self.lookback_days)
        meetings = {}
        # IDs of meetings whose start time is only a date
        missing_time_ids = set()

        archive_rows = []
        for panel in response.css(".CollapsiblePanel"):
            panel_name = self._clean_text(
                panel.css(".CollapsiblePanelTab h2::text").get()
            )
            for row in panel.css("li.table-row:not(.table-row--head)"):
                raw_title = self._clean_text(row.css(".archive-name::text").get())
                # Placeholder rows linking to older archives don't have a title
                body = self._match_body(raw_title) if raw_title else None
                if body is None:
                    continue
                title_time = self._parse_title_time(raw_title)
                start = self._parse_start(
                    row.css(".archive-date::text").get(), title_time
                )
                if start:
                    is_own_panel = body.get("panel") == panel_name
                    archive_rows.append(
                        (is_own_panel, start, body, row, raw_title, title_time)
                    )

        # Rows from the body's own panel go first, other panels' listings of
        # the same meeting are ignored. Rows are sorted by start time so that
        # meetings with the same title on the same day always get the same IDs.
        own_panel_keys = set()
        for is_own_panel, start, body, row, raw_title, title_time in sorted(
            archive_rows, key=lambda archive_row: (not archive_row[0], archive_row[1])
        ):
            key = (self.bodies.index(body), start)
            if is_own_panel:
                own_panel_keys.add(key)
            elif key in own_panel_keys:
                continue
            meeting = self._add_meeting(
                meetings, self._create_meeting(row, raw_title, start, cutoff)
            )
            if meeting is not None and title_time is None:
                missing_time_ids.add(meeting["id"])

        # Archived listings take priority over upcoming listings of the same meeting
        archived = defaultdict(list)
        for meeting in meetings.values():
            archived[self._get_listing_key(meeting)].append(meeting)

        upcoming = []
        for row in response.css(".upcoming-list li.table-row:not(.table-row--head)"):
            raw_title = self._clean_text(row.css(".upcoming-name::text").get())
            if not raw_title or self._match_body(raw_title) is None:
                continue
            # e.g. "October 20, 2026 - 02:00 PM"
            date_str, _, time_str = self._clean_text(
                row.css(".upcoming-date::attr(data-eventdate)").get()
            ).partition(" - ")
            start = self._parse_start(
                date_str, self._parse_title_time(raw_title) or time_str
            )
            event_id = self._parse_event_id(row)
            if not start and event_id:
                yield scrapy.Request(
                    self.agenda_url.format(f"event_id={event_id}"),
                    callback=self._parse_upcoming_agenda,
                    errback=self._handle_agenda_error,
                    cb_kwargs={
                        "row": row,
                        "raw_title": raw_title,
                        "archived": archived,
                    },
                    dont_filter=True,
                )
                continue
            meeting = self._create_meeting(row, raw_title, start, cutoff)
            if meeting and not self._is_archived(meeting, archived):
                upcoming.append(meeting)
        for meeting in sorted(upcoming, key=lambda meeting: meeting["start"]):
            self._add_meeting(meetings, meeting)

        # For meetings whose start time is only a date, fetch
        # the agenda to recover the time
        for meeting_id, meeting in meetings.items():
            clip_id = self._parse_clip_id(meeting)
            if meeting_id in missing_time_ids and clip_id:
                yield scrapy.Request(
                    self.agenda_url.format(f"clip_id={clip_id}"),
                    callback=self._parse_agenda,
                    errback=self._handle_agenda_error,
                    cb_kwargs={"meeting": meeting},
                )
            else:
                yield meeting

    def _create_meeting(self, row, raw_title, start, cutoff=None):
        """Create a meeting from a listing row if it's in the window and matches"""
        if not start or (cutoff and start < cutoff):
            return None
        body = self._match_body(raw_title)
        if body is None:
            return None

        meeting = Meeting(
            title=self._parse_title(raw_title),
            description="",
            classification=body["classification"],
            start=start,
            end=None,
            all_day=False,
            closed_to_public=bool(self.closed_session_re.search(raw_title)),
            time_notes=self.time_notes,
            location=body.get("location", self.default_location),
            links=self._parse_links(row),
            source=self.base_url,
        )
        # Amendment notes are removed so that e.g. "(10A & 10B Rescheduled)"
        # doesn't mark the meeting as cancelled
        meeting["status"] = self._get_status(
            meeting, text=self.amendment_note_re.sub("", raw_title)
        )
        meeting["id"] = self._get_stable_id(meeting)
        return meeting

    def _get_stable_id(self, meeting):
        """Create an ID from the meeting's date, which doesn't change once archived"""
        return self._get_id(
            {
                "title": meeting["title"],
                "start": meeting["start"].replace(hour=0, minute=0),
            }
        )

    def _add_meeting(self, meetings, meeting):
        """
        Add a meeting unless it's already listed (e.g. a row repeated in the same
        panel), returning the meeting if it was added
        """
        if meeting is None:
            return None
        existing = meetings.get(meeting["id"])
        if existing is not None:
            if not self._is_separate_meeting(existing, meeting):
                return None
            # Meetings with the same title on the same day at different times
            # keep IDs based on their start times so they don't collide
            meeting["id"] = self._get_id(meeting)
            if meeting["id"] in meetings:
                return None
        meetings[meeting["id"]] = meeting
        return meeting

    def _is_separate_meeting(self, meeting, other):
        """Whether meetings with the same ID have different known start times"""
        return all(m["start"].hour or m["start"].minute for m in (meeting, other)) and (
            meeting["start"] != other["start"]
        )

    def _get_listing_key(self, meeting):
        """Identify a meeting across the upcoming and archived listings"""
        return meeting["start"].date(), meeting["title"].lower()

    def _is_archived(self, meeting, archived):
        """
        Whether an upcoming meeting is also listed in the archive, as opposed to
        a separate meeting with the same title later on the same day
        """
        return any(
            not self._is_separate_meeting(meeting, archived_meeting)
            for archived_meeting in archived.get(self._get_listing_key(meeting), [])
        )

    def _parse_agenda(self, response, meeting):
        """Recover a meeting's start time from the header of its agenda"""
        start = self._parse_agenda_start(response, meeting["start"])
        if start:
            meeting["start"] = start
            # Cancellation notes were removed from the title, so keep that status
            if meeting["status"] != CANCELLED:
                meeting["status"] = self._get_status(meeting)
        yield meeting

    def _parse_upcoming_agenda(self, response, row, raw_title, archived):
        """Take the date and time of an upcoming meeting without one from its agenda"""
        start = self._parse_agenda_start(response)
        title_time = self._parse_title_time(raw_title)
        if start and title_time:
            start = self._parse_start(start.strftime("%B %d, %Y"), title_time)
        if not start:
            self.logger.warning(
                f"Skipping upcoming meeting {raw_title!r} without a listed date "
                "or a date in its agenda"
            )
            return
        meeting = self._create_meeting(row, raw_title, start)
        if meeting and not self._is_archived(meeting, archived):
            yield meeting

    def _handle_agenda_error(self, failure):
        """Log the error and parse the meeting without its agenda"""
        self.logger.warning(
            f"Failed to fetch agenda {failure.request.url}: {failure.value!r}"
        )
        yield from failure.request.callback(None, **failure.request.cb_kwargs)

    def _parse_agenda_start(self, response, date=None):
        """
        Find the time following the meeting date (or the first date if it's not
        known) in the agenda header, e.g. "OCTOBER 1, 2026 - 06:00 PM" or
        "Tuesday, September 1, 2026 4:00PM"
        """
        if response is None:
            return None
        words = response.xpath(
            "//body//text()[not(ancestor::style) and not(ancestor::script)]"
        ).getall()
        text = self._clean_text(" ".join(words))
        if len(text.split()) < self.agenda_min_words:
            return None
        if date:
            date_re = rf"{date.strftime('%B')}\s+{date.day},\s+{date.year}"
        else:
            date_re = self.date_re.pattern
        match = re.search(
            rf"({date_re})[\s,\-–]*(?:at\s+)?({self.time_re.pattern})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        start = self._parse_start(match.group(1), match.group(2))
        if start and not (
            self.agenda_earliest_hour <= start.hour <= self.agenda_latest_hour
        ):
            return None
        return start

    def _parse_start(self, date_str, time_str=None):
        """Parse a date (e.g. 'October 14, 2026') and time (e.g. '6:00 p.m.')"""
        date_str = self._clean_text(date_str)
        if not date_str:
            return None
        try:
            # Lowercase since dateutil reads the "M" in "P.M." as a timezone
            return dateutil_parse(f"{date_str} {time_str or ''}".lower())
        except (ParserError, ValueError, OverflowError) as e:
            self.logger.warning(
                f"Failed to parse start from {date_str!r} and {time_str!r}: {e}"
            )
            return None

    def _parse_title_time(self, raw_title):
        """Return the start time in a title, e.g. '6:00 p.m.', if there is one"""
        # Ignore times inside amendment notes, e.g. "(... added 12-3-2024 12:20 p.m.)"
        match = self.time_re.search(self.amendment_note_re.sub("", raw_title))
        return match.group(0) if match else None

    def _parse_event_id(self, row):
        for href in row.css(".upcoming-agenda a::attr(href)").getall():
            match = self.event_id_re.search(href)
            if match:
                return match.group(1)
        return None

    def _parse_clip_id(self, meeting):
        for link in meeting["links"]:
            match = self.clip_id_re.search(link["href"])
            if match:
                return match.group(1)
        return None

    def _match_body(self, title):
        if self.exclude_pattern and re.search(
            self.exclude_pattern, title, re.IGNORECASE
        ):
            return None
        for body in self.bodies:
            if re.search(body["pattern"], title, re.IGNORECASE):
                return body
        return None

    def _clean_text(self, text):
        return " ".join((text or "").split())

    def _parse_title(self, raw_title):
        """Remove start times, cancellation and amendment notes from the title"""
        title = self.amendment_note_re.sub("", raw_title)
        title = self.time_re.sub("", title)
        title = self.cancelled_re.sub("", title)
        title = self.amended_re.sub("", title.strip())
        title = re.sub(r"\(\s*\)", "", title)
        title = self._clean_text(title)
        # Drop dangling separators left behind, e.g. "Meeting -" or "- Meeting"
        return re.sub(r"^[\s\-:]+|[\s\-:]+$", "", title)

    def _parse_links(self, row):
        links = []
        for link in row.css("a"):
            # e.g. "Open Video Only in Windows Media Player" for meetings in progress
            if "display:none" in link.attrib.get("style", "").replace(" ", ""):
                continue
            href = link.attrib.get("href", "")
            if href.startswith("javascript"):
                match = self.onclick_url_re.search(link.attrib.get("onclick", ""))
                href = match.group(1) if match else ""
            if not href:
                continue
            if href.startswith("//"):
                href = "https:" + href
            title = self._clean_text(" ".join(link.css("::text").getall()))
            # The live video link of meetings in progress
            if title.lower() == "in progress":
                title = "Video"
            links.append({"href": href, "title": title})
        return links
