from app.connectors.fundamentals_universe import (
    MockUniverse,
    ScreenerBulk,
    get_universe_source,
)

# A trimmed screener public-screen results table: header row with inline units + custom columns,
# two data rows each linking to /company/<SYMBOL>/, and a totals row to be ignored.
_PAGE = """
<table class="data-table">
  <thead><tr>
    <th>S.No.</th><th>Name</th><th>CMPRs.</th><th>P/E</th><th>Mar CapRs.Cr.</th>
    <th>Div Yld%</th><th>ROCE%</th><th>ROE%</th><th>Sales growth 5Years%</th>
    <th>Pledged percentage%</th>
  </tr></thead>
  <tbody>
    <tr><td>1.</td><td><a href="/company/TCS/">TCS</a></td><td>3,890.50</td><td>28.4</td>
        <td>14,20,000.00</td><td>1.20</td><td>55.00</td><td>47.00</td><td>12.50</td><td>0.00</td></tr>
    <tr><td>2.</td><td><a href="/company/SEPC/">SEPC</a></td><td>6.21</td><td></td>
        <td>1,100.00</td><td>0.00</td><td>-3.00</td><td>-5.00</td><td>8.00</td><td>45.00</td></tr>
    <tr><td></td><td>Median: 2 rows</td><td></td><td></td><td></td><td></td><td></td>
        <td></td><td></td><td></td></tr>
  </tbody>
</table>
"""


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Serves _PAGE on page 1, an empty table afterwards (end of results)."""

    def __init__(self, page1):
        self.page1 = page1
        self.pages_fetched = []

    def get(self, url, params=None):
        page = (params or {}).get("page", 1)
        self.pages_fetched.append(page)
        return _FakeResp(self.page1 if page == 1 else '<table class="data-table"></table>')


def test_parse_page_maps_headers_and_symbols():
    sb = ScreenerBulk("https://www.screener.in/screens/1/x/")
    rows = sb._parse_page(_PAGE)
    assert [r["symbol"] for r in rows] == ["TCS", "SEPC"]  # totals row dropped
    tcs = rows[0]
    assert tcs["pe"] == 28.4
    assert tcs["market_cap"] == 1420000.0        # commas stripped
    assert tcs["roce"] == 55.0 and tcs["roe"] == 47.0
    assert tcs["sales_cagr_5y"] == 12.5          # custom column mapped by header name
    assert tcs["promoter_pledge"] == 0.0
    # A blank cell (SEPC P/E) becomes None, not a crash.
    assert rows[1]["pe"] is None and rows[1]["promoter_pledge"] == 45.0


def test_get_universe_stops_on_short_page():
    client = _FakeClient(_PAGE)
    sb = ScreenerBulk("https://www.screener.in/screens/1/x/", client=client)
    uni = sb.get_universe()
    assert [r["symbol"] for r in uni] == ["TCS", "SEPC"]
    assert client.pages_fetched == [1]            # 2 rows (<25) => last page, no wasted fetch


def test_get_universe_paginates_full_pages():
    # 25-row pages force a real page-2 fetch; a repeated page past the end stops the loop.
    rows = "".join(
        f'<tr><td>{i}.</td><td><a href="/company/S{i}/">S{i}</a></td>'
        f'<td>10</td><td>15</td><td>500</td><td>0</td><td>20</td><td>18</td><td>11</td><td>0</td></tr>'
        for i in range(1, 26)
    )
    full = _PAGE.replace(
        _PAGE[_PAGE.find("<tbody>") + 7:_PAGE.find("</tbody>")], rows
    )
    calls = {"n": 0}

    class C:
        def get(self, url, params=None):
            calls["n"] += 1
            # page 1 & 2 identical full pages; dedup guard must stop at page 2.
            return _FakeResp(full)

    sb = ScreenerBulk("https://www.screener.in/screens/1/x/", client=C())
    uni = sb.get_universe()
    assert len(uni) == 25                          # 25 unique; page 2 repeats -> deduped & stops
    assert calls["n"] == 2


def test_norm_header():
    assert ScreenerBulk._norm_header("Mar CapRs.Cr.") == "Mar Cap"
    assert ScreenerBulk._norm_header("Div Yld%") == "Div Yld"
    assert ScreenerBulk._norm_header("ROCE%") == "ROCE"


def test_mock_universe_and_factory():
    assert get_universe_source("mock").get_universe()[0]["symbol"] == "TCS"
    assert isinstance(get_universe_source("mock"), MockUniverse)
    u = MockUniverse().get_universe()
    assert len(u) == 8 and all("roce" in r and "symbol" in r for r in u)
