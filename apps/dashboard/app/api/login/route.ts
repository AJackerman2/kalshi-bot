import { NextResponse } from "next/server";

const COOKIE_NAME = "kbm-auth";
const MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export async function POST(req: Request) {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    return NextResponse.json({ ok: false, error: "not_configured" }, { status: 503 });
  }
  const form = await req.formData();
  const supplied = String(form.get("password") ?? "");
  if (supplied !== expected) {
    const url = new URL("/login", req.url);
    url.searchParams.set("error", "bad_password");
    const next = form.get("next");
    if (typeof next === "string" && next) url.searchParams.set("next", next);
    return NextResponse.redirect(url, { status: 303 });
  }
  const next = form.get("next");
  const destination = typeof next === "string" && next.startsWith("/") ? next : "/";
  const res = NextResponse.redirect(new URL(destination, req.url), { status: 303 });
  res.cookies.set(COOKIE_NAME, supplied, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
  return res;
}
