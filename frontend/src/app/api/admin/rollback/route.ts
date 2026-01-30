import { NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function POST(request: Request) {
    const body = await request.json();
    const res = await fetch(`${BACKEND_URL}/api/admin/rollback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
}
