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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return getContainer(env.CNCFLOW, "api").fetch(request);
  },
};
