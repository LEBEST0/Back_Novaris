import { useEffect, useState } from "react";
import { AlertTriangle, Ban, Fingerprint, ScanFace, ShieldQuestion } from "lucide-react";
import { evaluateAccess } from "../lib/api";
import { suggestedIdentityResult } from "../lib/demo";
import type { DemoScenario, EvaluateAccessResult } from "../types";

interface SecurityVerificationProps {
  result: EvaluateAccessResult;
  demoScenario: DemoScenario | null;
  onResolved: (result: EvaluateAccessResult) => void;
  onBackToLogin: () => void;
}

export function SecurityVerification({ result, demoScenario, onResolved, onBackToLogin }: SecurityVerificationProps) {
  const [otp, setOtp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoStage, setAutoStage] = useState<"idle" | "scanning">("idle");

  const suggestion = suggestedIdentityResult(demoScenario);
  const action = result.next_action;

  const submitChallenge = async (challenge: Record<string, unknown>) => {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await evaluateAccess(result.session_id, challenge);
      onResolved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Le service de vérification est momentanément indisponible.");
    } finally {
      setSubmitting(false);
      setAutoStage("idle");
    }
  };

  // Rejoue automatiquement le résultat suggéré par le scénario démo actif, pour ne pas
  // obliger le présentateur à cliquer manuellement à chaque étape.
  useEffect(() => {
    if (action === "REQUIRE_BIOMETRIC" && suggestion.biometric) {
      setAutoStage("scanning");
      const t = window.setTimeout(() => submitChallenge({ biometric_result: suggestion.biometric }), 1400);
      return () => window.clearTimeout(t);
    }
    if (action === "REQUIRE_LIVENESS" && suggestion.liveness) {
      setAutoStage("scanning");
      const t = window.setTimeout(() => submitChallenge({ liveness_result: suggestion.liveness }), 1400);
      return () => window.clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action]);

  const handleOtpSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    submitChallenge({ otp_code: otp });
  };

  const isTerminalBlock = action === "TEMPORARY_BLOCK" || action === "BLOCK";
  const isCritical = action === "BLOCK";

  return (
    <div className="screen no-nav">
      <div className="topbar">
        <div>
          <p className="eyebrow">Novaris AI</p>
          <h1>Vérification de sécurité</h1>
        </div>
      </div>

      <div className={`verify-hero ${isCritical ? "critical" : ""}`}>
        <span className="icon-badge" aria-hidden="true">
          {action === "REQUIRE_OTP" || action === "REQUIRE_STEP_UP" ? <ShieldQuestion size={30} /> : null}
          {action === "REQUIRE_BIOMETRIC" ? <Fingerprint size={30} /> : null}
          {action === "REQUIRE_LIVENESS" ? <ScanFace size={30} /> : null}
          {action === "TEMPORARY_BLOCK" ? <AlertTriangle size={30} /> : null}
          {action === "BLOCK" ? <Ban size={30} /> : null}
        </span>
        <p className="summary">{result.user_message}</p>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {(action === "REQUIRE_OTP" || action === "REQUIRE_STEP_UP") && (
        <form className="field" onSubmit={handleOtpSubmit} style={{ gap: 14 }}>
          <label htmlFor="otp">Code de vérification (6 chiffres)</label>
          <input
            id="otp"
            inputMode="numeric"
            maxLength={6}
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
            style={{ textAlign: "center", letterSpacing: "6px", fontSize: 20 }}
            required
          />
          <p className="summary">Code de démonstration : 123456</p>
          <button className="btn btn-primary btn-block" type="submit" disabled={submitting || otp.length < 4}>
            {submitting ? "Vérification..." : "Vérifier"}
          </button>
        </form>
      )}

      {action === "REQUIRE_BIOMETRIC" && (
        <div className="field" style={{ gap: 14, textAlign: "center" }}>
          {autoStage === "scanning" ? (
            <p className="summary">Analyse biométrique en cours…</p>
          ) : (
            <>
              <p className="summary">Confirmez avec votre empreinte digitale ou Face ID.</p>
              <button className="btn btn-primary btn-block" disabled={submitting} onClick={() => submitChallenge({ biometric_result: "PASSED" })}>
                Simuler une empreinte valide
              </button>
              <button className="btn btn-secondary btn-block" disabled={submitting} onClick={() => submitChallenge({ biometric_result: "FAILED" })}>
                Simuler un échec
              </button>
            </>
          )}
        </div>
      )}

      {action === "REQUIRE_LIVENESS" && (
        <div className="field" style={{ gap: 14, textAlign: "center" }}>
          {autoStage === "scanning" ? (
            <p className="summary">Vérification de vivacité en cours…</p>
          ) : (
            <>
              <p className="summary">Capteurs biométriques indisponibles : vérifiez votre identité par liveness ou pièce d'identité.</p>
              <button className="btn btn-primary btn-block" disabled={submitting} onClick={() => submitChallenge({ liveness_result: "PASSED" })}>
                Simuler la vérification de vivacité
              </button>
              <button className="btn btn-secondary btn-block" disabled={submitting} onClick={() => submitChallenge({ liveness_result: "PASSED", cni_provided: true })}>
                Fournir ma pièce d'identité
              </button>
              <button className="btn btn-secondary btn-block" disabled={submitting} onClick={() => submitChallenge({ liveness_result: "FAILED" })}>
                Simuler un échec
              </button>
            </>
          )}
        </div>
      )}

      {isTerminalBlock && (
        <div className="field" style={{ gap: 14 }}>
          <button className="btn btn-secondary btn-block" onClick={onBackToLogin}>
            Retour à la connexion
          </button>
        </div>
      )}
    </div>
  );
}
