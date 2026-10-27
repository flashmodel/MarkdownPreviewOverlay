#!/usr/bin/env node
/**
 * Typeset a batch of TeX formulas to PNG.
 *
 * stdin:  {"color":"#RRGGBB","scale":2,"items":[{"tex":"...","display":true}]}
 * stdout: for each item, 4-byte big-endian status (0 png, 1 error),
 *         4-byte big-endian payload length, then the payload.
 *
 * argv[2] is a node_modules directory that contains mathjax and @resvg/resvg-js.
 * Nothing else is written to stdout. Fatal errors go to stderr and exit 1.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const {createRequire} = require('module');

const FONT_CANDIDATES = [
  ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'DejaVu Sans'],
  ['/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 'Liberation Sans'],
  ['/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf', 'Liberation Sans'],
  ['/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf', 'Noto Sans'],
  ['/usr/share/fonts/noto/NotoSans-Regular.ttf', 'Noto Sans'],
  ['/Library/Fonts/Arial.ttf', 'Arial'],
  ['/System/Library/Fonts/Supplemental/Arial.ttf', 'Arial'],
  ['/Library/Fonts/Arial Unicode.ttf', 'Arial Unicode MS'],
  ['C:/Windows/Fonts/arial.ttf', 'Arial'],
  ['C:/Windows/Fonts/segoeui.ttf', 'Segoe UI'],
];

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on('data', (chunk) => chunks.push(chunk));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks)));
    process.stdin.on('error', reject);
  });
}

function chooseFont() {
  for (const [file, family] of FONT_CANDIDATES) {
    if (fs.existsSync(file)) {
      return {file, family};
    }
  }
  return {file: null, family: 'DejaVu Sans'};
}

function normalizeColor(value) {
  const text = String(value || '').trim();
  if (/^#[0-9A-Fa-f]{6}$/.test(text)) {
    return text;
  }
  if (/^#[0-9A-Fa-f]{8}$/.test(text)) {
    return text.slice(0, 7);
  }
  if (/^#[0-9A-Fa-f]{3}$/.test(text)) {
    return '#' + text.slice(1).split('').map((ch) => ch + ch).join('');
  }
  return '#000000';
}

function escapeAttr(value) {
  return String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function paint(svg, color) {
  let next = svg.replace(/currentColor/g, color);
  if (/<svg\b[^>]*\sstyle="/i.test(next)) {
    next = next.replace(/(<svg\b[^>]*\sstyle=")/i, '$1color:' + color + ';');
  } else {
    next = next.replace(/<svg\b/i, '<svg style="color:' + color + '"');
  }
  return next;
}

function applyTextFont(svg, family) {
  if (!family) {
    return svg;
  }
  const attr = 'font-family="' + escapeAttr(family) + '"';
  return svg.replace(/<text\b([^>]*)>/gi, (match, attrs) => {
    if (/font-family="/i.test(attrs)) {
      return '<text' + attrs.replace(/font-family="[^"]*"/i, attr) + '>';
    }
    return '<text ' + attr + attrs + '>';
  });
}

function extractSvg(serialized) {
  const start = serialized.indexOf('<svg');
  const end = serialized.lastIndexOf('</svg>');
  if (start < 0 || end < 0) {
    throw new Error('MathJax did not return an SVG');
  }
  return serialized.slice(start, end + '</svg>'.length);
}

function serialize(node) {
  const adaptor = MathJax.startup && MathJax.startup.adaptor;
  if (!adaptor) {
    throw new Error('MathJax adaptor is unavailable');
  }
  if (typeof adaptor.serializeXML === 'function') {
    return adaptor.serializeXML(node);
  }
  if (typeof adaptor.outerHTML === 'function') {
    return adaptor.outerHTML(node);
  }
  throw new Error('MathJax adaptor cannot serialize SVG');
}

function loadRuntime(modulesDir) {
  const mathjaxPkg = path.join(modulesDir, 'mathjax', 'package.json');
  const resvgPkg = path.join(modulesDir, '@resvg', 'resvg-js', 'package.json');
  if (!fs.existsSync(mathjaxPkg) || !fs.existsSync(resvgPkg)) {
    throw new Error('mathjax and @resvg/resvg-js must both be installed in ' + modulesDir);
  }
  const req = createRequire(mathjaxPkg);
  return {
    MathJax: req('mathjax'),
    Resvg: req('@resvg/resvg-js').Resvg,
  };
}

function mathJaxConfig(family) {
  return {
    loader: {load: ['input/tex', 'output/svg']},
    startup: {typeset: false},
    // Glyphs outside the math font are already emitted as SVG <text>.
    // unknownFamily pins that text to a font resvg can load.
    // MathJax 4 line-breaks inline math by default. With no page width that
    // splits one formula into several <svg> tags, which resvg cannot draw.
    output: {
      unknownFamily: family || 'sans-serif',
      displayOverflow: 'overflow',
      linebreaks: {inline: false},
    },
    svg: {
      fontCache: 'none',
      displayOverflow: 'overflow',
      linebreaks: {inline: false},
    },
    tex: {
      packages: {'[+]': ['ams'], '[-]': ['noundefined']},
      formatError: (jax, error) => {
        throw error;
      },
    },
  };
}

let MathJax = null;
let Resvg = null;
let mathJaxReady = null;

function initMathJax(family) {
  if (mathJaxReady) {
    return mathJaxReady;
  }
  const ready = MathJax.init(mathJaxConfig(family));
  mathJaxReady = ready && typeof ready.then === 'function' ? ready : Promise.resolve();
  return mathJaxReady;
}

async function typesetSvg(tex, display, color, font) {
  const options = {display: Boolean(display)};
  const node = typeof MathJax.tex2svgPromise === 'function'
    ? await MathJax.tex2svgPromise(tex, options)
    : MathJax.tex2svg(tex, options);
  let svg = extractSvg(serialize(node));
  if (/data-mjx-error/.test(svg)) {
    throw new Error('TeX error');
  }
  // MathJax draws unknown glyphs as <text>. Pin those nodes to the system font
  // resvg was given, so letters outside the math font (for example š and ć
  // when they are not in the font, or other scripts) still rasterize.
  return applyTextFont(paint(svg, color), font.family);
}

function rasterize(svg, scale, font) {
  const fontOptions = {
    loadSystemFonts: true,
    defaultFontFamily: font.family || 'sans-serif',
    sansSerifFamily: font.family || 'sans-serif',
  };
  if (font.file) {
    fontOptions.fontFiles = [font.file];
  }
  const renderer = new Resvg(svg, {
    fitTo: {mode: 'zoom', value: scale},
    background: 'rgba(0,0,0,0)',
    font: fontOptions,
  });
  const png = Buffer.from(renderer.render().asPng());
  if (png.length < 24 || png.slice(0, 8).toString('binary') !== '\x89PNG\r\n\x1a\n') {
    throw new Error('resvg did not return a PNG');
  }
  return png;
}

async function renderItem(tex, display, color, scale, font) {
  const source = String(tex || '').trim();
  if (!source) {
    throw new Error('empty formula');
  }
  await initMathJax(font.family);
  const svg = await typesetSvg(source, display, color, font);
  return rasterize(svg, scale, font);
}

function writeFrames(frames) {
  const parts = frames.map((frame) => {
    const header = Buffer.alloc(8);
    header.writeUInt32BE(frame.status, 0);
    header.writeUInt32BE(frame.payload.length, 4);
    return Buffer.concat([header, frame.payload]);
  });
  const output = Buffer.concat(parts);
  process.stdout.write(output, () => process.exit(0));
}

async function main() {
  console.log = console.error;
  const modulesDir = process.argv[2];
  if (!modulesDir) {
    console.error('missing node_modules directory');
    process.exit(1);
  }
  const runtime = loadRuntime(modulesDir);
  MathJax = runtime.MathJax;
  Resvg = runtime.Resvg;

  const raw = await readStdin();
  let payload;
  try {
    payload = JSON.parse(raw.toString('utf8') || '{}');
  } catch (error) {
    console.error('invalid math request');
    process.exit(1);
  }
  const items = Array.isArray(payload.items) ? payload.items : [];
  const color = normalizeColor(payload.color);
  const scale = Number(payload.scale) > 0 ? Number(payload.scale) : 2;
  const font = chooseFont();
  const frames = [];
  for (const item of items) {
    try {
      const png = await renderItem(item.tex, item.display, color, scale, font);
      frames.push({status: 0, payload: png});
    } catch (error) {
      const message = String(error && error.message ? error.message : error);
      frames.push({status: 1, payload: Buffer.from(message, 'utf8')});
    }
  }
  writeFrames(frames);
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
