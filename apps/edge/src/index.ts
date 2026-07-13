import { type Context, Hono } from "hono";

interface EdgeBindings {
	readonly RAILWAY_ORIGIN: string;
	readonly WORKER_ORIGIN_SECRET: string;
}

const app = new Hono<{ Bindings: EdgeBindings }>();
const permittedMethods = new Set(["GET", "HEAD"]);

app.on(["GET", "HEAD"], "/api/*", proxyToRailway);
app.on(["GET", "HEAD"], "/stream/*", proxyToRailway);

app.all("/api/*", () => methodNotAllowed());
app.all("/stream/*", () => methodNotAllowed());
app.all("*", () => notFound());

export default app;

async function proxyToRailway(
	context: Context<{ Bindings: EdgeBindings }>,
): Promise<Response> {
	const request = context.req.raw;
	if (!permittedMethods.has(request.method)) {
		return methodNotAllowed();
	}

	const origin = originUrl(context.env.RAILWAY_ORIGIN);
	if (!origin || !context.env.WORKER_ORIGIN_SECRET) {
		return errorResponse(503, "Transit edge is not configured.");
	}

	const incomingUrl = new URL(request.url);
	const targetUrl = new URL(
		`${incomingUrl.pathname}${incomingUrl.search}`,
		origin,
	);
	const headers = upstreamHeaders(
		request.headers,
		context.env.WORKER_ORIGIN_SECRET,
	);

	try {
		const upstreamResponse = await fetch(targetUrl, {
			headers,
			method: request.method,
			redirect: "manual",
		});
		return secureProxyResponse(
			upstreamResponse,
			incomingUrl.pathname.startsWith("/stream/"),
		);
	} catch {
		return errorResponse(
			502,
			"Transit data origin is temporarily unavailable.",
		);
	}
}

function methodNotAllowed(): Response {
	return new Response(JSON.stringify({ detail: "Method not allowed." }), {
		headers: {
			Allow: "GET, HEAD",
			"Content-Type": "application/json; charset=utf-8",
		},
		status: 405,
	});
}

function notFound(): Response {
	return new Response(JSON.stringify({ detail: "Not found." }), {
		headers: { "Content-Type": "application/json; charset=utf-8" },
		status: 404,
	});
}

function errorResponse(status: number, detail: string): Response {
	return new Response(JSON.stringify({ detail }), {
		headers: { "Content-Type": "application/json; charset=utf-8" },
		status,
	});
}

function originUrl(value: string): URL | null {
	try {
		const url = new URL(value);
		return url.protocol === "https:" ? url : null;
	} catch {
		return null;
	}
}

function upstreamHeaders(source: Headers, edgeSecret: string): Headers {
	const headers = new Headers();
	const accept = source.get("Accept");
	const lastEventId = source.get("Last-Event-ID");
	if (accept) {
		headers.set("Accept", accept);
	}
	if (lastEventId) {
		headers.set("Last-Event-ID", lastEventId);
	}
	headers.set("X-Transit-Edge-Secret", edgeSecret);
	headers.set("X-Forwarded-Proto", "https");
	return headers;
}

function secureProxyResponse(upstream: Response, isStream: boolean): Response {
	const headers = new Headers(upstream.headers);
	headers.set("Referrer-Policy", "no-referrer");
	headers.set("X-Content-Type-Options", "nosniff");
	headers.set("X-Frame-Options", "DENY");
	headers.set("Permissions-Policy", "geolocation=(), microphone=(), camera=()");
	headers.set("Vary", "Accept");
	if (isStream) {
		headers.set("Cache-Control", "no-store, no-transform");
		headers.set("X-Accel-Buffering", "no");
	} else {
		headers.set("Cache-Control", "no-store");
	}
	return new Response(upstream.body, { headers, status: upstream.status });
}
