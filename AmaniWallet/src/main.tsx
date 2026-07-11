import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./App";

// Le service worker PWA n'est enregistré qu'en build de production (vite.config.ts,
// devOptions.enabled: false). En dev, on désenregistre tout SW resté d'une session
// précédente pour éviter qu'un navigateur serve du JS/CSS en cache et masque les
// changements récents (source d'un bug déjà rencontré : nav du bas figée sur l'ancien CSS).
if (import.meta.env.DEV && "serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((reg) => reg.unregister());
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
