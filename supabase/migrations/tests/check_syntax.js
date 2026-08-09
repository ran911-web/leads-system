#!/usr/bin/env node
/**
 * בדיקת תחביר JavaScript ותקינות מבנה HTML — ללא דפדפן, ללא רשת.
 * הרצה:  npm run test:syntax
 *        node tests/check_syntax.js [path/to/index.html]
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const file = process.argv[2] || path.join(__dirname, '..', 'index.html');
if (!fs.existsSync(file)) { console.error('❌ לא נמצא הקובץ: ' + file); process.exit(1); }
const html = fs.readFileSync(file, 'utf8');

let failures = 0;
const ok = (name, cond, extra) => {
  console.log((cond ? '  ✅ ' : '  ❌ ') + name + (cond ? '' : '  ' + (extra || '')));
  if (!cond) failures++;
};

// ── 1. תחביר JavaScript בכל בלוקי הסקריפט הפנימיים ──
const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
ok('נמצאו בלוקי script', scripts.length > 0, '(' + scripts.length + ')');
let syntaxOk = true, syntaxErr = '';
scripts.forEach((s, i) => {
  if (!s.trim()) return;
  try { new vm.Script(s); }
  catch (e) { syntaxOk = false; syntaxErr = 'block #' + i + ': ' + e.message; }
});
ok('תחביר JavaScript תקין', syntaxOk, syntaxErr);

const main = scripts.reduce((a, b) => (b.length > a.length ? b : a), '');

// ── 2. איזון סוגריים ו-backticks ──
let depth = 0;
for (const ch of main) { if (ch === '{') depth++; else if (ch === '}') depth--; }
ok('סוגריים מסולסלים מאוזנים', depth === 0, '(depth=' + depth + ')');
ok('backticks זוגיים', (main.split('`').length - 1) % 2 === 0);

// ── 3. מזהי HTML ──
const body = html
  .replace(/<script[\s\S]*?<\/script>/g, '')
  .replace(/<style[\s\S]*?<\/style>/g, '');
const ids = [...body.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
const dupIds = [...new Set(ids.filter((v, i) => ids.indexOf(v) !== i))];
ok('אין מזהי HTML כפולים', dupIds.length === 0, JSON.stringify(dupIds));

// ── 4. הגדרות פונקציה כפולות ──
const fns = [...main.matchAll(/\n\s*(?:async\s+)?function\s+(\w+)\s*\(/g)].map(m => m[1]);
const dupFns = [...new Set(fns.filter((v, i) => fns.indexOf(v) !== i))];
ok('אין הגדרות פונקציה כפולות', dupFns.length === 0, JSON.stringify(dupFns));

// ── 5. תגי div מאוזנים ──
const opens = (body.match(/<div\b/g) || []).length;
const closes = (body.match(/<\/div>/g) || []).length;
ok('תגי div מאוזנים', opens === closes, '(' + opens + ' פתיחות / ' + closes + ' סגירות)');

// ── 6. אין סודות ──
ok('אין service_role בקוד', !/service_role/.test(html));

console.log('\n' + '='.repeat(48));
if (failures) { console.log('❌ נכשלו ' + failures + ' בדיקות'); process.exit(1); }
console.log('✅ כל בדיקות התחביר והמבנה עברו');
