import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const COOKIE_NAME = "kbm-auth";
const MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export const config = {
  matcher: ["/((?!_next/|favicon|robots|api/login).*)"],
};

export function middleware(req: NextRequest) {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    // Fail closed: if the env var is missing the dashboard is locked.
    return new NextResponse("Dashboard password not configured", { status: 503 });
  }
  const supplied = req.cookies.get(COOKIE_NAME)?.value;
  if (supplied === expected) return NextResponse.next();

  // Allow rendering the login page itself.
  if (req.nextUrl.pathname === "/login") return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", req.nextUrl.pathname);
  return NextResponse.redirect(url);
}
