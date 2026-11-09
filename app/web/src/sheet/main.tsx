import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/tokens.css";
import "@/styles/shared.css";
import "./sheet.css";
import { Sheet } from "./Sheet";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Missing #root element");
}

createRoot(container).render(
  <StrictMode>
    <Sheet />
  </StrictMode>,
);
