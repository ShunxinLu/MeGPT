/**
 * API Route - Proxies document requests to the Python backend
 */
import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function POST(req: NextRequest) {
    try {
        const formData = await req.formData();

        // Forward FormData to backend
        const backendFormData = new FormData();
        for (const [key, value] of formData.entries()) {
            backendFormData.append(key, value);
        }

        const response = await fetch(`${BACKEND_URL}/api/documents`, {
            method: "POST",
            body: backendFormData,
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: "Backend error" }));
            return new Response(JSON.stringify(errorData), {
                status: response.status,
                headers: { "Content-Type": "application/json" },
            });
        }

        const result = await response.json();
        return new Response(JSON.stringify(result), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        });
    } catch (error) {
        console.error("Documents API proxy error:", error);
        return new Response(JSON.stringify({ detail: "Failed to connect to backend" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
        });
    }
}

export async function GET(req: NextRequest) {
    try {
        const { searchParams } = new URL(req.url);
        const chatId = searchParams.get("chat_id");
        const limit = searchParams.get("limit") || "50";

        const params = new URLSearchParams();
        if (chatId) params.append("chat_id", chatId);
        if (limit) params.append("limit", limit);

        const response = await fetch(`${BACKEND_URL}/api/documents?${params.toString()}`, {
            method: "GET",
        });

        if (!response.ok) {
            return new Response("Backend error", { status: response.status });
        }

        const result = await response.json();
        return new Response(JSON.stringify(result), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        });
    } catch (error) {
        console.error("Documents API proxy error:", error);
        return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        });
    }
}
