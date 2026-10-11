import { NextRequest } from "next/server";
import { handleApiProxy } from "@/lib/apiProxy";

export const dynamic = "force-dynamic";

type RouteProps = {
  params: Promise<{ path?: string[] }>;
};

async function forward(request: NextRequest, props: RouteProps) {
  const resolved = await props.params;
  return handleApiProxy(request, resolved?.path);
}

export async function GET(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}

export async function POST(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}

export async function PUT(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}

export async function PATCH(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}

export async function DELETE(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}

export async function HEAD(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}

export async function OPTIONS(request: NextRequest, props: RouteProps) {
  return forward(request, props);
}
