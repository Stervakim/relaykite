import { api } from "@/lib/pc-relay";
import { boundedBody, json } from "@/lib/phone-relay";
export const dynamic = "force-dynamic";
export async function POST(request: Request) {
  try {
    const body = await boundedBody(request, 4*1024*1024+8192);
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("JSON object required");
    return await api(request, body as Record<string, unknown>);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Bridge unavailable" }, 403);
  }
}
