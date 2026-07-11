import { Home, ListOrdered, User, Users } from "lucide-react";

export type NavScreen = "dashboard" | "beneficiaries" | "history" | "profile";

interface BottomNavProps {
  active: NavScreen;
  onNavigate: (screen: NavScreen) => void;
}

const items: Array<{ screen: NavScreen; label: string; icon: typeof Home }> = [
  { screen: "dashboard", label: "Accueil", icon: Home },
  { screen: "beneficiaries", label: "Bénéficiaires", icon: Users },
  { screen: "history", label: "Historique", icon: ListOrdered },
  { screen: "profile", label: "Profil", icon: User },
];

export function BottomNav({ active, onNavigate }: BottomNavProps) {
  return (
    <nav className="bottom-nav" aria-label="Navigation principale">
      {items.map(({ screen, label, icon: Icon }) => (
        <button
          key={screen}
          type="button"
          className={active === screen ? "is-active" : ""}
          onClick={() => onNavigate(screen)}
        >
          <Icon size={20} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
