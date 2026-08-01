from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from requests_mock import GET

from electricitymap.contrib.parsers.IN_price import (
    IEX_DAM_URL,
    fetch_price,
    parse_iex_dam_price,
)
from electricitymap.contrib.parsers.lib.exceptions import ParserException
from electricitymap.contrib.types import ZoneKey

FIXTURE = Path(__file__).parent / "mocks" / "IN" / "iex_dam.html"
IN_TZ = ZoneInfo("Asia/Kolkata")


def test_parse_iex_dam_price():
    prices = parse_iex_dam_price(FIXTURE.read_bytes())

    assert len(prices) == 3
    assert [price["price"] for price in prices] == [10000.0, 3850.97, 3339.6]
    assert prices[0]["datetime"] == datetime(2026, 8, 1, 0, 0, tzinfo=IN_TZ)
    assert prices[-1]["datetime"] == datetime(2026, 8, 1, 0, 45, tzinfo=IN_TZ)
    assert all(price["zoneKey"] == ZoneKey("IN") for price in prices)
    assert all(price["currency"] == "INR" for price in prices)
    assert all(price["source"] == "iexindia.com" for price in prices)


def test_fetch_price(session, requests_mock):
    requests_mock.register_uri(GET, IEX_DAM_URL, content=FIXTURE.read_bytes())

    assert fetch_price(session=session) == parse_iex_dam_price(FIXTURE.read_bytes())


def test_fetch_price_rejects_historical_dates(session):
    with pytest.raises(NotImplementedError, match="historical"):
        fetch_price(
            session=session,
            target_datetime=datetime(2026, 8, 1, tzinfo=IN_TZ),
        )


def test_fetch_price_raises_on_failed_request(session, requests_mock):
    requests_mock.register_uri(GET, IEX_DAM_URL, status_code=503)

    with pytest.raises(ParserException, match="503"):
        fetch_price(session=session)


def test_parse_raises_when_table_has_no_prices():
    with pytest.raises(ParserException, match="No IEX day-ahead market prices found"):
        parse_iex_dam_price(b"<html><body><table></table></body></html>")
