import { describe, expect, it } from "vitest";
import { decisionTone } from "./decision";
describe("decisionTone", () => { it("maps business decisions to their visual tokens", () => { expect(decisionTone("BLOCK")).toBe("block"); expect(decisionTone("REVIEW")).toBe("review"); }); });
