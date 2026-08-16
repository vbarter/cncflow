import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  CNCFLOW: DurableObjectNamespace;
  FILES: R2Bucket;
  CNCFLOW_CORS_ORIGINS?: string;
  CNCFLOW_R2_ACCOUNT_ID?: string;
  CNCFLOW_R2_ACCESS_KEY_ID?: string;
  CNCFLOW_R2_SECRET_ACCESS_KEY?: string;
  CNCFLOW_R2_BUCKET?: string;
  VISION_API_KEY?: string;
  VISION_API_BASE?: string;
}

/**
 * Flask + CadQuery stay in the Container. Do not rewrite as a Worker.
 * SQLite is single-writer so we pin one instance. Parser polls even without HTTP.
 */
export class CncflowContainer extends Container<Env> {
  defaultPort = 5001;
  sleepAfter = "24h";
  enableInternet = true;

  get envVars(): Record<string, string> {
    return {
      CNCFLOW_DB_PATH: "/data/cncflow.db",
      CNCFLOW_REQUIRE_PERSISTENT_DB: "1",
      CNCFLOW_FILE_STORAGE: "/data/uploads",
      CNCFLOW_PARSE_INLINE: "1",
      CNCFLOW_CORS_ORIGINS: this.env.CNCFLOW_CORS_ORIGINS || "*",
      CNCFLOW_R2_ACCOUNT_ID: this.env.CNCFLOW_R2_ACCOUNT_ID || "",
      CNCFLOW_R2_ACCESS_KEY_ID: this.env.CNCFLOW_R2_ACCESS_KEY_ID || "",
      CNCFLOW_R2_SECRET_ACCESS_KEY: this.env.CNCFLOW_R2_SECRET_ACCESS_KEY || "",
      CNCFLOW_R2_BUCKET: this.env.CNCFLOW_R2_BUCKET || "cncflow-files",
      VISION_API_KEY: this.env.VISION_API_KEY || "",
      VISION_API_BASE: this.env.VISION_API_BASE || "https://api.tu-zi.com",
    };
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
    const upstream = await getContainer(env.CNCFLOW, "api").fetch(request);
    return withCors(request, upstream, origins);
  },
};
