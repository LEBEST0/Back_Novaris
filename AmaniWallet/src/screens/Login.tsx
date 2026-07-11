import { useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { buildDeviceInfo } from "../lib/device";
import { login, register } from "../lib/api";
import { resolveDeviceOverrides, resolveLocation, toDemoSignalsPayload } from "../lib/demo";
import { RandomizedPinPad } from "../components/RandomizedPinPad";
import type { DemoScenario, EvaluateAccessResult } from "../types";

interface LoginProps {
  demoScenario: DemoScenario | null;
  onResetDemo: () => void;
  onLoginResult: (result: EvaluateAccessResult) => void;
}

type Mode = "login" | "signup";
type SignupStep = "identity" | "create-pin" | "confirm-pin";

export function Login({ demoScenario, onResetDemo, onLoginResult }: LoginProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [phone, setPhone] = useState("+2250700000001");
  const [fullName, setFullName] = useState("");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [signupStep, setSignupStep] = useState<SignupStep>("identity");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shuffleSeed, setShuffleSeed] = useState(0);

  const screenOpenedAt = useRef(Date.now());
  const pinStartedAt = useRef<number | null>(null);
  const correctionCount = useRef(0);
  const failedAttempts = useRef(0);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setPin("");
    setConfirmPin("");
    setSignupStep("identity");
    pinStartedAt.current = null;
    correctionCount.current = 0;
  };

  const runAccess = async (kind: "login" | "signup", enteredPin: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const device = await buildDeviceInfo(resolveDeviceOverrides(demoScenario));
      const location = await resolveLocation(demoScenario);
      const now = Date.now();
      const behaviour = {
        login_duration_ms: now - screenOpenedAt.current,
        pin_entry_duration_ms: pinStartedAt.current ? now - pinStartedAt.current : null,
        correction_count: correctionCount.current,
        failed_attempts: failedAttempts.current,
        time_on_page_ms: now - screenOpenedAt.current,
      };

      const result =
        kind === "login"
          ? await login({
              phone,
              pin: enteredPin,
              device,
              location,
              demo_signals: toDemoSignalsPayload(demoScenario),
              behaviour,
            })
          : await register({
              full_name: fullName,
              phone,
              pin: enteredPin,
              device,
              location,
              demo_signals: toDemoSignalsPayload(demoScenario),
              behaviour,
            });
      onLoginResult(result);
    } catch (err) {
      failedAttempts.current += 1;
      setShuffleSeed((s) => s + 1);
      setPin("");
      setConfirmPin("");
      if (kind === "signup") setSignupStep("create-pin");
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleLoginPinChange = (value: string) => {
    if (pinStartedAt.current === null) pinStartedAt.current = Date.now();
    if (value.length < pin.length) correctionCount.current += 1;
    setPin(value);
    if (value.length === 4) runAccess("login", value);
  };

  const handleSignupPinCreate = (value: string) => {
    if (pinStartedAt.current === null) pinStartedAt.current = Date.now();
    if (value.length < pin.length) correctionCount.current += 1;
    setPin(value);
    if (value.length === 4) {
      window.setTimeout(() => setSignupStep("confirm-pin"), 200);
    }
  };

  const handleSignupPinConfirm = (value: string) => {
    if (value.length < confirmPin.length) correctionCount.current += 1;
    setConfirmPin(value);
    if (value.length === 4) {
      if (value !== pin) {
        setError("Les deux saisies ne correspondent pas. Recommencez.");
        setShuffleSeed((s) => s + 1);
        setConfirmPin("");
        setPin("");
        setSignupStep("create-pin");
        return;
      }
      runAccess("signup", value);
    }
  };

  const handleIdentityContinue = (event: React.FormEvent) => {
    event.preventDefault();
    if (!fullName.trim() || !phone.trim()) return;
    setError(null);
    setSignupStep("create-pin");
  };

  return (
    <div className="screen no-nav">
      <div className="topbar">
        <div>
          <p className="eyebrow">Amani Wallet</p>
          <h1>{mode === "login" ? "Connexion" : "Créer un compte"}</h1>
        </div>
        <ShieldCheck size={22} color="#1B3FA0" aria-hidden="true" />
      </div>

      <div className="auth-tabs">
        <button type="button" className={mode === "login" ? "is-active" : ""} onClick={() => switchMode("login")}>
          Se connecter
        </button>
        <button type="button" className={mode === "signup" ? "is-active" : ""} onClick={() => switchMode("signup")}>
          Créer un compte
        </button>
      </div>

      {demoScenario && (
        <div className="demo-banner">
          Mode démonstration actif : <strong>{demoScenario.name}</strong>.{" "}
          <button type="button" className="link-button" style={{ display: "inline", padding: 0 }} onClick={onResetDemo}>
            Revenir au comportement normal
          </button>
        </div>
      )}

      {error && <p className="error-banner">{error}</p>}

      {mode === "login" && (
        <div className="screen" style={{ padding: 0, gap: 16 }}>
          <div className="field">
            <label htmlFor="phone">Numéro de téléphone</label>
            <input id="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" required />
          </div>
          <div className="field">
            <label>Mot de passe (4 chiffres)</label>
            <RandomizedPinPad value={pin} onChange={handleLoginPinChange} shuffleSeed={shuffleSeed} />
          </div>
          {submitting && <p className="summary">Vérification en cours...</p>}
          <button type="button" className="link-button" onClick={() => setError("Contactez votre agence Amani pour réinitialiser votre mot de passe.")}>
            Mot de passe oublié ?
          </button>
        </div>
      )}

      {mode === "signup" && signupStep === "identity" && (
        <form className="screen" style={{ padding: 0, gap: 16 }} onSubmit={handleIdentityContinue}>
          <div className="field">
            <label htmlFor="fullName">Nom complet</label>
            <input id="fullName" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="signupPhone">Numéro de téléphone</label>
            <input id="signupPhone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
          </div>
          <button className="btn btn-primary btn-block" type="submit">
            Continuer
          </button>
        </form>
      )}

      {mode === "signup" && signupStep === "create-pin" && (
        <div className="screen" style={{ padding: 0, gap: 16 }}>
          <p className="summary">Choisissez un mot de passe à 4 chiffres. La disposition change à chaque affichage.</p>
          <RandomizedPinPad value={pin} onChange={handleSignupPinCreate} shuffleSeed={shuffleSeed} />
          <button type="button" className="link-button" onClick={() => setSignupStep("identity")}>
            Revenir aux informations du compte
          </button>
        </div>
      )}

      {mode === "signup" && signupStep === "confirm-pin" && (
        <div className="screen" style={{ padding: 0, gap: 16 }}>
          <p className="summary">Confirmez votre mot de passe à 4 chiffres.</p>
          <RandomizedPinPad value={confirmPin} onChange={handleSignupPinConfirm} shuffleSeed={shuffleSeed} />
          {submitting && <p className="summary">Création du compte en cours...</p>}
          <button type="button" className="link-button" onClick={() => { setPin(""); setConfirmPin(""); setSignupStep("create-pin"); }}>
            Recommencer la saisie
          </button>
        </div>
      )}
    </div>
  );
}
