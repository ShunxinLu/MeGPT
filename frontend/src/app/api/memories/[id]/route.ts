/**
 * API Routes for /api/memories/[id]
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = "http://localhost:8000";

export async function DELETE(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params;
    try {
        const response = await fetch(`${BACKEND_URL}/api/memories/${id}`, {
            method: "DELETE",
        });
        if (!response.ok) {
            return NextResponse.json({ error: "Memory not found" }, { status: 404 });
        }
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: "Failed to delete memory" }, { status: 500 });
    }
}
