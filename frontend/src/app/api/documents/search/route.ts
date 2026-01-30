/**
 * API Route - Proxies document search requests to the Python backend
 */
import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET(req: NextRequest) {
    try {
        const { searchParams } = new URL(req.url);
        const q = searchParams.get("q");
        const chatId = searchParams.get("chat_id");
        const limit = searchParams.get("limit") || "10";

        if (!q) {
            return new Response(JSON.stringify({ results: [], total: 0 }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            });
        }

        const params = new URLSearchParams();
        params.append("q", q);
        if (chatId) params.append("chat_id", chatId);
        if (limit) params.append("limit", limit);

        const response = await fetch(`${BACKEND_URL}/api/documents/search?${params.toString()}`, {
            method: "GET",
        });

        if (!response.ok) {
            return new Response(JSON.stringify({ results: [], total: 0 }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            });
        }

        const result = await response.json();
        return new Response(JSON.stringify(result), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        });
    } catch (error) {
        console.error("Document search API proxy error:", error);
        return new Response(JSON.stringify({ results: [], total: 0 }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        });
    }
}
