/**
 * API Routes for /api/memories
 */
import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/api";

export async function GET() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/memories`);
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: "Failed to fetch memories" }, { status: 500 });
    }
}
