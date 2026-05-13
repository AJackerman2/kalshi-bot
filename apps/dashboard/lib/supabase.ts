import { createClient, SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "./db-types";

type Client = SupabaseClient<Database, "kalshi">;

let _client: Client | null = null;

export function supabase(): Client {
  if (_client) return _client;
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    throw new Error(
      "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set on the dashboard.",
    );
  }
  _client = createClient<Database, "kalshi">(url, key, {
    auth: { persistSession: false },
    db: { schema: "kalshi" },
  });
  return _client;
}
