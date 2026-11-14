import { NextResponse } from "next/server";
import { sendPlaybook } from "@/lib/data";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const body = (await request.json()) as { approved?: boolean; recipient?: string };
  if (body.approved !== true) {
    return NextResponse.json({ ok: false, message: "Explicit approval is required." }, { status: 400 });
  }
  const { id } = await params;
  return NextResponse.json(await sendPlaybook(id, body.recipient ?? ""));
}
