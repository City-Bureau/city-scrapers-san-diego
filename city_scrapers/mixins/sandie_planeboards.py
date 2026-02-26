import re
from datetime import datetime

import scrapy
from city_scrapers_core.constants import COMMITTEE, BOARD, CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from w3lib.html import remove_tags
import re
from datetime import datetime, time
from dateutil.relativedelta import relativedelta, MO, TU, WE, TH, FR, SA, SU


class SandiePlanboardsMixinMeta(type):
    """
    Metaclass that enforces the implementation of required static
    variables in child classes that inherit from the "Mixin" class.
    """

    def __init__(cls, name, bases, dct):
        required_static_vars = ["agency", "name", "group_param"]
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
    timezone = "America/Los_Angeles"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    _time_notes = "Please refer to the meeting attachments for more accurate meeting time and location."

    main_url = "https://www.sandiego.gov/"

    _seen_dates = set()
    _folder_year = None

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
                location=self._parse_location(response),
                links=self._parse_links(record),
                source=response.url,
            )

            meeting["status"] = self._get_status(meeting, record["title"])
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _get_status(self, meeting, title):
        if re.search(r"\b(adjournment|adjourned|date change|no meeting)\b", title, re.IGNORECASE):
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
    
    def _extract_date(self, title, meeting_time=None):
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
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s*\d{4}",
            title_normalized,
            re.IGNORECASE,
        )
        if not match:
            return None
        
        meeting_date = datetime.strptime(match.group(), "%B %d, %Y").date()

        return datetime.combine(meeting_date, meeting_time)
    
    def _extract_time(self, response):
        recurring_info = response.xpath(
            '//h2[normalize-space()="Meeting Info"]/following-sibling::div'
        )

        time_elements = (
            recurring_info.css('div.cell.auto p') or 
            recurring_info.xpath('.//div[contains(@class, "ten sm-ten columns")]')
        )

        if time_elements:
            time_text = time_elements[0]

        meeting_time = re.search(
            r"\b\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.)",
            time_text.get(),
            re.IGNORECASE,
        )

        if meeting_time:
            raw = meeting_time.group().lower()
            normalized = re.sub(
                r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\.?",
                lambda m: f"{m.group(1)}:{m.group(2) or '00'} {'AM' if m.group(3).startswith('a') else 'PM'}",
                raw,
            )
            meeting_time = datetime.strptime(normalized.strip(), "%I:%M %p").time()
        elif "noon" in time_text.get().lower():
            meeting_time = time(12, 0)
        else:
            meeting_time = time(0, 0)

        return meeting_time
    
    def _parse_meetings(self, response):
        agendas = []
        minutes_by_date = {}

        meeting_time = self._extract_time(response)

        for agenda in response.xpath(
            "//div[@id='tab-item-1']//li[a and not(ancestor::li/ul)]/a[contains(@href, '.pdf')]"
        ):
            title = re.sub(r"\s+", " ", agenda.css("::text").get("")).strip()
            date = self._extract_date(title, meeting_time)

            if date:
                agendas.append({
                    "title": title,
                    "agenda_url": response.urljoin(agenda.attrib["href"]),
                    "date": date,
                })

        for minutes in response.xpath(
            "//div[@id='tab-item-2']//li[a and not(ancestor::li/ul)]/a[contains(@href, '.pdf')]"
        ):
            title = re.sub(r"\s+", " ", minutes.css("::text").get("")).strip()
            date = self._extract_date(title, meeting_time)

            if date:
                minutes_by_date[date] = response.urljoin(minutes.attrib["href"])
        
        for agenda in agendas:
            if minutes_by_date.get(agenda["date"]):
                agenda["minute_url"] = minutes_by_date[agenda["date"]]

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
        regular_pattern = re.fullmatch(
            r"(agenda)",
            title_str,
            re.IGNORECASE
        )

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
            r"^Notice of Meeting (cancellation|cancelation|postponement|adjournment|date change)$",
        ]

        if any(re.search(p.lower(), title_str.lower()) for p in cancellation_only_patterns):
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
    
    def _parse_location(self, response):
        meeting_info = response.xpath(
            '//h2[normalize-space()="Meeting Info"]/following-sibling::div'
        )

        location_elements = (
            meeting_info.xpath('.//div[contains(@class, "cell auto")]') or
            meeting_info.xpath('.//div[contains(@class, "ten sm-ten columns")]')
        )

        if location_elements:
            raw_location_info = location_elements[1]

        location_info = [text.strip() for text in raw_location_info.xpath('.//p//text()').getall() if text.strip()]
        test_text = " ".join(text.lower() for text in location_info)
        location = {}

        location_text = " ".join(location_info)
        location_text = re.sub(r'\s,', ',', location_text).strip()
        location_match = re.search(r"\b\d{1,5}\s+[A-Za-z]", location_text)

        if "check" in test_text and "agenda" in test_text:
            location["name"] = "Check agenda for meeting location"
            location["address"] = "TBD"
        elif "virtual" in test_text:
            location["name"] = "Virtual Meeting"
            location["address"] = ""
        else:
            # location["name"] = " ".join(self._normalize_p_text(location_info[:2])) if len(location_info) > 3 else self._normalize_p_text(location_info[0])
            # location["address"] = ", ".join(location_info[2:]) if len(location_info) > 3 else ", ".join(location_info[1:])
            location["name"] = location_text[:location_match.start()].strip(" ,")
            location["address"] = location_text[location_match.start():].strip(" ,")

        return location

    def _normalize_p_text(self, p):
        return re.sub(r'\s+', ' ', p).strip()