/**
 * API Routes for /api/chats/[id]
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = "http://localhost:8000";

export async function GET(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params;
    try {
        const response = await fetch(`${BACKEND_URL}/api/chats/${id}`);
        if (!response.ok) {
            return NextResponse.json({ error: "Chat not found" }, { status: 404 });
        }
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: "Failed to fetch chat" }, { status: 500 });
    }
}

export async function PATCH(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params;
    try {
        const body = await req.json();
        const response = await fetch(`${BACKEND_URL}/api/chats/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: "Failed to update chat" }, { status: 500 });
    }
}

export async function DELETE(
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params;
    try {
        const response = await fetch(`${BACKEND_URL}/api/chats/${id}`, {
            method: "DELETE",
        });
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ error: "Failed to delete chat" }, { status: 500 });
    }
}
