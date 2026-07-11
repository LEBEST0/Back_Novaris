import { useEffect, useState } from "react";
import { LogOut, ShieldCheck } from "lucide-react";
import { fetchProfile } from "../lib/api";
import { BottomNav, type NavScreen } from "../components/BottomNav";
import type { Profile as ProfileData } from "../types";

interface ProfileProps {
  userId: string;
  onNavigate: (screen: NavScreen) => void;
  onLogout: () => void;
}

export function Profile({ userId, onNavigate, onLogout }: ProfileProps) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProfile(userId)
      .then(setProfile)
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger le profil."));
  }, [userId]);

  return (
    <div className="screen">
      <div className="topbar">
        <div>
          <p className="eyebrow">Amani Wallet</p>
          <h1>Profil &amp; sécurité</h1>
        </div>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {profile && (
        <>
          <div className="card detail-grid">
            <div className="row"><span>Nom</span><span>{profile.full_name}</span></div>
            <div className="row"><span>Téléphone</span><span className="mono">{profile.phone_masked}</span></div>
            <div className="row"><span>Compte créé le</span><span>{new Date(profile.created_at).toLocaleDateString("fr-FR")}</span></div>
            <div className="row"><span>Statut KYC</span><span>{profile.kyc_status}</span></div>
            <div className="row"><span>Appareil principal</span><span>{profile.primary_device ?? "—"}</span></div>
            <div className="row"><span>Dernière localisation</span><span>{profile.last_known_location ?? "—"}</span></div>
            <div className="row"><span>Dernier changement de PIN</span><span>{profile.last_pin_change}</span></div>
          </div>

          <div className="card">
            <p className="eyebrow">Méthodes de sécurité disponibles</p>
            {profile.security_methods.map((method) => (
              <div className="security-status" key={method} style={{ marginBottom: 8 }}>
                <ShieldCheck size={16} aria-hidden="true" />
                {method}
              </div>
            ))}
          </div>
        </>
      )}

      <button type="button" className="btn btn-secondary btn-block" onClick={onLogout}>
        <LogOut size={16} /> Se déconnecter
      </button>

      <BottomNav active="profile" onNavigate={onNavigate} />
    </div>
  );
}
