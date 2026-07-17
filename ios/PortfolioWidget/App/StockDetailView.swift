import SwiftUI
import WebKit

/// Holds the WKWebView so the SwiftUI layer can export the current page as a PDF to share.
final class WebPDFExporter: ObservableObject {
    weak var webView: WKWebView?

    func exportPDF(named name: String, completion: @escaping (URL?) -> Void) {
        guard let webView else { completion(nil); return }
        webView.createPDF(configuration: WKPDFConfiguration()) { result in
            switch result {
            case .success(let data):
                let safe = name.replacingOccurrences(of: "/", with: "-")
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(safe).pdf")
                do { try data.write(to: url); completion(url) } catch { completion(nil) }
            case .failure:
                completion(nil)
            }
        }
    }
}

struct ShareItem: Identifiable { let id = UUID(); let url: URL }

/// A server-rendered HTML page (per-stock analysis or the full daily report) shown in a web
/// view, with a toolbar button that exports the current page as a PDF and opens the share sheet.
struct WebReportView: View {
    let title: String
    let url: URL?
    let pdfName: String
    var editableSymbol: String? = nil   // when set + server supports it, shows an Edit-thesis button

    @StateObject private var exporter = WebPDFExporter()
    @State private var shareItem: ShareItem?
    @State private var exporting = false
    @State private var showThesis = false
    @State private var thesisSaved = false

    private var canEditThesis: Bool {
        editableSymbol != nil && !SettingsStore.isDemo && SettingsStore.serverHas("thesis_editing")
    }

    var body: some View {
        Group {
            if let url {
                AuthWebView(url: url, token: SettingsStore.token, exporter: exporter)
                    .ignoresSafeArea(edges: .bottom)
            } else {
                ContentUnavailableView("Not connected", systemImage: "wifi.slash")
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if canEditThesis {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showThesis = true } label: { Image(systemName: "square.and.pencil") }
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    exporting = true
                    exporter.exportPDF(named: pdfName) { out in
                        exporting = false
                        if let out { shareItem = ShareItem(url: out) }
                    }
                } label: {
                    if exporting { ProgressView() } else { Image(systemName: "square.and.arrow.up") }
                }
                .disabled(url == nil)
            }
        }
        .sheet(item: $shareItem) { item in ShareSheet(items: [item.url]) }
        .sheet(isPresented: $showThesis) {
            if let sym = editableSymbol {
                ThesisEditorView(symbol: sym) { thesisSaved = true }
            }
        }
        .alert("Thesis saved", isPresented: $thesisSaved) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("It'll be used in tomorrow's analysis.")
        }
    }
}

/// The per-stock analysis one-pager (bundled sample page in demo mode), with a thesis editor.
struct StockDetailView: View {
    let symbol: String
    var body: some View {
        let url = SettingsStore.isDemo
            ? Bundle.main.url(forResource: "DemoStock", withExtension: "html")
            : SettingsStore.stockURL(symbol)
        WebReportView(title: symbol, url: url, pdfName: "SM Adviser - \(symbol)", editableSymbol: symbol)
    }
}

/// The weekly new-stock screener shortlist (server-rendered one-pager), or a bundled sample in
/// demo mode. An optional `anchor` (a stock symbol) deep-links to that stock's section in the
/// report, so tapping a row lands on the right analysis instead of the top of the page.
struct NewStockIdeasView: View {
    var anchor: String? = nil

    /// Match the server's anchor ids (candidates_page._anchor): non-alphanumerics -> "-".
    private static func fragment(for symbol: String) -> String {
        let mapped = symbol.map { ($0.isLetter || $0.isNumber) ? $0 : "-" }
        var s = String(mapped)
        while s.contains("--") { s = s.replacingOccurrences(of: "--", with: "-") }
        return "stock-" + s.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    }

    private var url: URL? {
        let base = SettingsStore.isDemo
            ? Bundle.main.url(forResource: "DemoCandidates", withExtension: "html")
            : SettingsStore.candidatesURL
        guard let base, let anchor else { return base }
        var comps = URLComponents(url: base, resolvingAgainstBaseURL: false)
        comps?.fragment = Self.fragment(for: anchor)
        return comps?.url ?? base
    }

    var body: some View {
        WebReportView(title: anchor ?? "New-stock ideas", url: url, pdfName: "SM Adviser - Ideas")
    }
}

/// Minimal WKWebView wrapper that sends the Authorization header and exposes the view for PDF export.
struct AuthWebView: UIViewRepresentable {
    let url: URL
    let token: String
    var exporter: WebPDFExporter?

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.navigationDelegate = context.coordinator
        context.coordinator.fragment = url.fragment   // scroll target after load (deep-link)
        exporter?.webView = webView
        if url.isFileURL {
            // loadFileURL wants a plain path; strip any fragment — we scroll via JS on didFinish.
            var comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
            comps?.fragment = nil
            let fileURL = comps?.url ?? url
            webView.loadFileURL(fileURL, allowingReadAccessTo: fileURL.deletingLastPathComponent())
        } else {
            var request = URLRequest(url: url)
            if !token.isEmpty {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            webView.load(request)
        }
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    /// Scrolls to the deep-link anchor once the page finishes loading (reliable for file + https).
    final class Coordinator: NSObject, WKNavigationDelegate {
        var fragment: String?
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            guard let f = fragment, !f.isEmpty else { return }
            // f is sanitised to [A-Za-z0-9-] by NewStockIdeasView, so it's safe to inline.
            webView.evaluateJavaScript(
                "var e=document.getElementById('\(f)'); if(e){e.scrollIntoView(true);}",
                completionHandler: nil)
        }
    }
}

/// Bridges UIActivityViewController (the iOS share sheet) into SwiftUI.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
