import { query } from "@/lib/db";
import { NextResponse } from "next/server";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { outreach_status } = body;

    if (!outreach_status) {
      return NextResponse.json({ error: "outreach_status is required" }, { status: 400 });
    }

    const validStatuses = ["new", "contacted", "followed_up", "closed"];
    if (!validStatuses.includes(outreach_status)) {
      return NextResponse.json({ error: "Invalid outreach status" }, { status: 400 });
    }

    const res = await query(
      "UPDATE businesses SET outreach_status = $1 WHERE id = $2 RETURNING id",
      [outreach_status, id]
    );

    if (res.rows.length === 0) {
      return NextResponse.json({ error: "Business not found" }, { status: 404 });
    }

    return NextResponse.json({ success: true, id, outreach_status });
  } catch (error: any) {
    console.error("API error updating outreach status:", error);
    return NextResponse.json({ error: error.message || "Internal Server Error" }, { status: 500 });
  }
}
