#!/usr/bin/env node
// check-cross-links.js — validates doc-to-doc links and finds orphaned docs (pre-push / CI)
'use strict';

const fs = require('fs');
const path = require('path');

const LINK_PATTERN = /\[([^\]]+)\]\(([^)]+)\)/g;

function walkMd(dir, ignore, repoRoot) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (ignore.some(ig => path.relative(repoRoot, full).startsWith(ig))) continue;
    if (entry.isDirectory()) {
      results.push(...walkMd(full, ignore, repoRoot));
    } else if (entry.name.endsWith('.md')) {
      results.push(full);
    }
  }
  return results;
}

function extractLinks(content, fromFile, repoRoot) {
  const links = [];
  let match;
  const re = new RegExp(LINK_PATTERN.source, 'g');
  while ((match = re.exec(content)) !== null) {
    const href = match[2].split('#')[0];
    if (!href || href.startsWith('http') || href.startsWith('mailto:')) continue;
    const resolved = path.resolve(path.dirname(fromFile), href);
    links.push({ text: match[1], href, resolved });
  }
  return links;
}

function checkCrossLinks(repoRoot, config) {
  const results = [];
  const ignore = config.ignore_paths || ['node_modules', '.git', 'dist', 'build'];

  // Collect all MD files in docs/ and root
  const docsDir = path.join(repoRoot, 'docs');
  const allDocFiles = walkMd(docsDir, ignore, repoRoot);
  const rootMds = ['CLAUDE.md', 'ARCHITECTURE.md'].map(f => path.join(repoRoot, f)).filter(f => fs.existsSync(f));
  const allFiles = [...rootMds, ...allDocFiles];

  // Build set of all known doc paths
  const knownPaths = new Set(allFiles.map(f => path.resolve(f)));

  // Build reachability graph from CLAUDE.md
  const claudeMd = path.join(repoRoot, 'CLAUDE.md');
  const reachable = new Set();
  if (fs.existsSync(claudeMd)) {
    reachable.add(path.resolve(claudeMd));
    const queue = [claudeMd];
    while (queue.length > 0) {
      const current = queue.shift();
      if (!fs.existsSync(current)) continue;
      const content = fs.readFileSync(current, 'utf8');
      const links = extractLinks(content, current, repoRoot);
      for (const link of links) {
        if (!reachable.has(link.resolved) && knownPaths.has(link.resolved)) {
          reachable.add(link.resolved);
          queue.push(link.resolved);
        }
      }
    }
  }

  // Check for broken links
  const brokenLinks = [];
  for (const file of allFiles) {
    const content = fs.readFileSync(file, 'utf8');
    const links = extractLinks(content, file, repoRoot);
    for (const link of links) {
      if (!fs.existsSync(link.resolved)) {
        brokenLinks.push({
          from: path.relative(repoRoot, file),
          href: link.href,
          text: link.text,
        });
      }
    }
  }

  if (brokenLinks.length > 0) {
    results.push({
      check: 'cross-links',
      status: 'error',
      message: `${brokenLinks.length} broken link(s) in docs`,
      detail: brokenLinks.map(l => `  ${l.from}: [${l.text}](${l.href})`).join('\n'),
    });
  } else {
    results.push({
      check: 'cross-links',
      status: 'ok',
      message: `All doc links resolve (${allFiles.length} files checked)`,
    });
  }

  // Check for orphaned docs (not reachable from CLAUDE.md)
  const orphans = allDocFiles
    .map(f => path.resolve(f))
    .filter(f => !reachable.has(f))
    .map(f => path.relative(repoRoot, f));

  if (orphans.length > 0) {
    results.push({
      check: 'claude-md-toc-sync',
      status: 'warn',
      message: `${orphans.length} doc(s) not reachable from CLAUDE.md`,
      detail: orphans.map(o => `  ${o}`).join('\n') + '\n  → Add links in CLAUDE.md or run /garden:weed',
    });
  } else {
    results.push({
      check: 'claude-md-toc-sync',
      status: 'ok',
      message: 'All docs reachable from CLAUDE.md',
    });
  }

  return results;
}

module.exports = { checkCrossLinks };
