import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET(req: NextRequest) {
    const response = await fetch(`${BACKEND_URL}/api/providers/list`, {
        headers: {
            "Content-Type": "application/json",
        },
    });

    if (!response.ok) {
        return new Response("Backend error", { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}
