from app.analytics.fundamentals import hard_override, score_fundamental, score_valuation
from app.connectors.fundamentals import MockFundamentals, ScreenerFundamentals, get_fundamentals


def test_quality_scores_higher_than_junk():
    good = score_fundamental({"roce": 25, "roe": 22, "debt_to_equity": 0.2, "interest_coverage": 9, "rev_growth_3y": 18})
    poor = score_fundamental({"roce": 6, "roe": 5, "debt_to_equity": 2.0, "interest_coverage": 1.2, "rev_growth_3y": -3})
    assert good > 60 > poor


def test_fundamental_none_without_fields():
    assert score_fundamental({}) is None
    assert score_fundamental({"pe": 20}) is None  # pe is valuation, not a quality field


def test_valuation_cheap_vs_expensive():
    cheap = score_valuation({"pe": 15, "industry_pe": 25})
    rich = score_valuation({"pe": 40, "industry_pe": 25})
    assert cheap > rich


def test_valuation_none_without_pe_or_pb():
    assert score_valuation({"roce": 20}) is None


def test_hard_override_triggers():
    cfg = {"scoring": {"hard_overrides": {"interest_coverage_below": 1.5, "promoter_pledge_pct_above": 50}}}
    assert hard_override({"interest_coverage": 1.0}, cfg) is not None
    assert hard_override({"promoter_pledge": 65}, cfg) is not None
    assert hard_override({"interest_coverage": 8, "promoter_pledge": 5}, cfg) is None


def test_mock_connector_returns_fields():
    f = MockFundamentals().get_fundamentals("TCS")
    assert {"pe", "roce", "roe", "debt_to_equity", "interest_coverage"}.issubset(f.keys())


def test_factory():
    assert get_fundamentals("mock").name == "mock"
    assert isinstance(get_fundamentals("screener"), ScreenerFundamentals)


# --- Stage-2 deep company-page parsing (hermetic, mirrors screener's real markup) ------------
_PAGE = """
<html><body>
  <ul id="top-ratios">
    <li><span class="name">Stock P/E</span><span class="number">28.4</span></li>
    <li><span class="name">ROCE</span><span class="number">55.0</span> %</li>
    <li><span class="name">ROE</span><span class="number">47.0</span> %</li>
  </ul>
  <table class="ranges-table"><tbody>
    <tr><th>Compounded Sales Growth</th></tr>
    <tr><td>10 Years:</td><td>9%</td></tr>
    <tr><td>5 Years:</td><td>12%</td></tr>
    <tr><td>3 Years:</td><td>6%</td></tr>
  </tbody></table>
  <table class="ranges-table"><tbody>
    <tr><th>Compounded Profit Growth</th></tr>
    <tr><td>5 Years:</td><td>15%</td></tr>
    <tr><td>3 Years:</td><td>8%</td></tr>
  </tbody></table>
  <table class="ranges-table"><tbody>
    <tr><th>Return on Equity</th></tr>
    <tr><td>5 Years:</td><td>49%</td></tr>
    <tr><td>3 Years:</td><td>52%</td></tr>
  </tbody></table>
  <section id="shareholding"><table>
    <tr><th></th><th>Mar 2024</th><th>Jun 2024</th></tr>
    <tr><td>Promoters+</td><td>72.0%</td><td>72.30%</td></tr>
    <tr><td>Public+</td><td>28.0%</td><td>27.70%</td></tr>
  </table></section>
  <section id="balance-sheet"><table>
    <tr><td>Equity Capital</td><td>320</td></tr>
    <tr><td>Reserves</td><td>39,148</td></tr>
    <tr><td>Borrowings+</td><td>76,141</td></tr>
    <tr><td>Total Liabilities</td><td>174,564</td></tr>
  </table></section>
  <div class="pros-cons"><ul>
    <li>Promoters have pledged 45.0% of their holding.</li>
  </ul></div>
</body></html>
"""


def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def test_screener_deep_parse_full_page():
    out = ScreenerFundamentals()._parse_all(_soup(_PAGE))
    # top ratios
    assert out["pe"] == 28.4 and out["roce"] == 55.0 and out["roe"] == 47.0
    # multi-year growth + ROE history (durability)
    assert out["sales_cagr_5y"] == 12.0 and out["sales_cagr_3y"] == 6.0
    assert out["profit_cagr_5y"] == 15.0
    assert out["roe_5y"] == 49.0 and out["roe_3y"] == 52.0
    # governance
    assert out["promoter_holding"] == 72.30      # latest quarter (last column)
    assert out["promoter_pledge"] == 45.0
    # D/E = Borrowings / (Equity Capital + Reserves) = 76141 / 39468
    assert out["debt_to_equity"] == round(76141 / (320 + 39148), 2)


def test_screener_parses_sector():
    html = ('<div>'
            '<a href="/market/IN07/">Industrials</a>'
            '<a href="/market/IN07/IN0702/">Capital Goods</a>'
            '<a href="/market/IN07/IN0702/IN070203/">Electrical Equipment</a>'
            '</div>')
    out = ScreenerFundamentals()._parse_all(_soup(html))
    assert out["sector"] == "Industrials"       # macro sector (first /market/ link)
    assert out["industry"] == "Capital Goods"


def test_screener_pledge_absent_means_zero():
    # A page with no pledge bullet -> pledge 0.0, not missing/None.
    html = _PAGE.replace("Promoters have pledged 45.0% of their holding.", "Company is debt free.")
    out = ScreenerFundamentals()._parse_all(_soup(html))
    assert out["promoter_pledge"] == 0.0


def test_screener_partial_page_drops_only_missing_section():
    # Only top-ratios present: still parses, no crash, pledge defaults to 0.
    html = '<ul id="top-ratios"><li><span class="name">ROCE</span><span class="number">18</span></li></ul>'
    out = ScreenerFundamentals()._parse_all(_soup(html))
    assert out["roce"] == 18.0
    assert "debt_to_equity" not in out and "sales_cagr_5y" not in out
    assert out["promoter_pledge"] == 0.0
