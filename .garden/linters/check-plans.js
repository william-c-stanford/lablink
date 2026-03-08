#!/usr/bin/env node
// check-plans.js — validates plan placement, catalogue completeness, and active plan structure
'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REQUIRED_SECTIONS = ['## Progress', '## Decision Log', '## Outcomes & Retrospective'];

// Directories and filename patterns that indicate a misplaced plan/spec file
const STRAY_PLAN_DIRS = ['plans', '.agent/plans'];
const STRAY_SPEC_DIRS = ['specs', 'features', '.agent/specs'];
const STRAY_ALL_DIRS = [...STRAY_PLAN_DIRS, ...STRAY_SPEC_DIRS];

// Content-based signals that a file is a plan or spec
const PLAN_SIGNALS = ['## Progress', '## Milestones', '## Decision Log', '## Implementation Plan', '## Acceptance Criteria'];
const SPEC_SIGNALS = ['## User Story', '## Problem Statement', '## Proposed Solution'];
const ALL_SIGNALS = [...new Set([...PLAN_SIGNALS, ...SPEC_SIGNALS])];

function isForwardingStub(content) {
  return content.includes('has moved to');
}

function hasPlanSignals(content) {
  return PLAN_SIGNALS.filter(s => content.includes(s)).length >= 2;
}

function hasSpecSignals(content) {
  return SPEC_SIGNALS.filter(s => content.includes(s)).length >= 2;
}

function getStagedFiles(repoRoot) {
  try {
    const output = execSync('git diff --cached --name-only', { cwd: repoRoot, encoding: 'utf8' });
    return output.trim().split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

function walkDirs(dirs, repoRoot) {
  const results = [];
  for (const dir of dirs) {
    const full = path.join(repoRoot, dir);
    if (!fs.existsSync(full)) continue;
    const entries = fs.readdirSync(full, { withFileTypes: true });
    for (const entry of entries) {
      const entryPath = path.join(full, entry.name);
      if (entry.isDirectory()) {
        // one level deep for these dirs
        results.push(...walkMd(entryPath));
      } else if (entry.name.endsWith('.md')) {
        results.push(entryPath);
      }
    }
  }
  return results;
}

function walkMd(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkMd(full));
    } else if (entry.name.endsWith('.md')) {
      results.push(full);
    }
  }
  return results;
}

function checkPlans(repoRoot, config, mode = 'pre-push') {
  const results = [];
  const plansConfig = config.plans || {};
  const cataloguePath = path.join(repoRoot, plansConfig.cataloguePath || 'docs/PLANS.md');
  const activePath = path.join(repoRoot, plansConfig.activePath || 'docs/execution-plans/active');
  const ignore = plansConfig.ignore || [];

  // Pre-commit: check staged files for misplaced plans/specs
  if (mode === 'pre-commit') {
    const staged = getStagedFiles(repoRoot);
    const misplacedStaged = staged.filter(f => {
      if (!f.endsWith('.md')) return false;
      if (f.startsWith('docs/')) return false;
      if (f === 'README.md') return false;
      // Location signal: in a known stray directory
      if (STRAY_ALL_DIRS.some(d => f.startsWith(d + '/'))) return true;
      // Filename signal: root-level *-plan.md or *.plan.md
      const base = path.basename(f, '.md');
      if (base.endsWith('-plan') || f.match(/^[^/]+\.plan\.md$/)) return true;
      return false;
    });

    if (misplacedStaged.length > 0) {
      results.push({
        check: 'plans-misplaced',
        status: 'warn',
        message: `${misplacedStaged.length} staged plan/spec file(s) in non-standard location`,
        detail: misplacedStaged.map(f => `  ${f}`).join('\n') +
          '\n  → Run /garden:harmonize to migrate into docs/execution-plans/ or docs/product-specs/',
      });
    } else {
      results.push({
        check: 'plans-misplaced',
        status: 'ok',
        message: 'No staged plan/spec files in non-standard locations',
      });
    }
    return results;
  }

  // 1. plans-stray — whole-tree scan for plan/spec files outside docs/execution-plans/
  // Runs unconditionally (even if catalogue is absent) so strays are always reported.
  // (pre-push / CI only — more thorough than the staged-file pre-commit check)
  const strayByLocation = walkDirs(STRAY_ALL_DIRS, repoRoot).filter(f => {
    const content = fs.readFileSync(f, 'utf8');
    return !isForwardingStub(content) && path.basename(f) !== 'README.md';
  });

  // Also catch content-based strays outside docs/ and outside the known stray dirs
  const docsDir = path.join(repoRoot, 'docs');
  const allMdOutsideDocs = [];
  try {
    const entries = fs.readdirSync(repoRoot, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        if (entry.name.endsWith('.md') && entry.name !== 'README.md') {
          allMdOutsideDocs.push(path.join(repoRoot, entry.name));
        }
      }
    }
  } catch { /* ignore */ }

  const contentStrays = allMdOutsideDocs.filter(f => {
    const rel = path.relative(repoRoot, f);
    if (rel.startsWith('docs/')) return false;
    if (ignore.some(ig => rel.startsWith(ig))) return false;
    const content = fs.readFileSync(f, 'utf8');
    if (isForwardingStub(content)) return false;
    return hasPlanSignals(content) || hasSpecSignals(content);
  });

  const allStray = [...new Set([...strayByLocation, ...contentStrays])].map(f => path.relative(repoRoot, f));

  if (allStray.length > 0) {
    results.push({
      check: 'plans-stray',
      status: 'warn',
      message: `${allStray.length} plan/spec file(s) found outside standard structure`,
      detail: allStray.map(f => `  ${f}`).join('\n') +
        '\n  → Run /garden:harmonize to migrate into docs/execution-plans/ or docs/product-specs/',
    });
  } else {
    results.push({
      check: 'plans-stray',
      status: 'ok',
      message: 'No stray plan/spec files found outside docs/',
    });
  }

  // 2. plans-catalogue-exists
  if (!fs.existsSync(cataloguePath)) {
    results.push({
      check: 'plans-catalogue-exists',
      status: 'warn',
      message: 'docs/PLANS.md not found — run /garden:init to scaffold or create it manually',
    });
    // Without the catalogue the orphan/structure checks are meaningless
    return results;
  }

  results.push({
    check: 'plans-catalogue-exists',
    status: 'ok',
    message: 'docs/PLANS.md found',
  });

  const catalogueContent = fs.readFileSync(cataloguePath, 'utf8');

  // 3. plans-orphan — every .md under docs/execution-plans/ must be linked from the catalogue
  const execPlansDir = path.dirname(activePath); // docs/execution-plans/
  const allPlanFiles = walkMd(execPlansDir).filter(f => {
    const rel = path.relative(repoRoot, f);
    return !ignore.some(ig => rel.startsWith(ig));
  });

  const orphans = allPlanFiles.filter(f => {
    const rel = path.relative(path.dirname(cataloguePath), f); // relative to docs/
    // Check for the filename appearing anywhere in the catalogue as a link target
    const basename = path.basename(f);
    return !catalogueContent.includes(basename) && !catalogueContent.includes(rel);
  });

  if (orphans.length > 0) {
    results.push({
      check: 'plans-orphan',
      status: 'warn',
      message: `${orphans.length} plan file(s) not linked from docs/PLANS.md`,
      detail: orphans.map(f => `  ${path.relative(repoRoot, f)}`).join('\n') +
        '\n  → Add entries to docs/PLANS.md or move files to completed/',
    });
  } else {
    const count = allPlanFiles.length;
    results.push({
      check: 'plans-orphan',
      status: 'ok',
      message: count === 0
        ? 'No execution plan files found (docs/execution-plans/ is empty)'
        : `All ${count} plan file(s) linked from docs/PLANS.md`,
    });
  }

  // 5. plans-active-structure — every .md in active/ must have required sections
  const activePlanFiles = walkMd(activePath).filter(f => {
    const rel = path.relative(repoRoot, f);
    return !ignore.some(ig => rel.startsWith(ig));
  });

  const malformed = [];
  for (const f of activePlanFiles) {
    const content = fs.readFileSync(f, 'utf8');
    const missing = REQUIRED_SECTIONS.filter(s => !content.includes(s));
    if (missing.length > 0) {
      malformed.push({ file: path.relative(repoRoot, f), missing });
    }
  }

  if (malformed.length > 0) {
    results.push({
      check: 'plans-active-structure',
      status: 'error',
      message: `${malformed.length} active plan(s) missing required sections`,
      detail: malformed.map(m =>
        `  ${m.file}: missing ${m.missing.map(s => `"${s}"`).join(', ')}`
      ).join('\n'),
    });
  } else {
    results.push({
      check: 'plans-active-structure',
      status: 'ok',
      message: activePlanFiles.length === 0
        ? 'No active plans to check'
        : `All ${activePlanFiles.length} active plan(s) have required sections`,
    });
  }

  return results;
}

module.exports = { checkPlans };
