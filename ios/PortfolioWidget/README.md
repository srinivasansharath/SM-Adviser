# SM Adviser — iPhone Widget (SwiftUI / WidgetKit)

A native home-screen widget that shows your holdings with their **Hold / Watch / Trim / Exit**
signals, colour-coded, Apple-Stocks style.

**Distribution model (Home-Assistant style):** the app is generic. On first launch you connect it
to **your own self-hosted SM Adviser server** — nothing is hardcoded. Anyone can run the same app;
each person points it at the backend they host. The app stores the server URL + token on-device and
shares them with the widget via an **App Group**.

## Files (and which target they belong to)

| File | App target | Widget target |
|---|:--:|:--:|
| `Shared/AppConfig.swift` (App Group id + settings store) | ✅ | ✅ |
| `Shared/WidgetModels.swift` | ✅ | ✅ |
| `Shared/PortfolioService.swift` | ✅ | ✅ |
| `Shared/Styles.swift` | ✅ | ✅ |
| `App/SMAdviserApp.swift` | ✅ | — |
| `App/ContentView.swift` (dashboard + branching) | ✅ | — |
| `App/SetupView.swift` (connect-to-server screen) | ✅ | — |
| `Widget/PortfolioWidget.swift` | — | ✅ |
| `Widget/WidgetViews.swift` | — | ✅ |

The four `Shared/` files go in **both** targets (File Inspector → Target Membership).

## Prerequisites
- **Xcode** (on the Mac mini), an **iPhone**, an **Apple Developer account** ($99/yr for a widget
  that persists; a free Apple ID works but the app expires every 7 days).
- The iPhone must reach your server: install **Tailscale** on the iPhone, signed into the same
  tailnet as the NUC. (For local testing pre-deploy, use the same Wi-Fi + your Mac's LAN IP.)

## Steps

1. **New project:** Xcode → New → Project → **iOS → App**. Name **SM Adviser**, SwiftUI, Swift.
   Bundle id e.g. `com.sharath.smadviser`.
2. **Add the widget target:** File → New → Target → **Widget Extension**, name **PortfolioWidget**.
   Uncheck "Include Live Activity" and "Include Configuration App Intent". Activate the scheme.
3. **Delete the stubs** Xcode generated (the sample widget file; optionally the default ContentView).
4. **Add these source files**, setting Target Membership per the table (the `Shared/` four go in both).
5. **Enable the App Group on BOTH targets:** each target → Signing & Capabilities → **+ Capability →
   App Groups** → add `group.com.sharath.smadviser` (must match `AppConfig.appGroup` exactly, and be
   identical on both targets).
6. **Signing:** select your Team on both targets; give the app and widget unique bundle ids
   (`com.sharath.smadviser` and `com.sharath.smadviser.PortfolioWidget`).
7. **Allow the network call** only if you'll use a plain `http://` endpoint (e.g. local testing):
   app target → Info → **App Transport Security Settings → Allow Arbitrary Loads = YES**. A
   `https://…ts.net` Tailscale URL needs no exception.
8. **Build & run** the **SM Adviser** app on your iPhone; trust the developer cert if prompted.
9. **Connect:** the app opens on the setup screen. Enter your server URL (e.g.
   `https://nuc.tailXXXX.ts.net:8787`) and your `WIDGET_API_TOKEN` (or leave blank). Tap **Connect** —
   it validates against `/health`. On success you see your portfolio.
10. **Add the widget:** long-press the home screen → **+** → **SM Adviser** → pick a size → Add.

## Testing before the NUC is deployed
Run the backend on your Mac and connect over Wi-Fi:
```bash
.venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8787
```
In the app's setup screen enter `http://<your-Mac-LAN-IP>:8787`, enable ATS (step 7), keep the
iPhone on the same Wi-Fi.

## Notes
- **No hardcoded server** — change servers anytime via the app (Disconnect → reconnect). This is what
  makes it App-Store-shippable as one generic binary.
- **Refresh cadence:** WidgetKit reloads the timeline ~hourly; the meaningful update is after the
  morning run regenerates `widget.json`. A daily-signal widget, not a live ticker (by design).
- **Colours:** Hold/Accumulate = green, Watch = yellow, Trim = orange, Exit = red.
- **Token storage:** currently the App Group's shared `UserDefaults` (on-device, sandboxed). For a
  public App Store release, move the token to the Keychain — noted as a hardening step.
