#!/usr/bin/env node
import { Command } from 'commander';
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync, chmodSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const templatesDir = join(repoRoot, 'templates');
const allowedVariants = ['minimal', 'cli-workflow', 'tool-wrapper'] as const;
type Variant = (typeof allowedVariants)[number];

function normalizeName(raw: string): string {
  return raw.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-{2,}/g, '-').replace(/^-|-$/g, '');
}

function titleCase(name: string): string {
  return name.split('-').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function defaultDescription(variant: Variant): string {
  switch (variant) {
    case 'cli-workflow':
      return 'Describe what this skill does and when to use it. Include concrete triggers, data sources, inputs, or file types.';
    case 'tool-wrapper':
      return 'Describe the specific tool or API this skill wraps and when to use it. Include concrete triggers, commands, or failure cases.';
    default:
      return 'Describe what this skill does and when to use it. Include concrete trigger phrases, task types, or file types.';
  }
}

function renderTemplate(content: string, values: Record<string, string>): string {
  return content.replace(/\{\{([A-Z_]+)\}\}/g, (_, key: string) => values[key] ?? _);
}

function walk(dir: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      results.push(...walk(fullPath));
    } else {
      results.push(fullPath);
    }
  }
  return results;
}

function scaffoldSkill(options: { name: string; variant: Variant; path: string; force: boolean }) {
  const name = normalizeName(options.name);
  if (!name) throw new Error('Skill name must include at least one letter or digit.');
  if (name.length > 64) throw new Error(`Skill name is too long (${name.length} > 64).`);

  const sourceDir = join(templatesDir, `skill-${options.variant}`);
  if (!existsSync(sourceDir)) throw new Error(`Template not found: ${sourceDir}`);

  const targetDir = resolve(repoRoot, options.path, name);
  if (existsSync(targetDir)) {
    if (!options.force) throw new Error(`Target already exists: ${targetDir}`);
    rmSync(targetDir, { recursive: true, force: true });
  }

  mkdirSync(targetDir, { recursive: true });
  cpSync(sourceDir, targetDir, { recursive: true });

  const values = {
    SKILL_NAME: name,
    SKILL_TITLE: titleCase(name),
    DESCRIPTION: defaultDescription(options.variant),
  };

  for (const filePath of walk(targetDir)) {
    const content = readFileSync(filePath, 'utf8');
    writeFileSync(filePath, renderTemplate(content, values), 'utf8');
    if (filePath.endsWith('.sh')) chmodSync(filePath, 0o755);
  }

  console.log(`[OK] Created ${options.variant} skill scaffold at ${targetDir}`);
  console.log('[NEXT] Fill in the description, remove placeholders, and run validate-skill before review.');
}

const program = new Command();
program
  .name('new-skill')
  .description('Scaffold a new skill from an opinionated template')
  .argument('<name>', 'skill name, normalized to hyphen-case')
  .option('--variant <variant>', 'template variant', 'minimal')
  .option('--path <path>', 'parent directory for the generated skill', 'skills')
  .option('--force', 'overwrite an existing target directory', false)
  .action((name, options: { variant: Variant; path: string; force: boolean }) => {
    if (!allowedVariants.includes(options.variant)) {
      console.error(`[ERROR] Invalid variant: ${options.variant}`);
      console.error(`        Use one of: ${allowedVariants.join(', ')}`);
      process.exit(1);
    }

    try {
      scaffoldSkill({ name, variant: options.variant, path: options.path, force: options.force });
    } catch (error) {
      console.error(`[ERROR] ${(error as Error).message}`);
      process.exit(1);
    }
  });

program.parse();
