import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET(req: NextRequest) {
    const response = await fetch(`${BACKEND_URL}/api/email/config/classification`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
        return new Response(response.statusText, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}

export async function POST(req: NextRequest) {
    const body = await req.json();
    const response = await fetch(`${BACKEND_URL}/api/email/config/classification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const error = await response.text();
        return new Response(error, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}
