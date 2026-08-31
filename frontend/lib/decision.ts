import type { Decision } from "./api";
export function decisionTone(decision: Decision): "allow" | "review" | "block" { return decision.toLowerCase() as "allow" | "review" | "block"; }
