#!/usr/bin/env node
/**
 * Arma la carpeta site/ (dashboard.html + data/inversiones.enc.json + precios/dolar
 * sin encriptar, porque son datos de mercado, no personales — nunca los datos reales)
 * y la sube a Netlify.
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
const PUBLIC_MARKET_FILES = ["precios_historicos.json", "dolar_historico.json", "fondos_historico.json"];

function main() {
  if (!fs.existsSync(ENC)) {
    console.error("No existe data/inversiones.enc.json — corre primero: node scripts/publicar.js");
    process.exit(1);
  }
  fs.mkdirSync(path.join(SITE, "data"), { recursive: true });
  fs.copyFileSync(path.join(ROOT, "dashboard.html"), path.join(SITE, "dashboard.html"));
  fs.copyFileSync(ENC, path.join(SITE, "data", "inversiones.enc.json"));
  for (const name of PUBLIC_MARKET_FILES) {
    const src = path.join(ROOT, "data", name);
    if (fs.existsSync(src)) fs.copyFileSync(src, path.join(SITE, "data", name));
  }
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
