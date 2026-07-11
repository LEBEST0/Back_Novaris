// Identifiant applicatif local — jamais présenté comme un Android ID / IMEI réel.
// Génération et empreinte documentées dans Backend/scripts/seed_wallet_demo.py (même
// algorithme des deux côtés, pour que le mode démo « appareil de confiance » corresponde).
import type { DeviceInfo } from "../types";

const STORAGE_KEY = "amani_local_device_uuid";

export function getOrCreateLocalDeviceUuid(): string {
  const existing = localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;
  const fresh = crypto.randomUUID();
  localStorage.setItem(STORAGE_KEY, fresh);
  return fresh;
}

export function setLocalDeviceUuid(value: string) {
  localStorage.setItem(STORAGE_KEY, value);
}

function detectPlatform(): string {
  const ua = navigator.userAgent;
  if (/android/i.test(ua)) return "Android";
  if (/iphone|ipad|ipod/i.test(ua)) return "iOS";
  if (/windows/i.test(ua)) return "Windows";
  if (/mac os/i.test(ua)) return "macOS";
  if (/linux/i.test(ua)) return "Linux";
  return "unknown";
}

function detectOsVersion(): string {
  const ua = navigator.userAgent;
  const androidMatch = ua.match(/android (\d+(\.\d+)?)/i);
  if (androidMatch) return androidMatch[1];
  const iosMatch = ua.match(/os (\d+_\d+)/i);
  if (iosMatch) return iosMatch[1].replace("_", ".");
  return "apparente-inconnue";
}

function detectBrowser(): string {
  const ua = navigator.userAgent;
  if (/edg\//i.test(ua)) return "Edge";
  if (/chrome\//i.test(ua) && /mobile/i.test(ua)) return "Chrome Mobile";
  if (/chrome\//i.test(ua)) return "Chrome";
  if (/firefox\//i.test(ua)) return "Firefox";
  if (/safari\//i.test(ua) && !/chrome/i.test(ua)) return "Safari";
  return "navigateur inconnu";
}

export async function isBiometricAvailable(): Promise<boolean> {
  try {
    if (!window.PublicKeyCredential) return false;
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

async function sha256Hex(input: string): Promise<string> {
  const encoded = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// Empreinte applicative — pas une preuve matérielle absolue (cf. cahier des charges,
// section 8). Un même appareil physique peut changer de fingerprint (nouveau navigateur,
// données locales effacées) : c'est un signal parmi d'autres, pas une identité garantie.
export async function computeDeviceFingerprint(parts: {
  localDeviceUuid: string;
  platform: string;
  osVersion: string;
  screenSize: string;
  language: string;
  timezone: string;
}): Promise<string> {
  const raw = [parts.localDeviceUuid, parts.platform, parts.osVersion, parts.screenSize, parts.language, parts.timezone].join("|");
  return sha256Hex(raw);
}

interface DeviceInfoOverrides {
  localDeviceUuid: string;
  sensorsAvailable: boolean;
  // Empreinte complète (utilisé par le mode démo « appareil de confiance ») : le fingerprint
  // dépend de TOUS ces champs, pas seulement de local_device_uuid — un desktop de test doit
  // pouvoir se faire passer pour le téléphone habituel du client de démonstration.
  platform: string;
  osVersion: string;
  browser: string;
  screenWidth: number;
  screenHeight: number;
  language: string;
  timezone: string;
}

export async function buildDeviceInfo(overrides?: Partial<DeviceInfoOverrides>): Promise<DeviceInfo> {
  const localDeviceUuid = overrides?.localDeviceUuid ?? getOrCreateLocalDeviceUuid();
  const platform = overrides?.platform ?? detectPlatform();
  const osVersion = overrides?.osVersion ?? detectOsVersion();
  const browser = overrides?.browser ?? detectBrowser();
  const screenWidth = overrides?.screenWidth ?? window.screen.width;
  const screenHeight = overrides?.screenHeight ?? window.screen.height;
  const screenSize = `${screenWidth}x${screenHeight}`;
  const language = overrides?.language ?? navigator.language ?? "fr-FR";
  const timezone = overrides?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "Africa/Abidjan";

  const fingerprint = await computeDeviceFingerprint({
    localDeviceUuid,
    platform,
    osVersion,
    screenSize,
    language,
    timezone,
  });

  const sensorsAvailable = overrides?.sensorsAvailable ?? (await isBiometricAvailable());

  return {
    local_device_uuid: localDeviceUuid,
    device_fingerprint: fingerprint,
    platform,
    os_version: osVersion,
    browser,
    screen_width: screenWidth,
    screen_height: screenHeight,
    language,
    timezone,
    sensors_available: sensorsAvailable,
  };
}
