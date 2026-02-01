import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

type RouteContext = {
    params: Promise<{ id: string }>;
};

export async function GET(req: NextRequest, context: RouteContext) {
    const { id } = await context.params;
    const response = await fetch(`${BACKEND_URL}/api/email/emails/${id}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
        return new Response(response.statusText, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}

export async function DELETE(req: NextRequest, context: RouteContext) {
    const { id } = await context.params;
    const response = await fetch(`${BACKEND_URL}/api/email/emails/${id}`, {
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

export async function POST(req: NextRequest, context: RouteContext) {
    const { id } = await context.params;
    const response = await fetch(`${BACKEND_URL}/api/email/emails/${id}/read`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
        const error = await response.text();
        return new Response(error, { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}
