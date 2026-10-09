import type { components } from "./schema";

type Schemas = components["schemas"];

export type PaperSummary = Schemas["PaperSummary"];
export type PaperDetail = Schemas["PaperDetail"];
export type GraphSummary = Schemas["GraphSummary"];
export type SimilarPaper = Schemas["SimilarPaper"];
export type PaperInsightResult = Schemas["PaperInsightResult"];
export type AskResponse = Schemas["AskResponse"];
export type AnswerSource = Schemas["Source"];
