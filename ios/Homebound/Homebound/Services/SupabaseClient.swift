import Supabase
import Foundation

/// Supabase client configuration for Realtime subscriptions
/// Used for instant UI updates when data changes on the server
enum SupabaseConfig {
    static let url: URL = {
        guard let urlString = Bundle.main.infoDictionary?["SUPABASE_URL"] as? String,
              let url = URL(string: urlString) else {
            fatalError("SUPABASE_URL not configured in Info.plist")
        }
        return url
    }()

    static let anonKey: String = {
        guard let key = Bundle.main.infoDictionary?["SUPABASE_ANON_KEY"] as? String else {
            fatalError("SUPABASE_ANON_KEY not configured in Info.plist")
        }
        return key
    }()
}

/// Global Supabase client instance for Realtime connections
/// Note: We only use Supabase for Realtime, not for authentication (handled by Python backend)
let supabase = SupabaseClient(
    supabaseURL: SupabaseConfig.url,
    supabaseKey: SupabaseConfig.anonKey,
    options: SupabaseClientOptions(
        auth: SupabaseClientOptions.AuthOptions(
            emitLocalSessionAsInitialSession: true
        )
    )
)
