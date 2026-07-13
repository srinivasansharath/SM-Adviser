import SwiftUI
import WidgetKit

/// First-launch onboarding: connect to YOUR self-hosted SM Adviser server (Home-Assistant style).
struct SetupView: View {
    var onConnected: () -> Void

    @State private var baseURL = ""
    @State private var token = ""
    @State private var testing = false
    @State private var message: String?

    var body: some View {
        Form {
            Section {
                TextField("https://your-server.tailXXXX.ts.net:8787", text: $baseURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                SecureField("Access token (leave blank if none)", text: $token)
            } header: {
                Text("Your SM Adviser server")
            } footer: {
                Text("SM Adviser connects only to a server you host yourself. Enter the address of your own SM Adviser backend (e.g. on your home NUC over Tailscale). See the project README to run one.")
            }

            Section {
                Button {
                    Task { await connect() }
                } label: {
                    HStack {
                        Text(testing ? "Connecting…" : "Connect")
                        if testing { Spacer(); ProgressView() }
                    }
                }
                .disabled(baseURL.isEmpty || testing)

                if let message {
                    Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.red).font(.footnote)
                }
            }

            Section {
                Button {
                    SettingsStore.isDemo = true
                    WidgetCenter.shared.reloadAllTimelines()
                    onConnected()
                } label: {
                    Label("Preview with demo data", systemImage: "eye")
                }
            } footer: {
                Text("Explore the app with sample data — no server required.")
            }
        }
        .navigationTitle("Connect")
    }

    private func connect() async {
        testing = true
        message = nil
        let clean = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        SettingsStore.save(ServerSettings(baseURL: clean, token: token))
        if let err = await PortfolioService.validate() {
            message = err
            SettingsStore.clear()  // don't persist a bad server
            testing = false
        } else {
            WidgetCenter.shared.reloadAllTimelines()
            testing = false
            onConnected()
        }
    }
}
