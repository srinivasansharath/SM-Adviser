import Foundation

/// A per-stock investment thesis (GET /theses). Decoded with .convertFromSnakeCase.
struct ThesisData: Codable, Identifiable {
    var id: String { symbol }
    let symbol: String
    var thesis: String?
    var boughtReason: String?
    var conviction: String?        // high | medium | low
    var targetWeightPct: Double?
    var exitIf: [String]
    let updatedAt: String?
}

/// PUT /theses/{symbol} body (no symbol/updated_at). Encoded with .convertToSnakeCase.
struct ThesisUpsert: Codable {
    var thesis: String?
    var boughtReason: String?
    var conviction: String?
    var targetWeightPct: Double?
    var exitIf: [String]
}

/// GET /meta — capability + version negotiation.
struct ServerMeta: Codable {
    let apiVersion: Int
    let serverVersion: String
    let features: [String]
    let minAppBuild: Int
}

extension JSONDecoder {
    static var snake: JSONDecoder {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d
    }
}

extension JSONEncoder {
    static var snake: JSONEncoder {
        let e = JSONEncoder(); e.keyEncodingStrategy = .convertToSnakeCase; return e
    }
}
