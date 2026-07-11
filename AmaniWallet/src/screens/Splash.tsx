import { useEffect, useRef, useState } from "react";
import { logAccessEvent } from "../lib/api";

interface SplashProps {
  onDone: () => void;
  onOpenDemoMode: () => void;
}

export function Splash({ onDone, onOpenDemoMode }: SplashProps) {
  const [clickCount, setClickCount] = useState(0);
  const clickTimer = useRef<number | null>(null);

  useEffect(() => {
    logAccessEvent("APP_OPENED").catch(() => {
      // La journalisation d'ouverture n'est pas bloquante : l'app continue même hors ligne.
    });
    const timer = window.setTimeout(onDone, 1900);
    return () => window.clearTimeout(timer);
  }, [onDone]);

  const handleLogoClick = () => {
    setClickCount((count) => {
      const next = count + 1;
      if (clickTimer.current) window.clearTimeout(clickTimer.current);
      if (next >= 5) {
        onOpenDemoMode();
        return 0;
      }
      clickTimer.current = window.setTimeout(() => setClickCount(0), 1500);
      return next;
    });
  };

  return (
    <div className="splash">
      <svg
        className="splash-logo"
        viewBox="0 0 512 512"
        role="img"
        aria-label="Amani Wallet"
        onClick={handleLogoClick}
      >
        <rect width="512" height="512" rx="112" fill="#ffffff" opacity="0.06" />
        <path
          d="M256 128 L372 192 V292 C372 356 320 398 256 418 C192 398 140 356 140 292 V192 Z"
          fill="none"
          stroke="#F5A623"
          strokeWidth="14"
        />
        <path
          d="M212 292 L244 328 L308 224"
          fill="none"
          stroke="#FFFFFF"
          strokeWidth="22"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <h1>Amani Wallet</h1>
      <p className="slogan">Votre argent, votre confiance</p>
      <div className="status-line">
        <span className="spinner" aria-hidden="true" />
        Vérification de votre environnement sécurisé
      </div>
    </div>
  );
}
