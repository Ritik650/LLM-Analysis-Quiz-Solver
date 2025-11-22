export async function sha1(message) {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest("SHA-1", msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function getEmail() {
  const urlParams = new URLSearchParams(globalThis.location.search.replace(/^\?/, ""));
  return urlParams.get("email");
}

export async function emailNumber(email) {
  email = email || getEmail();
  if (!email) return null;
  return (parseInt((await sha1(email)).slice(0, 4), 16));
}

export const demo2Blob = "8b1f4c3a2d";

export async function demo2Key(email) {
  const base = await emailNumber(email);
  if (base == null) return null;
  const keyNumber = (base * 7919 + 12345) % 100000000;
  return String(keyNumber).padStart(8, "0");
}
