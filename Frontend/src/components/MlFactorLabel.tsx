import { ArrowDownCircle, ArrowUpCircle } from "lucide-react";

const UP_MARKER = "fait monter le risque";
const DOWN_MARKER = "fait baisser le risque";

/** Un facteur ML/SHAP est un texte du type "Bénéficiaire non habituel (fait baisser le
 * risque)". On détecte la formule pour l'afficher avec une flèche + une couleur plutôt
 * qu'un texte brut — plus rapide à scanner pour un analyste, et sans jargon "impact +/-"
 * qui n'était pas compris tel quel. Les raisons qui viennent d'une règle (pas du ML)
 * n'ont pas ce marqueur et s'affichent simplement en texte. */
export function MlFactorLabel({ factor }: { factor: string }) {
  const isUp = factor.includes(`(${UP_MARKER})`);
  const isDown = factor.includes(`(${DOWN_MARKER})`);

  if (!isUp && !isDown) {
    return <>{factor}</>;
  }

  const label = factor.replace(` (${UP_MARKER})`, "").replace(` (${DOWN_MARKER})`, "");
  const Icon = isUp ? ArrowUpCircle : ArrowDownCircle;

  return (
    <span className="ml-factor">
      {label}
      <span className={`ml-factor-direction ${isUp ? "ml-factor-up" : "ml-factor-down"}`}>
        <Icon size={13} aria-hidden="true" />
        {isUp ? "augmente le risque" : "réduit le risque"}
      </span>
    </span>
  );
}
