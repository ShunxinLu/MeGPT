/**
 * API Route - Proxies document content requests to the Python backend
 */
import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        const { id } = await params;

        const response = await fetch(`${BACKEND_URL}/api/documents/${id}/content`, {
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
        console.error("Document content API proxy error:", error);
        return new Response(JSON.stringify({ detail: "Failed to connect to backend" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
        });
    }
}
