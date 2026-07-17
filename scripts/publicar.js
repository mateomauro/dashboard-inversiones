#!/usr/bin/env node
/**
 * Encripta data/inversiones.json con una contraseña y guarda el resultado en
 * data/inversiones.enc.json — ese SI se puede subir a internet (GitHub Pages),
 * porque sin la contraseña es ilegible.
 *
 * Usa el mismo Web Crypto (AES-GCM + PBKDF2) que el navegador, para que
 * dashboard.html pueda desencriptarlo despues con la misma contraseña.
 *
 * Uso:
 *   node scripts/publicar.js
 *   (pide la contraseña por consola, no la escribas en ningun script)
 */
const fs = require("fs");
const path = require("path");
const readline = require("readline");
const { webcrypto } = require("crypto");

const ROOT = path.join(__dirname, "..");
const SRC = path.join(ROOT, "data", "inversiones.json");
const OUT = path.join(ROOT, "data", "inversiones.enc.json");
const ITERATIONS = 210000;

function toB64(buf) { return Buffer.from(buf).toString("base64"); }

async function deriveKey(password, salt) {
  const enc = new TextEncoder();
  const keyMaterial = await webcrypto.subtle.importKey(
    "raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]
  );
  return webcrypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt"]
  );
}

function preguntarPassword() {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question("Contraseña para encriptar (no la compartas): ", (pass) => {
      rl.close();
      resolve(pass);
    });
  });
}

async function main() {
  if (!fs.existsSync(SRC)) {
    console.error("No existe " + SRC);
    process.exit(1);
  }
  const password = await preguntarPassword();
  if (!password || password.length < 6) {
    console.error("Usá una contraseña de al menos 6 caracteres.");
    process.exit(1);
  }
  const plaintext = fs.readFileSync(SRC, "utf-8");
  const salt = webcrypto.getRandomValues(new Uint8Array(16));
  const iv = webcrypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(password, salt);
  const ciphertext = await webcrypto.subtle.encrypt(
    { name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext)
  );
  const out = {
    v: 1,
    iterations: ITERATIONS,
    salt: toB64(salt),
    iv: toB64(iv),
    ciphertext: toB64(ciphertext),
    updated: new Date().toISOString(),
  };
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf-8");
  console.log("Listo: " + OUT);
  console.log("Ese archivo SI se puede subir a internet — sin la contraseña es ilegible.");
}

main();
