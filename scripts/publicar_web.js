#!/usr/bin/env node
/**
 * Arma la carpeta site/ (solo dashboard.html + data/inversiones.enc.json,
 * nunca los datos reales) y la sube a Netlify.
 *
 * Uso:
 *   node scripts/publicar.js       (primero, para generar/actualizar el .enc.json)
 *   node scripts/publicar_web.js   (despues, para subir lo nuevo a internet)
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const SITE = path.join(ROOT, "site");
const ENC = path.join(ROOT, "data", "inversiones.enc.json");

function main() {
  if (!fs.existsSync(ENC)) {
    console.error("No existe data/inversiones.enc.json — corre primero: node scripts/publicar.js");
    process.exit(1);
  }
  fs.mkdirSync(path.join(SITE, "data"), { recursive: true });
  fs.copyFileSync(path.join(ROOT, "dashboard.html"), path.join(SITE, "dashboard.html"));
  fs.copyFileSync(ENC, path.join(SITE, "data", "inversiones.enc.json"));
  fs.writeFileSync(
    path.join(SITE, "index.html"),
    '<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url=dashboard.html"></head><body>Redirigiendo...</body></html>'
  );
  console.log("Carpeta site/ actualizada. Subiendo a Netlify...");
  execFileSync("npx", ["--yes", "netlify", "deploy", "--prod", "--dir=site"], {
    cwd: ROOT,
    stdio: "inherit",
    shell: true,
  });
}

main();
