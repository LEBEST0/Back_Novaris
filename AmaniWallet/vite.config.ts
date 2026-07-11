import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Amani Wallet",
        short_name: "Amani",
        description: "Portefeuille mobile de démonstration — Votre argent, votre confiance.",
        theme_color: "#1B3FA0",
        background_color: "#FFFFFF",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
        ],
      },
      devOptions: {
        // Désactivé en dev : le service worker mettait en cache d'anciens modules JS et
        // masquait les modifications (Vite HMR + SW précaching ne font pas bon ménage).
        // Le PWA (manifest + SW) reste testable via `npm run build && npm run preview`.
        enabled: false,
      },
    }),
  ],
  server: {
    host: "127.0.0.1",
    port: 5180,
  },
});
