import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  CNCFLOW: DurableObjectNamespace;
  FILES: R2Bucket;
  CNCFLOW_CORS_ORIGINS?: string;
  CNCFLOW_R2_ACCOUNT_ID?: string;
  CNCFLOW_R2_ACCESS_KEY_ID?: string;
  CNCFLOW_R2_SECRET_ACCESS_KEY?: string;
  CNCFLOW_R2_BUCKET?: string;
  TUZI_API_KEY?: string;
  TUZI_MODEL?: string;
  // Legacy secret name kept so existing deployments continue to work.
  VISION_API_KEY?: string;
}

/**
 * Flask + CadQuery stay in the Container. Do not rewrite as a Worker.
 * SQLite is single-writer so we pin one instance. Parser polls even without HTTP.
 */
export class CncflowContainer extends Container<Env> {
  defaultPort = 5001;
  sleepAfter = "24h";
  enableInternet = true;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Parent class assigns `envVars = {}` on the instance, which shadows a
    // subclass getter. Set the field after super so R2 secrets actually reach Flask.
    this.envVars = {
      CNCFLOW_DB_PATH: "/data/cncflow.db",
      CNCFLOW_REQUIRE_PERSISTENT_DB: "1",
      CNCFLOW_FILE_STORAGE: "/data/uploads",
      CNCFLOW_PARSE_INLINE: "1",
      CNCFLOW_CORS_ORIGINS: env.CNCFLOW_CORS_ORIGINS || "*",
      CNCFLOW_R2_ACCOUNT_ID: env.CNCFLOW_R2_ACCOUNT_ID || "",
      CNCFLOW_R2_ACCESS_KEY_ID: env.CNCFLOW_R2_ACCESS_KEY_ID || "",
      CNCFLOW_R2_SECRET_ACCESS_KEY: env.CNCFLOW_R2_SECRET_ACCESS_KEY || "",
      CNCFLOW_R2_BUCKET: env.CNCFLOW_R2_BUCKET || "cncflow-files",
      TUZI_API_KEY: env.TUZI_API_KEY || env.VISION_API_KEY || "",
      TUZI_MODEL: env.TUZI_MODEL || "gpt-4.1-mini",
      TUZI_BASE_URL: "https://api.tu-zi.com/v1",
      CHAT_JAIL: "/app/chat-jail",
      CHAT_PORT: "3002",
      CHAT_HOST: "0.0.0.0",
    };
  }

  override fetch(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname.replace(/\/+$/, "") || "/";
    const chat = path === "/api/v1/chat" || path === "/api/chat";
    if (chat) {
      const self = this as { containerFetch?: (req: Request, port?: number) => Promise<Response> };
      if (typeof self.containerFetch === "function") {
        return self.containerFetch(request, 3002);
      }
      const headers = new Headers(request.headers);
      headers.set("cf-container-target-port", "3002");
      return super.fetch(new Request(request, { headers }));
    }
    return super.fetch(request);
  }

  override onActivityExpired(): void {
    // Parser worker polls SQLite; do not stop when HTTP is idle.
  }
}

function allowedOrigin(request: Request, raw: string | undefined): string | null {
  const origin = request.headers.get("Origin");
  if (!origin) return null;
  const allowed = (raw || "*").split(",").map((item) => item.trim()).filter(Boolean);
  if (allowed.includes("*") || allowed.includes(origin)) return origin;
  return null;
}

function withCors(request: Request, response: Response, raw: string | undefined): Response {
  const origin = allowedOrigin(request, raw);
  if (!origin) return response;
  const headers = new Headers(response.headers);
  headers.set("Access-Control-Allow-Origin", origin);
  headers.set("Vary", "Origin");
  headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization");
  headers.set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS");
  headers.set("Access-Control-Max-Age", "86400");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origins = env.CNCFLOW_CORS_ORIGINS || "*";
    if (request.method === "OPTIONS") {
      return withCors(request, new Response(null, { status: 204 }), origins);
    }
    const path = new URL(request.url).pathname.replace(/\/+$/, "") || "/";
    const chat = path === "/api/v1/chat" || path === "/api/chat";
    const upstream = await getContainer(env.CNCFLOW, "api").fetch(request);
    const proxied = withCors(request, upstream, origins);
    if (!chat) return proxied;
    const headers = new Headers(proxied.headers);
    // Content-Length / gzip wait for EOS. HTTP/2 forbids Transfer-Encoding.
    headers.delete("Content-Length");
    headers.delete("Transfer-Encoding");
    headers.set("Cache-Control", "no-cache, no-transform");
    headers.set("X-Accel-Buffering", "no");
    headers.set("Content-Encoding", "identity");
    return new Response(proxied.body, {
      status: proxied.status,
      statusText: proxied.statusText,
      headers,
    });
  },
};
