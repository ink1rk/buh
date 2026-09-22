import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { applyTheme, useUiStore } from "./shared/store/ui";
import "./styles.css";

applyTheme(useUiStore.getState().theme);

const container = document.getElementById("root");
if (!container) throw new Error("Не найден корневой элемент #root");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
