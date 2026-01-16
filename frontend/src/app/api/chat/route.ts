/**
 * API Route - Proxies chat requests to the Python backend
 * Streams the response with Data Stream Protocol events
 */
import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
    try {
        const body = await req.json();

        const response = await fetch("http://localhost:8000/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            return new Response("Backend error", { status: response.status });
        }

        // Stream the response directly from backend
        return new Response(response.body, {
            headers: {
                "Content-Type": "text/plain; charset=utf-8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "x-vercel-ai-ui-message-stream": "v1",
            },
        });
    } catch (error) {
        console.error("API proxy error:", error);
        return new Response("Failed to connect to backend", { status: 500 });
    }
}
