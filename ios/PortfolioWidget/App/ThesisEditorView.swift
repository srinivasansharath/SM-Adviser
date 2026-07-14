import SwiftUI

/// Edit one holding's investment thesis and save it to the server (PUT /theses/{symbol}).
/// Pre-loads the current thesis so a save never silently drops fields. The next morning run
/// scores against the updated thesis.
struct ThesisEditorView: View {
    let symbol: String
    var onSaved: () -> Void = {}

    @Environment(\.dismiss) private var dismiss

    @State private var thesis = ""
    @State private var boughtReason = ""
    @State private var conviction = "medium"
    @State private var targetWeight = ""
    @State private var exitIf: [String] = []
    @State private var loading = true
    @State private var saving = false
    @State private var error: String?

    private let convictions = ["high", "medium", "low"]

    var body: some View {
        NavigationStack {
            Form {
                if loading {
                    HStack { ProgressView(); Text("Loading…").foregroundStyle(.secondary) }
                } else {
                    Section("Why you own it") {
                        TextField("Your thesis for this stock", text: $thesis, axis: .vertical)
                            .lineLimit(2...6)
                    }
                    Section("What made you buy (optional)") {
                        TextField("Bought reason", text: $boughtReason, axis: .vertical)
                            .lineLimit(1...4)
                    }
                    Section("Conviction & sizing") {
                        Picker("Conviction", selection: $conviction) {
                            ForEach(convictions, id: \.self) { Text($0.capitalized).tag($0) }
                        }
                        HStack {
                            Text("Target weight")
                            Spacer()
                            TextField("—", text: $targetWeight)
                                .keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 70)
                            Text("%").foregroundStyle(.secondary)
                        }
                    }
                    Section {
                        ForEach(exitIf.indices, id: \.self) { i in
                            TextField("Condition", text: $exitIf[i], axis: .vertical)
                        }
                        .onDelete { exitIf.remove(atOffsets: $0) }
                        Button { exitIf.append("") } label: { Label("Add condition", systemImage: "plus") }
                    } header: {
                        Text("Exit if…")
                    } footer: {
                        Text("Conditions that would break the thesis. The agent checks these against the evidence each morning.")
                    }
                    if let error {
                        Section { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red) }
                    }
                }
            }
            .navigationTitle("\(symbol) — thesis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }.disabled(saving || loading)
                }
            }
            .task { await load() }
        }
    }

    private func load() async {
        loading = true
        let all = await PortfolioService.fetchTheses() ?? []
        if let t = all.first(where: { $0.symbol == symbol }) {
            thesis = t.thesis ?? ""
            boughtReason = t.boughtReason ?? ""
            conviction = t.conviction ?? "medium"
            targetWeight = t.targetWeightPct.map { String(format: "%g", $0) } ?? ""
            exitIf = t.exitIf
        }
        loading = false
    }

    private func save() async {
        saving = true; error = nil
        let body = ThesisUpsert(
            thesis: thesis.isEmpty ? nil : thesis,
            boughtReason: boughtReason.isEmpty ? nil : boughtReason,
            conviction: conviction,
            targetWeightPct: Double(targetWeight.trimmingCharacters(in: .whitespaces)),
            exitIf: exitIf.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        )
        if let err = await PortfolioService.putThesis(symbol, body) {
            error = err
            saving = false
        } else {
            saving = false
            onSaved()
            dismiss()
        }
    }
}
