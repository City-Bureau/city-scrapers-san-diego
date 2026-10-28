"""
A Mixin & Mixin Meta for City of Carlsbad, California scrapers.

Meetings come from the city calendar (one page per month, all departments).
Attachments come from two places:

- the board's page under /city-hall/meetings-agendas, which has a document
  folder per recent or upcoming meeting (folders can hold subfolders, so they
  are walked recursively)
- the city's Laserfiche records portal. Its "Meeting Packets" section has a
  folder per meeting with every document (agenda, staff reports, minutes,
  resolutions); the board's "Past materials" folder (agendas only) is used for
  meetings that have no packet folder.

Meeting videos come from the city's Swagit archive (linked from its Public
Meeting Archive page), which has a recording of almost every meeting.

www.carlsbadca.gov is behind Akamai, which rejects Scrapy's TLS fingerprint,
so its pages are fetched with curl-cffi (as in sandie_citychula). Akamai also
answers event detail pages with a JavaScript challenge that curl-cffi can't
run, so the spider reads everything it needs from the calendar grid and the
document folders instead. The Laserfiche portal isn't behind Akamai.

Required class variables (enforced by metaclass):
    name (str): Spider name/slug (e.g., "sandie_carlsbad_council_committees")
    agency (str): Full agency name (e.g., "City of Carlsbad- City Council Committees")
    boards (list): One dict per board this spider covers, with:
        title: board name, used in logs
        keywords: lowercase phrases; a calendar title matching any is this board
        exclude: (optional) phrases that rule a calendar title out
        classification: classification constant for the board's meetings
        page: board page path under /city-hall/meetings-agendas ("" for the
              City Council page itself)
        laserfiche_packets_id: the board's folder under Meeting Packets
        laserfiche_agendas_id: the board's "Past materials" (Agendas) folder
        swagit_tab: the Swagit archive tab that has the board's videos
"""

import random
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from curl_cffi import requests as curl_requests
from scrapy.http import HtmlResponse

# curl-cffi impersonation target, as in sandie_citychula and sandie_nationalcity
IMPERSONATE = "chrome131"
REQUEST_TIMEOUT = 30


class SandieCarlsbadMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from the "Mixin" class.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "boards"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class SandieCarlsbadMixin(CityScrapersSpider, metaclass=SandieCarlsbadMixinMeta):
    """Mixin for City of Carlsbad spiders: city calendar plus attachments."""

    name = None
    agency = None
    boards = None
    timezone = "America/Los_Angeles"
    tzinfo = ZoneInfo(timezone)

    base_url = "https://www.carlsbadca.gov"
    # This returns events for "All Departments"; each board's keywords pick its
    # meetings
    calendar_url = base_url + "/departments/calendar/-curm-{month}/-cury-{year}/"
    agendas_url = base_url + "/city-hall/meetings-agendas"
    laserfiche_listing_url = "https://records.carlsbadca.gov/WebLink/FolderListingService.aspx/GetFolderListing2"  # noqa
    laserfiche_file_url = "https://records.carlsbadca.gov/WebLink/ElectronicFile.aspx?docid={id}&dbid=0&repo=CityOfCarlsbad"  # noqa
    laserfiche_page_size = 200
    # Each tab lists its videos newest first, 10 to a page
    swagit_url = "https://carlsbadca.new.swagit.com/views/295/{tab}?page={page}"
    swagit_video_url = "https://carlsbadca.new.swagit.com/videos/{id}"

    # Scraped period: meetings from this many years ago (as in the City of
    # Encinitas factory), through every month the calendar has up to
    # months_ahead from now.
    lookback_years = 2
    months_ahead = 12

    # Seconds between requests to the Akamai-protected site (plus up to 1s of
    # jitter); bursts of requests get rejected.
    request_delay = 5
    # Akamai intermittently rejects single requests; retry those with backoff.
    akamai_retries = 3
    akamai_retry_backoff = 20
    # Document folders nest at most a level or two; this only stops a loop.
    max_folder_depth = 4
    # A subcommittee ("Arts Commission Subcommittee Meeting") isn't the board
    # itself, so these never match any board; a spider config can add more
    exclude_keywords = ["subcommittee"]
    # For a calendar listing without a time (and no folder that gives one)
    no_time_notes = "Please check the meeting attachment for start time details."

    location = {
        "name": "City Council Chamber",
        "address": "1200 Carlsbad Village Drive, Carlsbad, CA 92008",
    }

    custom_settings = {
        # Pages are fetched with curl-cffi, not Scrapy; the only Scrapy
        # request is the data: URL that starts the crawl.
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    # "Oct. 20, 2026, 5 p.m. City Council Chamber - Regular Meeting"
    _FOLDER_RE = re.compile(
        r"^(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4}),?\s*"
        r"(?:(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>[ap])\.?m\.?)?",
        re.IGNORECASE,
    )
    # Calendar title suffixes that are a room or a status, not part of the name
    _LOCATION_SUFFIX_RE = re.compile(r"\s*-\s*(?:City\s+)?Council Chamber\b", re.I)
    _STATUS_SUFFIX_RE = re.compile(
        r"\s*-?\s*\b(?:CANCELL?ED|ADJOURNED|POSTPONED|RESCHEDULED)\b", re.I
    )
    _CLOSED_RE = re.compile(r"closed\s+(?:to\s+(?:the\s+)?public|session)", re.I)
    # Laserfiche entry names start with the meeting date: "2026-10-06; City
    # Council; Agendas; Regular Session" (one has a colon: "2026-01-13: ...")
    _LASERFICHE_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*[;:]\s*")
    # "01" or "CS01": a numbered agenda item in a Laserfiche entry name
    _ITEM_NUMBER_RE = re.compile(r"[A-Z]*\d+")
    _CLOSED_SESSION_RE = re.compile(r"closed session", re.I)
    _SPECIAL_RE = re.compile(r"\bspecial\b", re.I)
    _CANCEL_RE = re.compile(r"cancel", re.I)
    _SWAGIT_VIDEO_RE = re.compile(r"/videos/(\d+)$")
    # aria-label "Scheduled events, Thursday, October 1, 2026"
    _DAY_LABEL_RE = re.compile(r"([A-Za-z]+ \d{1,2}, \d{4})\s*$")
    _EVENT_TIME_RE = re.compile(r"\s*(\d{1,2}:\d{2})\s*([AP]M)", re.I)
    _SPACES_RE = re.compile(r"\s+")
    _TRAILING_DASH_RE = re.compile(r"[\s-]+$")
    _SPACES_DASHES_RE = re.compile(r"[\s-]+")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_akamai_request = None
        # (board title, date) -> list of (folder title, start or None, links)
        self._folder_links = defaultdict(list)
        # (board title, date) -> list of (session text, link)
        self._laserfiche_links = defaultdict(list)
        # (board title, date) -> list of (Swagit video title, link)
        self._videos = defaultdict(list)

    # DATES

    def _start_cutoff(self):
        """Earliest meeting start to scrape: today in Carlsbad minus
        lookback_years (it's compared with meeting starts, which are local).
        Feb. 29 moves to Feb. 28 in a year that has none."""
        today = datetime.now(self.tzinfo).replace(
            tzinfo=None, hour=0, minute=0, second=0, microsecond=0
        )
        day = 28 if (today.month, today.day) == (2, 29) else today.day
        return today.replace(year=today.year - self.lookback_years, day=day)

    def _calendar_months(self):
        """(year, month) pairs from the cutoff month to months_ahead from now."""
        start, now = self._start_cutoff(), datetime.now(self.tzinfo)
        year, month = start.year, start.month
        last_index = now.year * 12 + now.month - 1 + self.months_ahead
        while year * 12 + month - 1 <= last_index:
            yield year, month
            year, month = (year, month + 1) if month < 12 else (year + 1, 1)

    # REQUESTS

    def start_requests(self):
        """
        Kick off the spider without touching the protected site.

        The real pages are fetched inside _run_crawl() using curl-cffi; a
        data: URL avoids a Scrapy-fingerprinted request that Akamai would 403.
        """
        yield scrapy.Request(
            "data:,",
            callback=self._run_crawl,
            errback=self._handle_error,
            dont_filter=True,
        )

    def _handle_error(self, failure):
        """Log a request that failed, so a broken run doesn't look clean."""
        self.logger.warning("Request failed: %s", failure.getErrorMessage())

    def _run_crawl(self, response):
        """Read the calendar, then attach each meeting's documents."""
        cutoff = self._start_cutoff()
        meetings = {}
        for year, month in self._calendar_months():
            url = self.calendar_url.format(month=month, year=year)
            page = self._akamai_get(url)
            if page is None:
                self.logger.warning("Could not fetch calendar month: %s", url)
                continue
            for meeting in self.parse(page):
                if meeting["start"] >= cutoff:
                    self._keep_current(meetings, meeting)

        self._load_attachments(meetings.values())
        finished = [
            self._finish(meeting)
            for meeting in sorted(meetings.values(), key=lambda m: m["start"])
        ]
        self._add_videos(finished)
        yield from finished

    def _keep_current(self, meetings, meeting):
        """Add a meeting, keeping the active copy when an id repeats (the
        calendar sometimes keeps a cancelled listing beside its re-post)."""
        existing = meetings.get(meeting["id"])
        if existing is None or (
            existing["status"] == CANCELLED and meeting["status"] != CANCELLED
        ):
            meetings[meeting["id"]] = meeting

    def _akamai_get(self, url, referer=None):
        """GET a www.carlsbadca.gov page with curl-cffi Chrome impersonation.

        Akamai intermittently answers with a 403 or its JavaScript challenge
        page (bm-verify); those are retried with an increasing backoff. Returns
        a Scrapy HtmlResponse, or None if every attempt failed. Blocks the
        Twisted reactor; callers run sequentially.
        """
        for attempt in range(1, self.akamai_retries + 1):
            # Keep at least request_delay (+ jitter) seconds between requests
            if self._last_akamai_request is not None:
                elapsed = time.monotonic() - self._last_akamai_request
                time.sleep(max(0, self.request_delay + random.random() - elapsed))
            self._last_akamai_request = time.monotonic()
            try:
                response = curl_requests.get(
                    url,
                    impersonate=IMPERSONATE,
                    timeout=REQUEST_TIMEOUT,
                    headers={"Referer": referer or self.base_url + "/"},
                )
            except curl_requests.RequestsError as e:
                self.logger.warning("Request failed for %s: %s", url, e)
                return None

            challenge = b"bm-verify" in response.content
            if response.status_code == 200 and not challenge:
                return HtmlResponse(url=url, body=response.content, encoding="utf-8")

            self.logger.warning(
                "Got %s for %s (attempt %s/%s)",
                "an Akamai challenge page" if challenge else response.status_code,
                url,
                attempt,
                self.akamai_retries,
            )
            if response.status_code != 403 and not challenge:
                return None
            if attempt < self.akamai_retries:
                time.sleep(self.akamai_retry_backoff * attempt)
        return None

    def _user_agent_headers(self):
        """The project's User-Agent for the sites that aren't behind Akamai."""
        user_agent = getattr(self, "settings", None) and self.settings.get("USER_AGENT")
        return {"User-Agent": user_agent} if user_agent else None

    def _swagit_get(self, url):
        """GET a Swagit archive page as an HtmlResponse, or None if it failed."""
        try:
            response = curl_requests.get(
                url, headers=self._user_agent_headers(), timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
        except curl_requests.RequestsError as e:
            self.logger.warning("Swagit page %s failed: %s", url, e)
            return None
        return HtmlResponse(url=url, body=response.content, encoding="utf-8")

    def _laserfiche_entries(self, folder_id):
        """Every entry in a Laserfiche folder, or None if it can't be listed."""
        entries, start = [], 0
        while True:
            try:
                response = curl_requests.post(
                    self.laserfiche_listing_url,
                    json={
                        "repoName": "CityOfCarlsbad",
                        "folderId": int(folder_id),
                        "getNewListing": True,
                        "start": start,
                        "end": start + self.laserfiche_page_size,
                        "sortColumn": "",
                        "sortAscending": True,
                    },
                    headers=self._user_agent_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                data = response.json()["data"]
            except (curl_requests.RequestsError, ValueError, KeyError) as e:
                self.logger.warning("Laserfiche folder %s failed: %s", folder_id, e)
                return None
            if not data or data.get("failed"):
                self.logger.warning(
                    "Laserfiche folder %s failed: %s",
                    folder_id,
                    (data or {}).get("errMsg"),
                )
                return None
            results = data.get("results") or []
            entries.extend(results)
            start += len(results)
            if not results or start >= (data.get("totalEntries") or 0):
                return entries

    # ATTACHMENTS

    def _load_attachments(self, meetings):
        """Index the documents of every board with a meeting in this run."""
        needed = defaultdict(set)
        for meeting in meetings:
            board = self._match_board(meeting["title"])
            if board:
                needed[board["title"]].add(meeting["start"].date())

        for board in self.boards:
            dates = needed.get(board["title"])
            if not dates:
                continue
            self._load_board_folders(board, dates)
            self._load_laserfiche(board, board["laserfiche_packets_id"], dates)
            # The Agendas folder only for meetings without a packet folder
            missing = {
                d for d in dates if (board["title"], d) not in self._laserfiche_links
            }
            if missing:
                self._load_laserfiche(board, board["laserfiche_agendas_id"], missing)
        self._load_videos(needed)

    def _load_videos(self, needed):
        """Index the Swagit videos of the boards and dates in this run. Tabs
        list videos newest first, so paging stops once a page reaches the
        run's earliest date."""
        tabs = sorted({b["swagit_tab"] for b in self.boards if needed.get(b["title"])})
        earliest = min((d for dates in needed.values() for d in dates), default=None)
        for tab in tabs:
            page = 1
            while True:
                url = self.swagit_url.format(tab=tab, page=page)
                response = self._swagit_get(url)
                if response is None:
                    break
                rows = response.css("#video-table tbody tr")
                if not rows:
                    self.logger.warning("No videos found on %s", url)
                    break
                oldest = None
                for row in rows:
                    video = self._parse_video_row(row, url)
                    if video is None:
                        continue
                    title, oldest, link = video
                    board = self._match_board(title)
                    if board and oldest in needed.get(board["title"], ()):
                        self._videos[(board["title"], oldest)].append((title, link))
                if not response.css(".pagination li.next a") or (
                    oldest and oldest < earliest
                ):
                    break
                page += 1

    def _parse_video_row(self, row, url):
        """(title, date, link) from a Swagit row, or None if it can't be read."""
        link = row.css("td a[href*='/videos/']")
        match = self._SWAGIT_VIDEO_RE.search(link.attrib.get("href", ""))
        title = self._SPACES_RE.sub(" ", " ".join(link.css("::text").getall()))
        date_text = self._SPACES_RE.sub(
            " ", " ".join(row.css("td:nth-child(2) ::text").getall())
        ).strip()
        try:
            video_date = datetime.strptime(date_text, "%b %d, %Y").date()
        except ValueError as e:
            self.logger.warning("Unparseable video date on %s: %s", url, e)
            return None
        if not match or not title.strip():
            self.logger.warning("Skipping video row without a link on %s", url)
            return None
        href = self.swagit_video_url.format(id=match.group(1))
        return title.strip(), video_date, {"href": href, "title": "Meeting Video"}

    def _load_board_folders(self, board, dates):
        """Index the documents in the board page's meeting folders."""
        page_url = (
            f"{self.agendas_url}/{board['page']}" if board["page"] else self.agendas_url
        )
        page = self._akamai_get(page_url)
        if page is None:
            self.logger.warning("Could not fetch board page: %s", page_url)
            return
        for title, href in self._parse_folders(page):
            folder_date, folder_start = self._parse_folder_title(title)
            if folder_date is None:
                self.logger.warning(
                    "Skipping folder with no parseable date on %s: %r", page_url, title
                )
                continue
            if folder_date not in dates:
                continue
            links = self._folder_documents(urljoin(page_url, href), page_url, 1)
            self._folder_links[(board["title"], folder_date)].append(
                (title, folder_start, links)
            )

    def _folder_documents(self, url, referer, depth):
        """Documents in a folder and, recursively, in its subfolders."""
        page = self._akamai_get(url, referer=referer)
        if page is None:
            self.logger.warning("Could not fetch document folder: %s", url)
            return []
        links = []
        for link in page.css(".document_widget li a[href]"):
            href = link.attrib["href"].strip()
            if "/showpublisheddocument/" not in href.lower():
                continue
            title = self._SPACES_RE.sub(" ", " ".join(link.css("::text").getall()))
            title = title.strip()
            links.append(
                {"href": urljoin(self.base_url, href), "title": title or "Document"}
            )
        if depth >= self.max_folder_depth:
            return links
        for _, href in self._parse_folders(page):
            links.extend(self._folder_documents(urljoin(url, href), url, depth + 1))
        return links

    def _parse_folders(self, response):
        """(title, href) for each subfolder in a page's document widget."""
        folders = []
        for link in response.css(".document_widget .doc_folder_img + a"):
            title = " ".join(link.css("::text").getall()).strip()
            href = link.attrib.get("href", "").strip()
            if title and href:
                folders.append((title, href.split("#")[0]))
        return folders

    def _parse_folder_title(self, title):
        """
        (date, start) from a folder title like "Oct. 20, 2026, 5 p.m. City
        Council Chamber - Regular Meeting". start is None without a time.
        A typo in the year's century ("Sept. 21, 2626" on the live Parks &
        Recreation page) is corrected to the current century, with a warning.
        """
        match = self._FOLDER_RE.match(title.strip())
        if not match:
            return None, None
        typed = int(match.group("year"))
        year = datetime.now(self.tzinfo).year // 100 * 100 + typed % 100
        if year != typed:
            self.logger.warning("Corrected year %s -> %s in %r", typed, year, title)
        # "Sept." and "March" both become "Sep"/"Mar" for %b
        date_text = f"{match.group('month')[:3]} {match.group('day')} {year}"
        try:
            folder_date = datetime.strptime(date_text, "%b %d %Y").date()
        except ValueError as e:
            self.logger.warning("Unparseable folder date %r: %s", title, e)
            return None, None
        if not match.group("hour"):
            return folder_date, None
        minute = match.group("minute") or "00"
        clock = f"{match.group('hour')}:{minute} {match.group('ampm').upper()}M"
        return folder_date, datetime.strptime(
            f"{date_text} {clock}", "%b %d %Y %I:%M %p"
        )

    def _load_laserfiche(self, board, folder_id, dates):
        """
        Index Laserfiche documents for dates under a board's folder. Year
        folders are walked only for the years needed, and a meeting's own
        folder ("2026-10-06; City Council; Regular Session", in Meeting
        Packets) only for a needed date.
        """
        years = {str(d.year) for d in dates}
        # (folder id, depth, session text of the meeting folder it's in)
        pending = [(folder_id, 0, "")]
        while pending:
            current_id, depth, session = pending.pop()
            entries = self._laserfiche_entries(current_id)
            if entries is None:
                continue
            for entry in entries:
                name = (entry.get("name") or "").strip()
                entry_date = self._parse_laserfiche_date(name)
                if entry.get("type") == 0:
                    if depth < self.max_folder_depth and (
                        name in years or entry_date in dates
                    ):
                        # A year folder keeps its parent's session text; a
                        # meeting folder's name is the session text
                        pending.append(
                            (
                                entry["entryId"],
                                depth + 1,
                                name if entry_date else session,
                            )
                        )
                    continue
                if not entry.get("isEdoc") or entry_date not in dates:
                    continue
                self._laserfiche_links[(board["title"], entry_date)].append(
                    (
                        session or name,
                        {
                            "href": self.laserfiche_file_url.format(
                                id=entry["entryId"]
                            ),
                            "title": self._laserfiche_title(name),
                        },
                    )
                )

    def _parse_laserfiche_date(self, name):
        """Date from an entry name like "2026-10-06; City Council; Agendas"."""
        match = self._LASERFICHE_DATE_RE.match(name)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group(1))
        except ValueError as e:
            self.logger.warning("Unparseable Laserfiche date %r: %s", name, e)
            return None

    def _laserfiche_title(self, name):
        """
        Link title from an entry name, without its date and board:
        "...; City Council; Agendas; Regular Session" -> "Agenda - Regular
        Session", "...; City Council; 01; Acceptance of Donation" -> "Item 01 -
        Acceptance of Donation", "...; City Council; Resolution 2026-194" ->
        "Resolution 2026-194".
        """
        name = self._SPACES_RE.sub(" ", self._LASERFICHE_DATE_RE.sub("", name))
        parts = [p.strip() for p in name.split(";")]
        parts = [p for p in parts[1:] if p]
        if not parts:
            return "Document"
        if parts[0] == "Agendas":
            parts[0] = "Agenda"
        elif self._ITEM_NUMBER_RE.fullmatch(parts[0]):
            parts[0] = f"Item {parts[0]}"
        return " - ".join(parts)

    def _links_for(self, board_title, meeting):
        """
        Documents for a meeting, and the title of its board-page folder.

        The board-page folder is used when there is one (it has documents
        Laserfiche doesn't, like correspondence and action agendas), plus any
        Laserfiche minutes it doesn't have; otherwise every Laserfiche
        document for the meeting. When a board has several meetings on one
        date (e.g. a closed session before a regular meeting, or a cancelled
        regular meeting and a special one), the folder with the same start
        time, or the Laserfiche documents of the same session type, are used.
        """
        key = (board_title, meeting["start"].date())
        laserfiche = self._laserfiche_links.get(key, [])
        if not meeting["closed_to_public"]:
            # A closed session's documents never belong to an open meeting
            laserfiche = [
                (session, link)
                for session, link in laserfiche
                if not self._CLOSED_SESSION_RE.search(session)
            ]
        # Narrow to sessions that are closed, special and cancelled like this
        # meeting; a filter that would leave nothing is skipped
        for pattern, wanted in [
            (self._CLOSED_SESSION_RE, meeting["closed_to_public"]),
            (self._SPECIAL_RE, bool(self._SPECIAL_RE.search(meeting["title"]))),
            (self._CANCEL_RE, meeting["status"] == CANCELLED),
        ]:
            laserfiche = [
                (session, link)
                for session, link in laserfiche
                if bool(pattern.search(session)) == wanted
            ] or laserfiche
        laserfiche = [link for _, link in laserfiche]

        folders = self._folder_links.get(key, [])
        # A meeting listed without a time matches its date's only folder
        timed = [f for f in folders if f[1] == meeting["start"]]
        chosen = timed or (folders if len(folders) == 1 else [])
        if not chosen:
            return laserfiche, ""
        folder_title, _, links = chosen[0]
        if not any("minutes" in link["title"].lower() for link in links):
            links = links + [
                link for link in laserfiche if link["title"].startswith("Minutes")
            ]
        return links, folder_title

    # PARSING

    def parse(self, response):
        """
        Parse one month of the city calendar and yield this spider's meetings.

        Links aren't known yet: _run_crawl() adds them after every month has
        been read, so the documents are only fetched for meetings in the run.
        """
        # Weekdays are td.calendar_day, but today is td.calendar_today,
        # weekends td.calendar_weekendday and days of the months on either
        # side td.calendar_othermonthday
        days = response.css(
            "td.calendar_day, td.calendar_today, td.calendar_weekendday, "
            "td.calendar_othermonthday"
        )
        if not days:
            self.logger.warning("No calendar days found on %s", response.url)
            return

        meetings = {}
        for day in days:
            events = day.css("a.calendar_eventlink")
            if not events:
                continue
            day_date = self._parse_day(day)
            if day_date is None:
                self.logger.warning(
                    "Skipping %s event(s) in a calendar day with no parseable "
                    "date on %s: %r",
                    len(events),
                    response.url,
                    day.attrib.get("aria-label", ""),
                )
                continue
            for event in events:
                raw_title = self._SPACES_RE.sub(
                    " ",
                    (
                        event.attrib.get("title")
                        or " ".join(event.css("::text").getall())
                    )
                    .replace("–", "-")
                    .replace("—", "-")
                    .replace("’", "'"),
                ).strip()
                title = self._parse_title(raw_title)
                board = self._match_board(title)
                if board is None:
                    continue
                time_text = (
                    event.xpath("./parent::div")
                    .css("span.calendar_eventtime::text")
                    .get("")
                )
                start = self._parse_start(day_date, time_text)
                time_notes = ""
                if start is None:
                    # Kept at 00:00 with a note rather than dropped
                    self.logger.warning(
                        "No start time for %r on %s (%r)",
                        raw_title,
                        day_date,
                        time_text,
                    )
                    start = datetime.combine(day_date, datetime.min.time())
                    time_notes = self.no_time_notes
                href = event.attrib.get("href", "").strip()
                meeting = Meeting(
                    title=title,
                    description="",
                    classification=board["classification"],
                    start=start,
                    end=None,
                    all_day=False,
                    time_notes=time_notes,
                    location=self.location,
                    links=[],
                    # The event's detail page, without the calendar's query
                    source=(
                        urljoin(self.base_url, href).split("?")[0]
                        if href
                        else response.url
                    ),
                )
                meeting["closed_to_public"] = bool(self._CLOSED_RE.search(raw_title))
                meeting["status"] = self._get_status(meeting, text=raw_title)
                meeting["id"] = self._get_id(meeting)
                self._keep_current(meetings, meeting)
        yield from meetings.values()

    def _finish(self, meeting):
        """Add documents to a meeting, and what its folder title adds (a
        cancellation or a closed session)."""
        board = self._match_board(meeting["title"])
        links, folder_title = self._links_for(board["title"], meeting)
        meeting["links"] = links
        if folder_title:
            if self._CLOSED_RE.search(folder_title):
                meeting["closed_to_public"] = True
            # The calendar's own status already counted; the folder can only
            # add a cancellation the calendar doesn't show
            if meeting["status"] != CANCELLED:
                meeting["status"] = self._get_status(meeting, text=folder_title)
        return meeting

    def _add_videos(self, meetings):
        """
        Add each meeting's Swagit video, unless it's cancelled or already has
        the recording from Laserfiche. Swagit lists videos by date only, so
        when a date has several, the one that is special (or not) like the
        meeting is used; a closed session counts as special, since Swagit
        calls its open part a special meeting. A video two meetings would
        both get is left out rather than guessed.
        """
        picks = []
        for meeting in meetings:
            if meeting["status"] == CANCELLED or any(
                "video" in link["title"].lower() for link in meeting["links"]
            ):
                continue
            board = self._match_board(meeting["title"])
            videos = self._videos.get((board["title"], meeting["start"].date()), [])
            if len(videos) > 1:
                special = meeting["closed_to_public"] or bool(
                    self._SPECIAL_RE.search(meeting["title"])
                )
                videos = [
                    v for v in videos if bool(self._SPECIAL_RE.search(v[0])) == special
                ]
            if len(videos) == 1:
                picks.append((meeting, videos[0][1]))
        counts = Counter(link["href"] for _, link in picks)
        for meeting, link in picks:
            if counts[link["href"]] == 1:
                meeting["links"] = meeting["links"] + [link]

    def _parse_day(self, day):
        """Date of a calendar cell, from an aria-label like "Scheduled events,
        Thursday, October 1, 2026"."""
        label = day.attrib.get("aria-label", "")
        match = self._DAY_LABEL_RE.search(label)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%B %d, %Y").date()
        except ValueError as e:
            self.logger.warning("Unparseable calendar date %r: %s", label, e)
            return None

    def _parse_start(self, day_date, time_text):
        """Start datetime from the cell's date and a time like "5:30 PM"."""
        match = self._EVENT_TIME_RE.match(time_text)
        if not match:
            return None
        clock = f"{match.group(1)} {match.group(2).upper()}"
        try:
            return datetime.strptime(f"{day_date} {clock}", "%Y-%m-%d %I:%M %p")
        except ValueError as e:
            self.logger.warning("Unparseable start time %r: %s", time_text, e)
            return None

    def _parse_title(self, raw_title):
        """Calendar title without its room or status suffix: "Arts Commission
        - Council Chamber" -> "Arts Commission", "City Council Meeting -
        CANCELED" -> "City Council Meeting"."""
        title = self._LOCATION_SUFFIX_RE.sub("", raw_title)
        title = self._STATUS_SUFFIX_RE.sub("", title)
        return self._TRAILING_DASH_RE.sub("", title).strip()

    def _normalize(self, text):
        text = text.lower().replace("&", " and ")
        return self._SPACES_DASHES_RE.sub(" ", text).strip()

    def _match_board(self, title):
        """The first board whose keywords match the title, if any."""
        normalized = self._normalize(title)
        if any(self._normalize(e) in normalized for e in self.exclude_keywords):
            return None
        for board in self.boards:
            if any(self._normalize(e) in normalized for e in board.get("exclude", [])):
                continue
            if any(self._normalize(k) in normalized for k in board["keywords"]):
                return board
        return None
