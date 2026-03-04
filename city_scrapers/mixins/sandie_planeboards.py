import re
from datetime import datetime, time

import scrapy
from city_scrapers_core.constants import BOARD, CANCELLED, COMMITTEE
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider


class SandiePlanboardsMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from the "Mixin" class.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "group_param", "meeting_time", "meeting_location"]  # noqa
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): "
                f"{missing_vars_str}."
            )

        super().__init__(name, bases, dct)


class SandiePlanboardsMixin(CityScrapersSpider, metaclass=SandiePlanboardsMixinMeta):
    name = None
    agency = None
    group_param = None
    meeting_time = time(0, 0)
    meeting_location = {
        "name": "",
        "address": "",
    }
    timezone = "America/Los_Angeles"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    _time_notes = "Please refer to the meeting attachments for more accurate meeting time and location."  # noqa

    main_url = "https://www.sandiego.gov/"

    def start_requests(self):
        yield scrapy.Request(
            url=f"{self.main_url}{self.group_param}",
            callback=self.parse,
        )

    def parse(self, response):
        meetings = self._parse_meetings(response)
        for record in meetings:
            meeting = Meeting(
                title=self._parse_title(record["title"]),
                description="",
                classification=self._parse_classification(record["title"]),
                start=record["date"],
                end=None,
                all_day=False,
                time_notes=self._time_notes,
                location=self.meeting_location,
                links=self._parse_links(record),
                source=response.url,
            )

            full_li_text = record.get("li_text", record["title"])
            meeting["status"] = self._get_status(meeting, full_li_text)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _get_status(self, meeting, title):
        if re.search(
            r"\b(adjournment|adjourned|date change|no meeting)\b", title, re.IGNORECASE
        ):
            return CANCELLED
        return super()._get_status(meeting, title)

    def _parse_classification(self, title):
        if re.search(r"\b(?:sub[-\s]*)?(committee|commitee)\b", title, re.IGNORECASE):
            return COMMITTEE
        return BOARD

    def _parse_links(self, record):
        links = []

        if record.get("agenda_url"):
            links.append(
                {
                    "title": "Agenda",
                    "href": record["agenda_url"],
                }
            )

        if record.get("minute_url"):
            links.append(
                {
                    "title": "Minutes",
                    "href": record["minute_url"],
                }
            )

        return links

    def _extract_date(self, title, meeting_time=time(0, 0)):
        MONTH_TYPOS = {
            "feruary": "february",
            "febuary": "february",
            "janurary": "january",
            "marchh": "march",
            "aprilr": "april",
            "sept": "september",
            "oct": "october",
            "nov": "november",
            "dec": "december",
        }

        title_normalized = title.lower()

        for typo, correct in MONTH_TYPOS.items():
            title_normalized = re.sub(rf"\b{typo}\b", correct, title_normalized)

        title_normalized = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", title_normalized)
        title_normalized = re.sub(r"(\d{1,2})\.", r"\1,", title_normalized)
        title_normalized = re.sub(r"\s*,\s*", ", ", title_normalized)

        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*\d{4}",  # noqa
            title_normalized,
            re.IGNORECASE,
        )
        if not match:
            return None

        meeting_date = datetime.strptime(match.group(), "%B %d, %Y").date()

        return datetime.combine(meeting_date, meeting_time)

    def _parse_meetings(self, response):
        agendas = []
        minutes_by_date = {}

        for agenda in response.xpath(
            "//div[@id='tab-item-1']//li[a and not(ancestor::li/ul)]/a[contains(@href, '.pdf')]"  # noqa
        ):
            link_title = re.sub(r"\s+", " ", agenda.css("::text").get("")).strip()
            li_text = re.sub(
                r"\s+",
                " ",
                " ".join(agenda.xpath("./parent::li").css("::text").getall()),
            ).strip()
            li_text = re.sub(
                r"\b([A-Z])\s+([a-z])", r"\1\2", li_text
            )  # Fix split words like "J anuary"
            dates = self._split_date_range(li_text, self.meeting_time)
            if not dates:
                single_date = self._extract_date(
                    li_text, self.meeting_time
                ) or self._extract_date(link_title, self.meeting_time)
                if single_date:
                    dates = [single_date]

            for date in dates or []:
                agendas.append(
                    {
                        "title": link_title,
                        "li_text": li_text,
                        "agenda_url": response.urljoin(agenda.attrib["href"]),
                        "date": date,
                    }
                )

        minutes_by_date = {}  # date only — for normal meetings
        minutes_by_date_title = {}  # date + title — for same-day meetings

        for minutes in response.xpath(
            "//div[@id='tab-item-2']//li[a and not(ancestor::li/ul)]/a[contains(@href, '.pdf')]"  # noqa
        ):
            title = re.sub(r"\s+", " ", minutes.css("::text").get("")).strip()
            date = self._extract_date(title, self.meeting_time)
            if date:
                minutes_by_date[date] = response.urljoin(minutes.attrib["href"])
                minutes_by_date_title[(date, title)] = response.urljoin(
                    minutes.attrib["href"]
                )

        for agenda in agendas:
            minute_url = (
                minutes_by_date_title.get((agenda["date"], agenda["li_text"]))
                or minutes_by_date_title.get((agenda["date"], agenda["title"]))
                or minutes_by_date.get(agenda["date"])
            )
            if minute_url:
                agenda["minute_url"] = minute_url

        return agendas

    def _parse_title(self, title):
        title_str = title.strip()

        title_str = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", title_str)

        title_str = re.sub(
            r"^[A-Za-z]+\s*\d{1,2}\s*[,.]\s*\d{4}\s*-?\s*",
            "",
            title_str,
        ).strip()

        bilingual_pattern = re.fullmatch(
            r"(?:/\s*)?\d{1,2}\s+de\s+[a-záéíóúñ]+\s+de\s+\d{4}",
            title_str,
            re.IGNORECASE,
        )
        regular_pattern = re.fullmatch(r"(agenda)", title_str, re.IGNORECASE)

        regular_condition = not title_str or regular_pattern

        if regular_condition or bilingual_pattern:
            return "Regular Meeting"

        cancellation_only_patterns = [
            r"^cancelled$",
            r"^Adjourned$",
            r"^no meeting$",
            r"^English and Spanish$",
            r"^video conference cover letter,?$",
            r"^meeting notice$",
            r"^meeting (cancelled|cancellation|Adjournment|adjourned)$",
            r"^meeting (cancellation|cancelation|adjournment|Postponement) notice$",
            r"^(cancelled|cancellation|postponement|adjournment) notice$",
            r"^notice of (cancellation|postponement|adjournment)$",
            r"^Notice of Meeting (cancellation|cancelation|postponement|adjournment|date change)$",  # noqa
        ]

        if any(
            re.search(p.lower(), title_str.lower()) for p in cancellation_only_patterns
        ):
            return "Regular Meeting"

        title_str = re.sub(
            r"\s*-\s*(meeting\s*)?(notice of\s*)?"
            r"(cancellation|cancelled|postponement|adjournment)"
            r"(\s*notice)?\b.*",
            "",
            title_str,
            flags=re.IGNORECASE,
        )
        title_str = re.sub(
            r"\s*-\s*cancelled.*",
            "",
            title_str,
            flags=re.IGNORECASE,
        )
        title_str = re.sub(
            r"\u2013",
            "-",
            title_str,
            flags=re.IGNORECASE,
        )
        title_str = re.sub(
            r"(?:(?<=\s)|^)_+",
            "",
            title_str,
            flags=re.IGNORECASE,
        )

        title_str = title_str.strip()

        if " - " in title_str:
            parts = [p.strip() for p in title_str.split(" - ") if p.strip()]
            if parts:
                return parts[-1]

        return title_str or "Regular Meeting"

    def _split_date_range(self, title, meeting_time):
        match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)"  # noqa
            r"\s+(\d{1,2}),?\s*[&,]\s*(\d{1,2})\s+(\d{4})",
            title,
            re.IGNORECASE,
        )
        if not match:
            return None

        month, day1, day2, year = (
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
        )
        date1 = datetime.strptime(f"{month} {day1}, {year}", "%B %d, %Y").date()
        date2 = datetime.strptime(f"{month} {day2}, {year}", "%B %d, %Y").date()

        return [
            datetime.combine(date1, meeting_time),
            datetime.combine(date2, meeting_time),
        ]
