// Mode démonstration (cahier des charges, section 10) — accessible uniquement via 5 clics
// sur le logo de l'écran de démarrage. Tant qu'aucun scénario n'est choisi, le comportement
// par défaut est celui de NORMAL_USER (appareil de confiance déjà seedé côté backend).
import type { DemoScenario, DemoSignals, LocationInfo } from "../types";

// Doit rester identique à Backend/scripts/seed_wallet_demo.py (TRUSTED_DEVICE) : le
// fingerprint dépend de TOUS ces champs, pas seulement de l'UUID — sur un poste de test
// desktop, on doit pouvoir se faire passer pour le téléphone habituel du client démo.
export const TRUSTED_DEVICE_PROFILE = {
  localDeviceUuid: "demo-trusted-device-0001",
  platform: "Android",
  osVersion: "14",
  browser: "Chrome Mobile",
  screenWidth: 412,
  screenHeight: 915,
  language: "fr-FR",
  timezone: "Africa/Abidjan",
};

export function usesTrustedDevice(scenario: DemoScenario | null): boolean {
  if (!scenario) return true;
  return scenario.mock_signals.use_trusted_device !== false;
}

export function resolveDeviceOverrides(scenario: DemoScenario | null) {
  const sensorsValue = scenario?.mock_signals.sensors_available;
  const sensorsAvailable = typeof sensorsValue === "boolean" ? sensorsValue : undefined;

  if (usesTrustedDevice(scenario)) {
    return { ...TRUSTED_DEVICE_PROFILE, sensorsAvailable };
  }
  return {
    localDeviceUuid: `demo-${scenario!.name.toLowerCase()}-${crypto.randomUUID().slice(0, 8)}`,
    sensorsAvailable,
  };
}

export async function resolveLocation(scenario: DemoScenario | null): Promise<LocationInfo> {
  const override = scenario?.mock_signals.location as { latitude: number; longitude: number } | undefined;
  if (override) {
    return { latitude: override.latitude, longitude: override.longitude, accuracy: 50, permission_granted: true };
  }
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve({ latitude: null, longitude: null, accuracy: null, permission_granted: false });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          permission_granted: true,
        }),
      () => resolve({ latitude: null, longitude: null, accuracy: null, permission_granted: false }),
      { timeout: 5000 },
    );
  });
}

export function toDemoSignalsPayload(scenario: DemoScenario | null): DemoSignals {
  if (!scenario) return { scenario: "NORMAL_USER" };
  const m = scenario.mock_signals;
  return {
    scenario: scenario.name,
    android_id_mock: (m.android_id_mock as string | null) ?? null,
    device_integrity_mock: (m.device_integrity_mock as string) ?? "PASSED",
    emulator_detected_mock: Boolean(m.emulator_detected_mock),
    root_detected_mock: Boolean(m.root_detected_mock),
    sim_changed_recently_mock: Boolean(m.sim_changed_recently_mock),
    esim_activated_recently_mock: Boolean(m.esim_activated_recently_mock),
    sim_age_hours_mock: (m.sim_age_hours_mock as number | null) ?? null,
  };
}

export function suggestedIdentityResult(scenario: DemoScenario | null): {
  biometric?: string;
  liveness?: string;
} {
  if (!scenario) return {};
  const m = scenario.mock_signals;
  return {
    biometric: (m.biometric_result_mock as string | undefined) ?? undefined,
    liveness: (m.liveness_result_mock as string | undefined) ?? undefined,
  };
}
