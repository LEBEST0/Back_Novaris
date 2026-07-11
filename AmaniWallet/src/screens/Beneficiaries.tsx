import { useEffect, useMemo, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { addBeneficiary, fetchBeneficiaries } from "../lib/api";
import { BottomNav, type NavScreen } from "../components/BottomNav";
import type { Beneficiary } from "../types";

interface BeneficiariesProps {
  userId: string;
  onNavigate: (screen: NavScreen) => void;
  onSelect: (beneficiary: Beneficiary) => void;
}

export function Beneficiaries({ userId, onNavigate, onSelect }: BeneficiariesProps) {
  const [items, setItems] = useState<Beneficiary[]>([]);
  const [query, setQuery] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    fetchBeneficiaries(userId)
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger les bénéficiaires."));
  };

  useEffect(load, [userId]);

  const filtered = useMemo(
    () => items.filter((b) => b.full_name.toLowerCase().includes(query.toLowerCase())),
    [items, query],
  );

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await addBeneficiary(userId, { full_name: fullName, phone });
      setFullName("");
      setPhone("");
      setShowForm(false);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d'ajouter ce bénéficiaire.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="screen">
      <div className="topbar">
        <div>
          <p className="eyebrow">Amani Wallet</p>
          <h1>Bénéficiaires</h1>
        </div>
      </div>

      <div className="search-input">
        <Search size={16} color="#6b7a8d" aria-hidden="true" />
        <input placeholder="Rechercher un bénéficiaire" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      {error && <p className="error-banner">{error}</p>}

      {showForm && (
        <form className="card" style={{ display: "grid", gap: 12 }} onSubmit={handleAdd}>
          <div className="field">
            <label>Nom complet</label>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div className="field">
            <label>Téléphone</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} required />
          </div>
          <button className="btn btn-primary btn-block" type="submit" disabled={saving}>
            {saving ? "Ajout en cours..." : "Ajouter"}
          </button>
        </form>
      )}

      <div className="card">
        {filtered.length === 0 && <p className="summary">Aucun bénéficiaire trouvé.</p>}
        {filtered.map((b) => (
          <button key={b.id} type="button" className="list-row" onClick={() => onSelect(b)}>
            <div className="avatar">{b.full_name.slice(0, 2).toUpperCase()}</div>
            <div className="main">
              <strong>{b.full_name}</strong>
              <span className="mono">{b.phone_masked}</span>
            </div>
            <span className={`badge ${b.status === "habituel" ? "badge-success" : "badge-neutral"}`}>{b.status}</span>
          </button>
        ))}
      </div>

      <button type="button" className="fab" onClick={() => setShowForm((v) => !v)} aria-label="Ajouter un bénéficiaire">
        {showForm ? <X size={22} /> : <Plus size={22} />}
      </button>

      <BottomNav active="beneficiaries" onNavigate={onNavigate} />
    </div>
  );
}
