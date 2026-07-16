"""API contract version + advertised capabilities. See PROTOCOL.md for the rules.

`API_VERSION` is the app<->server contract version. It is an integer bumped ONLY on a
breaking change. Additive changes (new optional fields, new endpoints, new features) keep
the same version — clients ignore unknown fields and tolerate missing ones.

The pre-versioned payloads served to the 1.x app are retroactively "version 1"; this is the
first explicitly-versioned contract, and the v2 generation of the app/server, so it starts at 2.
"""

API_VERSION = 2
SERVER_VERSION = "2.0.0"
MIN_APP_BUILD = 1  # oldest iOS app build number this server still supports

# Capabilities the app negotiates against. Advertise a feature only when the server can serve
# it, so older apps hide what a newer server lacks and vice-versa.
FEATURES = [
    "widget",          # GET /widget.json
    "stock_analysis",  # GET /stock/{symbol}
    "full_report",     # GET /report/latest
    "intraday",        # widget.json carries near-live prices (prices_as_of)
    "thesis_editing",  # GET /theses, PUT /theses/{symbol}
    "news",            # corporate-announcement filings feed scoring + the analysis page
    "screening",       # GET /candidates(.json) — weekly new-stock buy-candidate shortlist
]
