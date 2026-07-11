export type PresetKey = "normal" | "suspect" | "critique";

interface PresetSelectorProps {
  value: PresetKey;
  onChange: (preset: PresetKey) => void;
}

const presets: Array<{ key: PresetKey; label: string }> = [
  { key: "normal", label: "Normal" },
  { key: "suspect", label: "Suspect" },
  { key: "critique", label: "Critique" },
];

export function PresetSelector({ value, onChange }: PresetSelectorProps) {
  return (
    <div className="scenario-selector" aria-label="Préremplir avec un profil de test">
      {presets.map((preset) => (
        <button
          type="button"
          key={preset.key}
          className={preset.key === value ? "is-active" : ""}
          onClick={() => onChange(preset.key)}
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}
