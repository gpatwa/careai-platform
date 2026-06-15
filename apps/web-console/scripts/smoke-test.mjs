import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(new URL("..", import.meta.url).pathname);
const app = readFileSync(resolve(root, "src/App.tsx"), "utf8");
const styles = readFileSync(resolve(root, "src/styles.css"), "utf8");

const requiredAppFragments = [
  "Overview",
  "Models",
  "Deployments",
  "Monitoring",
  "RAG",
  "Governance",
  "VITE_CONTROL_PLANE_API_URL",
  "VITE_RAG_SERVICE_URL",
  "/models/${model.id}/promote",
  "/rag/query",
  "mockData"
];

const requiredStyleFragments = [
  ".app-shell",
  ".tabs",
  ".panel",
  ".metric-row",
  ".rag-form",
  "@media"
];

function assertIncludes(source, fragment, label) {
  if (!source.includes(fragment)) {
    throw new Error(`${label} is missing required fragment: ${fragment}`);
  }
}

for (const fragment of requiredAppFragments) {
  assertIncludes(app, fragment, "App.tsx");
}

for (const fragment of requiredStyleFragments) {
  assertIncludes(styles, fragment, "styles.css");
}

console.log("web-console smoke test passed");
