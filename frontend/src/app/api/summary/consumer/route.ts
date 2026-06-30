import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/backendProxy";

export async function GET(req: NextRequest) {
  return proxyToBackend(req, "/api/summary/consumer");
}
