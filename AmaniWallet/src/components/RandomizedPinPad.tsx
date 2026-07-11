import { useMemo } from "react";
import { Delete } from "lucide-react";

interface RandomizedPinPadProps {
  value: string;
  onChange: (value: string) => void;
  length?: number;
  /** Change cette valeur pour forcer un nouveau mélange (ex: après une erreur). */
  shuffleSeed?: number;
}

function shuffledDigits(seed: number): string[] {
  const digits = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  // Mélange de Fisher-Yates — la disposition change à chaque affichage de la grille,
  // pour limiter les risques d'observation par-dessus l'épaule (shoulder surfing).
  let random = seed;
  const next = () => {
    random = (random * 9301 + 49297) % 233280;
    return random / 233280;
  };
  for (let i = digits.length - 1; i > 0; i -= 1) {
    const j = Math.floor(next() * (i + 1));
    [digits[i], digits[j]] = [digits[j], digits[i]];
  }
  return digits;
}

export function RandomizedPinPad({ value, onChange, length = 4, shuffleSeed = 0 }: RandomizedPinPadProps) {
  const digits = useMemo(
    () => shuffledDigits(Date.now() % 100000 + shuffleSeed),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [shuffleSeed],
  );

  const handleDigit = (digit: string) => {
    if (value.length >= length) return;
    onChange(value + digit);
  };

  const handleBackspace = () => onChange(value.slice(0, -1));
  const handleClear = () => onChange("");

  return (
    <div>
      <div className="pin-dots" aria-label={`${value.length} sur ${length} chiffres saisis`}>
        {Array.from({ length }).map((_, i) => (
          <span key={i} className={i < value.length ? "filled" : ""} />
        ))}
      </div>
      <div className="pin-grid">
        {digits.slice(0, 9).map((digit) => (
          <button key={digit} type="button" className="pin-key" onClick={() => handleDigit(digit)}>
            {digit}
          </button>
        ))}
        <button type="button" className="pin-key pin-key-utility" onClick={handleClear}>
          Effacer
        </button>
        <button type="button" className="pin-key" onClick={() => handleDigit(digits[9])}>
          {digits[9]}
        </button>
        <button type="button" className="pin-key pin-key-utility" onClick={handleBackspace} aria-label="Supprimer le dernier chiffre">
          <Delete size={18} />
        </button>
      </div>
    </div>
  );
}
