import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET(req: NextRequest) {
    // Forward query parameters for pagination and filtering
    const response = await fetch(`${BACKEND_URL}/api/email/emails${req.nextUrl.search}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
        return new Response(response.statusText, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}

export async function DELETE(req: NextRequest) {
    // For bulk delete or other operations
    const response = await fetch(`${BACKEND_URL}/api/email/emails`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
        const error = await response.text();
        return new Response(error, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}
