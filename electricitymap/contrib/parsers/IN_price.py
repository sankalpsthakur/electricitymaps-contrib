import re
from datetime import datetime, timedelta
from logging import Logger, getLogger
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from requests import Session

from electricitymap.contrib.lib.models.event_lists import PriceList
from electricitymap.contrib.parsers.lib.config import refetch_frequency
from electricitymap.contrib.parsers.lib.exceptions import ParserException
from electricitymap.contrib.types import ZoneKey

IEX_DAM_URL = "https://www.iexindia.com/market-data/day-ahead-market/market-snapshot"
IEX_SOURCE = "iexindia.com"
IN_TZ = ZoneInfo("Asia/Kolkata")

_DATE_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")
_TIME_BLOCK_PATTERN = re.compile(
    r"^(?P<hour>\d{2}):(?P<minute>\d{2})\s*-\s*\d{2}:\d{2}$"
)


def parse_iex_dam_price(
    content: bytes,
    zone_key: ZoneKey = ZoneKey("IN"),
    logger: Logger = getLogger(__name__),
) -> list[dict[str, Any]]:
    """Parse 15-minute unconstrained DAM market-clearing prices from IEX.

    The IEX table uses row spans for the delivery date and hour columns, so
    most rows do not repeat their date. The parser carries the last explicit
    delivery date forward and identifies rows by their time-block cell rather
    than relying on a fixed number of columns.
    """
    soup = BeautifulSoup(content, "lxml")
    prices = PriceList(logger)

    delivery_date = None
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if first_row is None:
            continue
        headers = [
            cell.get_text(" ", strip=True)
            for cell in first_row.find_all(["th", "td"])
        ]
        if not any("time block" in header.casefold() for header in headers):
            continue
        if not any("mcp" in header.casefold() for header in headers):
            continue

        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            if not cells:
                continue

            date_cell = next(
                (cell for cell in cells if _DATE_PATTERN.fullmatch(cell)), None
            )
            if date_cell is not None:
                delivery_date = datetime.strptime(date_cell, "%d-%m-%Y").date()

            time_block = next(
                (cell for cell in cells if _TIME_BLOCK_PATTERN.fullmatch(cell)), None
            )
            if time_block is None:
                continue
            if delivery_date is None:
                raise ParserException(
                    parser="IN_price.py",
                    message="IEX DAM row did not include a delivery date",
                    zone_key=zone_key,
                )

            price_text = cells[-1].replace(",", "").strip()
            if price_text in {"", "-"}:
                continue

            time_match = _TIME_BLOCK_PATTERN.fullmatch(time_block)
            assert time_match is not None
            event_datetime = datetime(
                delivery_date.year,
                delivery_date.month,
                delivery_date.day,
                int(time_match.group("hour")),
                int(time_match.group("minute")),
                tzinfo=IN_TZ,
            )
            prices.append(
                zoneKey=zone_key,
                datetime=event_datetime,
                price=float(price_text),
                currency="INR",
                source=IEX_SOURCE,
            )

        if prices:
            break

    result = prices.to_list()
    if not result:
        raise ParserException(
            parser="IN_price.py",
            message="No IEX day-ahead market prices found",
            zone_key=zone_key,
        )
    return result


@refetch_frequency(timedelta(hours=1))
def fetch_price(
    zone_key: ZoneKey = ZoneKey("IN"),
    session: Session | None = None,
    target_datetime: datetime | None = None,
    logger: Logger = getLogger(__name__),
) -> list[dict[str, Any]]:
    """Fetch the latest 15-minute unconstrained day-ahead MCP from IEX."""
    if target_datetime is not None:
        raise NotImplementedError("This parser does not yet support historical dates")

    session = session or Session()
    response = session.get(
        IEX_DAM_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; ElectricityMapsParser/1.0; "
                "+https://github.com/electricitymaps/electricitymaps-contrib)"
            )
        },
    )
    if not response.ok:
        raise ParserException(
            parser="IN_price.py",
            message=f"IEX DAM request returned {response.status_code}",
            zone_key=zone_key,
        )

    return parse_iex_dam_price(response.content, zone_key=zone_key, logger=logger)


if __name__ == "__main__":
    print(fetch_price())
