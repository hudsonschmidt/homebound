import Supabase
import Foundation

/// Supabase client configuration for Realtime subscriptions
/// Used for instant UI updates when data changes on the server
enum SupabaseConfig {
    static let url = URL(string: "https://kolnssrlszsyylhouswp.supabase.co")!
    static let anonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtvbG5zc3Jsc3pzeXlsaG91c3dwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEyNDQ2NTcsImV4cCI6MjA3NjgyMDY1N30.D3eWhtUpoifs6YOOwQFmd6GZx8AH-_E7OAxuuCwmdsg"
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
