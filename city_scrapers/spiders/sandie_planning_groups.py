"""
City of San Diego Community Planning Groups.

One spider for every planning group, discovered at run time:

1. The community list on https://www.sandiego.gov/planning/community-plans
   links to each community's page.
2. Each community page links to the planning group that covers it (its own
   ".../<community>/planning-group" page, or a neighbouring group's).
3. Each planning group page has a "Meeting Info" box (regular time and
   location) and "Agendas" / "Minutes" tabs that list the meetings.

A community added to the city's list is picked up automatically. Major
breakages (failed requests, a missing community list, no meetings, a
site-wide "Meeting Info" change) are reported once on close through the
`spider_error` signal, which forwards them to Sentry.
Problems with single entries or pages are only logged.
"""

import html
import re
from collections import OrderedDict
from datetime import datetime, time
from urllib.parse import urlparse

import pytz
import scrapy
from city_scrapers_core.constants import BOARD, CANCELLED, COMMITTEE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta
from scrapy import signals
from twisted.python.failure import Failure

_GROUP_PATH_RE = re.compile(r"^/planning/community-plans/[^/]+/planning-group$")

# "Meeting Info" notes saying the location is not fixed: "Virtual Meetings –
# See Agenda for Link", "Check the agenda for the meeting location"
_LOCATION_NOTE_RE = re.compile(
    r"\bvirtual\b|\b(?:check|see)\b.*\bagenda\b", re.IGNORECASE
)


class SandiePlanningGroupsError(Exception):
    """A San Diego planning group source could not be read as expected."""


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Month abbreviations
_MONTH_ALIASES = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}

_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_MONTH_RE = (
    r"(?P<month>"
    + "|".join(sorted(list(_MONTHS) + list(_MONTH_ALIASES), key=len, reverse=True))
    + r")\.?"
)
_DAY_RE = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR_RE = r"(?P<year>(?:19|20)\d{2})"

# "February 10, & 11 2026"
_RANGE_RE = re.compile(
    rf"\b{_MONTH_RE}\s*,?\s*(?P<day1>\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*"
    rf"(?:&|and)\s*(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?:\s*[,.]?\s*{_YEAR_RE})?(?!\d)",
    re.IGNORECASE,
)
# "October 20, 2026", "October 13 , 2026", "March 17" (year from the heading)
_SINGLE_RE = re.compile(
    rf"\b{_MONTH_RE}\s*,?\s*{_DAY_RE}(?!\d)"
    # Year, or a truncated year typo ("December 2, 202") that is dropped so the
    # accordion year heading is used instead
    rf"(?:\s*[,.]?\s*{_YEAR_RE}(?!\d)|\s*,\s*\d{{1,3}}(?!\d))?",
    re.IGNORECASE,
)
# "8 de septiembre de 2025", "12 de julio del 2025"
_SPANISH_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+de\s+(?P<month>"
    + "|".join(_SPANISH_MONTHS)
    + r")\s+(?:de|del)\s+(?P<year>(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
# Month + year only ("June 2026 - Meeting Adjourned"); no day, so no meeting
_MONTH_ONLY_RE = re.compile(rf"\b{_MONTH_RE}\s*,?\s*{_YEAR_RE}\b", re.IGNORECASE)

_STATUS_NOISE_RE = re.compile(
    r"\b(?:"
    r"(?:notice\s+of\s+)?(?:meeting\s+)?(?:"
    r"cancel\w*|adjourn\w*|postpone\w*|reschedul\w*\b.*|date\s+change"
    r")(?:\s*(?:and|&|/)\s*(?:cancel\w*|adjourn\w*|postpone\w*|reschedul\w*\b.*))?"
    r"(?:\s+notice)?"
    r"|no\s+meeting(?:\s+notice)?"
    r")",
    re.IGNORECASE,
)
_DOC_NOISE_RE = re.compile(
    r"\b(?:revised|amended|draft|updated|final|approved)\b"
    r"|\b(?:agendas?|minutes)\b"
    r"|\bnotice\b(?=\s*(?:$|[-–—(:]))"
    r"|\benglish\s+and\s+spanish\b",
    re.IGNORECASE,
)
_GENERIC_TITLE_RE = re.compile(
    r"^(?:regular|general|board|monthly|planning\s+group|cpg)?\s*(?:meeting)?$",
    re.IGNORECASE,
)
# Other names La Jolla uses for its regular board meeting ("LJCPA" is the La
# Jolla Community Planning Association)
_MAIN_BOARD_ALIAS_RE = re.compile(
    r"^(?:ljcpa|trustees?)(?:\s+meeting)?$", re.IGNORECASE
)

# Words that say nothing about which meeting a document belongs to
_TITLE_STOP_WORDS = {
    "meeting",
    "committee",
    "subcommittee",
    "board",
    "the",
    "of",
    "and",
    "ad",
    "hoc",
    "adhoc",
    "a",
    "la",
    "jolla",
    "special",
}
# A document is matched to a meeting when its title is at least this similar
# (0-1) to the meeting's
_MATCH_THRESHOLD = 0.5
_CANCELLED_RE = re.compile(
    r"cancel|postpone|reschedul|adjourn|no\s+meeting|date\s+change|aplazad",
    re.IGNORECASE,
)
_COMMITTEE_RE = re.compile(
    r"\bcommittees?\b|subcommittee|task\s*force|ad[-\s]?hoc",
    re.IGNORECASE,
)


class SandiePlanningGroupsSpider(CityScrapersSpider):
    name = "sandie_planning_groups"
    agency = "San Diego City Community Planning Groups"
    timezone = "America/Los_Angeles"

    tz = pytz.timezone(timezone)

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    base_url = "https://www.sandiego.gov"
    index_url = "https://www.sandiego.gov/planning/community-plans"

    # Pages with the planning group layout that the community list does not
    # link to. The Community Planners Committee is the citywide committee of
    # planning group chairs.
    extra_group_paths = ["/planning/community-plans/community-planners-committee"]

    # Planning group pages that are archives, not active groups.
    skip_group_paths = {
        # "combined into the Carmel Mountain Ranch/Sabre Springs Community
        # Committee in 2013"; only 2009-2012 documents, no Meeting Info box.
        "/planning/community-plans/sabre-springs/planning-group",
    }

    # Group names for pages whose heading doesn't tell them apart: the Miramar
    # Ranch North page is headed "Scripps Ranch Community Planning Group", like
    # the Scripps Miramar Ranch page, but lists different meetings.
    group_name_overrides = {
        "/planning/community-plans/miramar-ranch-north/planning-group": (
            "Scripps Ranch Community Planning Group (Miramar Ranch North)"
        ),
    }

    # Only meetings from the last two years are published
    lookback_years = 2

    time_notes = (
        "Please refer to the meeting attachments for more accurate meeting time "
        "and location."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._problems = []
        self._failed_requests = 0
        self._meetings_parsed = 0
        self._requested_groups = set()
        self._group_pages = set()
        self._groups_parsed = 0
        self._groups_without_meeting_info = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider._on_spider_closed, signal=signals.spider_closed)
        return spider

    # ------------------------------------------------------------------ #
    # Discovery: index -> community pages -> planning group pages
    # ------------------------------------------------------------------ #

    def start_requests(self):
        yield self._request(self.index_url, self.parse)

    def _request(self, url, callback):
        return scrapy.Request(url, callback=callback, errback=self._request_failed)

    def parse(self, response):
        """Follow every community in the index's community list."""
        communities = response.xpath("//div[@id='tab-item-1']//ul/li/a/@href").getall()
        if not communities:
            self._add_problem(
                "community list (div#tab-item-1) not found on the community "
                f"plans index; the page layout may have changed (url={response.url})"
            )
        for href in communities:
            yield self._request(response.urljoin(href), self.parse_community)
        for path in self.extra_group_paths:
            yield from self._group_request(self.base_url + path)

    def parse_community(self, response):
        """Request the planning group(s) a community page links to."""
        found = False
        for href in response.xpath("//a/@href").getall():
            url = response.urljoin(href)
            if _GROUP_PATH_RE.match(self._path(url)):
                found = True
                yield from self._group_request(url)
        if not found:
            # e.g. East Elliott: "No active community planning group at this time"
            self.logger.info(f"No planning group linked from {response.url}")

    def _group_request(self, url):
        path = self._path(url)
        if path in self.skip_group_paths or path in self._requested_groups:
            return
        self._requested_groups.add(path)
        yield self._request(self.base_url + path, self.parse_group)

    def _path(self, url):
        return urlparse(url).path.rstrip("/")

    def _request_failed(self, failure):
        """
        Without an errback, HTTP errors (404/500) and network failures are only
        logged by Scrapy and never reach Sentry; reported on spider close.
        """
        self._failed_requests += 1
        request = getattr(failure, "request", None)
        url = request.url if request else self.index_url
        self._add_problem(f"request to {url} failed: {failure.value!r}")

    # ------------------------------------------------------------------ #
    # Planning group pages
    # ------------------------------------------------------------------ #

    def parse_group(self, response):
        path = self._path(response.url)
        if path in self._group_pages:
            # Two links that redirect to the same group page
            return
        self._group_pages.add(path)

        agenda_tab = response.xpath("//div[@id='tab-item-1']")
        if not agenda_tab:
            # One page is logged; if it happens site-wide, "0 meetings parsed"
            # is reported on close.
            self.logger.warning(f"Agendas tab not found on {response.url}")
            return
        self._groups_parsed += 1
        minutes_tab = response.xpath("//div[@id='tab-item-2']")

        group = self._parse_group_name(response)
        meeting_time, location, description = self._parse_meeting_info(response)

        entries = self._parse_entries(agenda_tab, "Agenda", response)
        entries += self._parse_entries(minutes_tab, "Minutes", response)
        records = self._group_entries(entries, meeting_time)
        if not records:
            self.logger.warning(f"No meetings listed for {group} ({response.url})")

        for record in records:
            title = self._group_title(group, record["title"])
            meeting = Meeting(
                title=title,
                description=description,
                classification=self._parse_classification(record["title"], group),
                start=record["start"],
                end=None,
                all_day=False,
                time_notes=self.time_notes,
                location=location,
                links=record["links"],
                source=response.url,
            )
            meeting["status"] = self._get_status(
                meeting, " ".join(record["status_text"])
            )
            meeting["id"] = self._get_id(meeting)
            self._meetings_parsed += 1
            yield meeting

    def _parse_group_name(self, response):
        path = self._path(response.url)
        if path in self.group_name_overrides:
            return self.group_name_overrides[path]
        name = self._clean_text(" ".join(response.xpath("//main//h1//text()").getall()))
        if not name:
            name = path.split("/")[-2].replace("-", " ").title() + " Planning Group"
            self.logger.warning(f"Group heading (h1) not found on {response.url}")
        return name

    def _group_title(self, group, meeting_title):
        """Group name, plus the meeting type unless it's a regular meeting."""
        if meeting_title == "Regular Meeting":
            return group
        return f"{group} - {meeting_title}"

    def _parse_meeting_info(self, response):
        """
        Regular meeting time and location from the page's "Meeting Info" box.
        Pages only show the current values, so they apply to all meetings.
        """
        box = response.xpath(
            "//h2[normalize-space()='Meeting Info']/following-sibling::div"
        )
        time_lines = self._info_lines(box, "icon-clock")
        location_lines = self._info_lines(box, "icon-map-marker")

        meeting_time = self._parse_info_time(" ".join(time_lines))
        if meeting_time is None:
            # Logged per page; reported on close only if no page had it
            self._groups_without_meeting_info += 1
            self.logger.warning(
                f"Could not read the meeting time from 'Meeting Info' "
                f"({' '.join(time_lines)!r}) on {response.url}; using midnight"
            )
            meeting_time = time(0, 0)
        if not location_lines:
            self.logger.warning(
                f"Could not read the meeting location from 'Meeting Info' on "
                f"{response.url}"
            )

        # "Virtual Meetings – See Agenda for Link", "Check the agenda for the
        # meeting location": the location is only on each agenda, so keep the
        # note as the description and leave the location TBD.
        notes = [
            line
            for line in time_lines + location_lines
            if _LOCATION_NOTE_RE.search(line)
        ]
        if notes:
            return meeting_time, {"name": "TBD", "address": ""}, " ".join(notes)
        return meeting_time, self._parse_info_location(location_lines), ""

    def _info_lines(self, box, icon):
        """Text lines of a "Meeting Info" cell, as written on the page."""
        cell = box.xpath(
            f".//i[contains(@class, '{icon}')]"
            "/ancestor::div[1]/following-sibling::div[1]"
        ).get("")
        text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", cell, flags=re.IGNORECASE)
        text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
        lines = (re.sub(r"\s+", " ", line).strip(" ,.") for line in text.split("\n"))
        return [line for line in lines if line]

    def _parse_info_time(self, text):
        match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\b", text, re.I)
        if not match:
            return None
        hour = int(match.group(1)) % 12
        if match.group(3).lower() == "p":
            hour += 12
        return time(hour, int(match.group(2) or 0))

    def _parse_info_location(self, lines):
        """
        ["Mira Mesa Branch Library", "8405 New Salem St", "San Diego, CA 92126"]
        -> name + address.
        """
        if not lines:
            return {"name": "TBD", "address": ""}
        address_start = next(
            (i for i, line in enumerate(lines) if re.match(r"\d", line)), None
        )
        if address_start is None:
            return {"name": " ".join(lines), "address": ""}
        return {
            "name": " ".join(lines[:address_start]),
            "address": ", ".join(lines[address_start:]),
        }

    # ------------------------------------------------------------------ #
    # Error reporting
    # ------------------------------------------------------------------ #

    def _add_problem(self, problem):
        self.logger.warning(problem)
        self._problems.append(problem)

    def _on_spider_closed(self, spider, reason):
        """
        Report one error per run for major breakages only: failed requests, a
        missing community list, no meetings, or a site-wide
        "Meeting Info" change. Problems with single entries or pages are logged.
        """
        problems = list(self._problems)
        if reason == "finished":
            if self._meetings_parsed == 0:
                problems.append("0 meetings parsed")
            if (
                self._groups_parsed
                and self._groups_without_meeting_info == self._groups_parsed
            ):
                problems.append(
                    "'Meeting Info' time unreadable on every group page; all "
                    "meetings were published at midnight"
                )
        if not problems:
            return
        self._report_error(
            SandiePlanningGroupsError(
                f"{self.name}: {'; '.join(problems)} "
                f"(finish_reason={reason}, failed_requests={self._failed_requests}, "
                f"groups={self._groups_parsed}, meetings={self._meetings_parsed})"
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

    # ------------------------------------------------------------------ #
    # Entry parsing
    # ------------------------------------------------------------------ #

    def _lookback_cutoff(self):
        now = datetime.now(self.tz).replace(tzinfo=None)
        return (now - relativedelta(years=self.lookback_years)).date()

    def _parse_entries(self, tab, doc_type, response):
        entries = []
        cutoff = self._lookback_cutoff()
        for li in tab.xpath(".//li"):
            year_hint = self._accordion_year(li)
            if year_hint and year_hint < cutoff.year:
                # Whole year section older than the lookback
                continue
            anchors = li.xpath("./a | ./*[not(self::ul or self::ol)]//a")
            href = anchors.xpath("@href").get() if anchors else None
            text = self._node_text(anchors[0]) if anchors else ""
            # Prefer the link text; fall back to the whole item when the date
            # is split around the link ("J<a>anuary 6, 2026</a>")
            if not (text and self._parse_entry_text(text, year_hint)):
                text = self._node_text(li, exclude_lists=True)
            entry = self._parse_entry_text(text, year_hint) if text else None
            if entry is None:
                # "None posted", "June 2026 - Meeting Adjourned", "Press
                # Release": not meetings with a readable date
                self.logger.debug(f"Skipping {doc_type} entry without a date: {text!r}")
                continue
            entry["dates"] = [d for d in entry["dates"] if d >= cutoff]
            if not entry["dates"]:
                continue
            filename = (href or "").rsplit("/", 1)[-1].lower()
            entry.update(
                {
                    # Minutes are occasionally posted under the Agendas tab
                    "doc_type": "Minutes" if "minute" in filename else doc_type,
                    "href": response.urljoin(href) if href else None,
                    "raw": text,
                }
            )
            title_text = entry.pop("title_text")
            # Translations only duplicate the English entry's title
            entry["title"] = (
                "Regular Meeting" if entry["spanish"] else self._parse_title(title_text)
            )
            entries.append(entry)
        return entries

    def _parse_entry_text(self, text, year_hint):
        """
        Returns {"dates": [...], "title_text": str, "spanish": bool} or None
        when no full date can be read from the text.
        """
        normalized = self._clean_text(text)

        match = _RANGE_RE.search(normalized)
        if match:
            month = self._month_number(match.group("month"))
            year = self._resolve_year(match.group("year"), month, year_hint)
            if year:
                days = [int(match.group("day1")), int(match.group("day2"))]
                dates = [self._safe_date(year, month, d) for d in days]
                if all(dates):
                    return {
                        "dates": dates,
                        "title_text": self._remove_span(normalized, match),
                        "spanish": False,
                    }

        match = _SINGLE_RE.search(normalized)
        if match:
            month = self._month_number(match.group("month"))
            year = self._resolve_year(match.group("year"), month, year_hint)
            date = self._safe_date(year, month, int(match.group("day")))
            if date:
                return {
                    "dates": [date],
                    "title_text": self._remove_span(normalized, match),
                    "spanish": False,
                }

        match = _SPANISH_RE.search(normalized)
        if match:
            date = self._safe_date(
                int(match.group("year")),
                _SPANISH_MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
            if date:
                return {
                    "dates": [date],
                    "title_text": self._remove_span(normalized, match),
                    "spanish": True,
                }
        return None

    def _resolve_year(self, explicit_year, month, year_hint):
        if explicit_year:
            year = int(explicit_year)
            # Common new-year typo: "January 6, 2025" listed under the 2026
            # heading (the linked PDFs confirm 2026).
            if year_hint and month == 1 and year == year_hint - 1:
                self.logger.info(
                    "Using year heading %s instead of %s for a January entry",
                    year_hint,
                    year,
                )
                return year_hint
            return year
        return year_hint

    def _safe_date(self, year, month, day):
        if not (year and month and day):
            return None
        try:
            return datetime(year, month, day).date()
        except ValueError:
            self.logger.warning(f"Invalid date: {year}-{month}-{day}")
            return None

    def _month_number(self, month):
        month = month.lower().rstrip(".")
        return _MONTHS.get(_MONTH_ALIASES.get(month, month))

    def _remove_span(self, text, match):
        return (text[: match.start()] + " " + text[match.end() :]).strip()

    def _accordion_year(self, li):
        heading = li.xpath(
            "ancestor::div[contains(@class, 'accordion__drawer')][1]"
            "/preceding-sibling::*[contains(@class, 'accordion__heading')][1]"
            "//text()"
        ).getall()
        match = re.search(r"\b((?:19|20)\d{2})\b", " ".join(heading))
        return int(match.group(1)) if match else None

    def _node_text(self, node, exclude_lists=False):
        if exclude_lists:
            texts = node.xpath(
                "./text() | ./*[not(self::ul or self::ol)]/descendant-or-self::text()"
            ).getall()
        else:
            texts = node.xpath(".//text()").getall()
        # Join without separators so split words ("A<a>ugust") are rejoined
        return self._clean_text("".join(texts))

    def _clean_text(self, text):
        for dash in ("\u2013", "\u2014"):
            text = text.replace(dash, "-")
        text = text.replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    # ------------------------------------------------------------------ #
    # Grouping entries into meetings
    # ------------------------------------------------------------------ #

    def _group_entries(self, entries, meeting_time):
        """
        Merge agenda, minutes and translated documents of the same meeting.

        English agendas define the meetings, keyed by (date, title). Every other
        document (minutes, translations) on a date is attached to that date's
        meeting with, in order:

        1. the same title (ignoring case and punctuation);
        2. the most similar title ("Traffic and Transportation Board" and
           "Traffic & Transportation Board", "Elections" and "Annual Elections
           Meeting");
        3. the only meeting that day, unless both are differently named
           committees (e.g. Communications minutes on a day with only a Urban
           Design agenda).

        Anything left becomes its own meeting (e.g. minutes posted without an
        agenda).
        """
        meetings = OrderedDict()

        def key(date, title):
            # Same normalization as the meeting ID
            return (date, re.sub(r"[^a-z0-9]+", "", title.lower()))

        def add_doc(record, entry):
            link_title = entry["doc_type"]
            if entry["spanish"]:
                link_title += " (Spanish)"
            if entry["href"] and entry["href"] not in {
                link["href"] for link in record["links"]
            }:
                record["links"].append({"title": link_title, "href": entry["href"]})
            record["status_text"].append(entry["raw"])
            if entry["href"]:
                record["status_text"].append(entry["href"].rsplit("/", 1)[-1])

        def new_record(date, title):
            record = {
                "start": datetime.combine(date, meeting_time),
                "title": title,
                "links": [],
                "status_text": [],
            }
            meetings[key(date, title)] = record
            return record

        # Agendas (English) first so they define the meetings
        ordered = sorted(
            entries,
            key=lambda e: (e["doc_type"] != "Agenda", e["spanish"]),
        )
        for entry in ordered:
            for date in entry["dates"]:
                record = meetings.get(key(date, entry["title"]))
                if record is None and (
                    entry["spanish"] or entry["doc_type"] != "Agenda"
                ):
                    candidates = [r for (d, _), r in meetings.items() if d == date]
                    record = self._match_document(entry, candidates)
                if record is None:
                    record = new_record(date, entry["title"])
                add_doc(record, entry)

        return sorted(meetings.values(), key=lambda r: r["start"], reverse=True)

    def _match_document(self, entry, candidates):
        """The meeting a minutes/translation entry belongs to, or None."""
        if not candidates:
            return None

        def title_score(record):
            if "Regular Meeting" in (entry["title"], record["title"]):
                return 0.0
            return self._title_similarity(entry["title"], record["title"])

        best = max(candidates, key=title_score)
        if title_score(best) >= _MATCH_THRESHOLD:
            return best

        if len(candidates) == 1:
            only = candidates[0]
            named = [
                t
                for t in (entry["title"], only["title"])
                if t != "Regular Meeting" and self._title_words(t)
            ]
            if len(named) == 2 and title_score(only) == 0:
                # Two differently named committees met that day
                return None
            return only

        generic = [r for r in candidates if r["title"] == "Regular Meeting"]
        if entry["title"] == "Regular Meeting" and len(generic) == 1:
            return generic[0]
        return None

    def _title_words(self, title):
        words = re.findall(r"[a-z]+", title.lower().replace("&", " and "))
        words = (re.sub(r"s$", "", word) for word in words)
        return {word for word in words if word not in _TITLE_STOP_WORDS}

    def _title_similarity(self, title, other):
        """1 if one title's words contain the other's, else the share in common."""
        words, other_words = self._title_words(title), self._title_words(other)
        if not words or not other_words:
            return 0.0
        if words <= other_words or other_words <= words:
            return 1.0
        return len(words & other_words) / len(words | other_words)

    # ------------------------------------------------------------------ #
    # Meeting fields
    # ------------------------------------------------------------------ #

    def _get_status(self, meeting, text=""):
        if _CANCELLED_RE.search(text):
            return CANCELLED
        return super()._get_status(meeting, text)

    def _parse_classification(self, meeting_title, group):
        """
        A committee if the meeting (e.g. "Project Review Subcommittee") or the
        group itself (the Community Planners Committee) is one.
        """
        if _COMMITTEE_RE.search(meeting_title) or _COMMITTEE_RE.search(group):
            return COMMITTEE
        return BOARD

    def _parse_title(self, text):
        """
        `text` is the entry text with the date already removed. Strip status and
        document words, then fall back to "Regular Meeting".
        """
        title = text
        # Leftover Spanish dates and month-only dates
        title = _SPANISH_RE.sub(" ", title)
        title = re.sub(
            r"\(?\s*\d{1,2}\s+de\s+[a-záéíóúñ]+\s+(?:de|del)\s+\d{4}\s*\)?",
            " ",
            title,
            flags=re.IGNORECASE,
        )
        title = _MONTH_ONLY_RE.sub(" ", title)
        title = _STATUS_NOISE_RE.sub(" ", title)
        title = _DOC_NOISE_RE.sub(" ", title)
        title = re.sub(r"\(\s*\)|\[\s*\]", " ", title)
        title = re.sub(r"\s+", " ", title)
        # Leading/trailing punctuation left behind by removed words
        title = re.sub(r"^[\s\-,:;/|&.]+|[\s\-,:;/|&]+$", "", title)
        title = re.sub(r"^\((.*)\)$", r"\1", title).strip()
        title = re.sub(r"^[\s\-,:;/|&.*]+|[\s\-,:;/|&*]+$", "", title)

        if (
            not title
            or _GENERIC_TITLE_RE.fullmatch(title)
            or _MAIN_BOARD_ALIAS_RE.fullmatch(title)
        ):
            return "Regular Meeting"
        if re.fullmatch(r"special(?:\s+meeting)?", title, re.IGNORECASE):
            return "Special Meeting"
        return title
