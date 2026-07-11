import {
  Activity,
  BarChart3,
  FileText,
  GitBranch,
  Radar,
  SearchCheck,
} from "lucide-react";
import type { ReactNode } from "react";

export type Screen = "dashboard" | "analysis" | "investigation" | "graph" | "report";

interface AppLayoutProps {
  activeScreen: Screen;
  lastAnalysis: string;
  onNavigate: (screen: Screen) => void;
  children: ReactNode;
}

const navItems: Array<{ screen: Screen; label: string; icon: typeof BarChart3 }> = [
  { screen: "dashboard", label: "Dashboard", icon: BarChart3 },
  { screen: "analysis", label: "Analyse", icon: SearchCheck },
  { screen: "investigation", label: "Investigation", icon: Radar },
  { screen: "graph", label: "Graphe", icon: GitBranch },
  { screen: "report", label: "Rapport", icon: FileText },
];

export function AppLayout({
  activeScreen,
  lastAnalysis,
  onNavigate,
  children,
}: AppLayoutProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Navigation principale">
        <div className="brand">
          <Activity aria-hidden="true" />
          <div>
            <strong>Novaris AI</strong>
            <span>Fraud Control</span>
          </div>
        </div>
        <nav>
          {navItems.map(({ screen, label, icon: Icon }) => (
            <button
              key={screen}
              type="button"
              className={activeScreen === screen ? "is-active" : ""}
              onClick={() => onNavigate(screen)}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div>
            <span className="product-name">Novaris AI</span>
            <span className="demo-badge">Démo</span>
          </div>
          <span className="last-analysis">Dernière analyse : {lastAnalysis}</span>
        </header>
        {children}
      </main>
    </div>
  );
}
