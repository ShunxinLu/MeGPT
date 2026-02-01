import { NextRequest } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function POST(req: NextRequest) {
    const body = await req.json();

    const response = await fetch(`${BACKEND_URL}/api/providers/configure`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        return new Response("Backend error", { status: response.status });
    }

    const data = await response.json();
    return Response.json(data);
}
