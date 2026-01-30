/**
 * API Routes for /api/chats/search
 */
import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET(req: NextRequest) {
    const searchParams = req.nextUrl.searchParams;
    const q = searchParams.get("q") || "";

    try {
        const response = await fetch(`${BACKEND_URL}/api/chats/search?q=${encodeURIComponent(q)}`);
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: "Failed to search chats" }, { status: 500 });
    }
}
