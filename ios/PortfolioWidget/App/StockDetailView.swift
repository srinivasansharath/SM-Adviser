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

    @StateObject private var exporter = WebPDFExporter()
    @State private var shareItem: ShareItem?
    @State private var exporting = false

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
    }
}

/// The per-stock analysis one-pager (bundled sample page in demo mode).
struct StockDetailView: View {
    let symbol: String
    var body: some View {
        let url = SettingsStore.isDemo
            ? Bundle.main.url(forResource: "DemoStock", withExtension: "html")
            : SettingsStore.stockURL(symbol)
        WebReportView(title: symbol, url: url, pdfName: "SM Adviser - \(symbol)")
    }
}

/// Minimal WKWebView wrapper that sends the Authorization header and exposes the view for PDF export.
struct AuthWebView: UIViewRepresentable {
    let url: URL
    let token: String
    var exporter: WebPDFExporter?

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView()
        webView.isOpaque = false
        webView.backgroundColor = .clear
        exporter?.webView = webView
        if url.isFileURL {
            webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
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
}

/// Bridges UIActivityViewController (the iOS share sheet) into SwiftUI.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
