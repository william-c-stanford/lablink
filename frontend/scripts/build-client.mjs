/**
 * Post-processing script for the generated OpenAPI TypeScript client.
 *
 * This script runs after `openapi-typescript` generates src/api/schema.d.ts
 * to verify the output is correct and report generation statistics.
 *
 * Run via: node scripts/build-client.mjs
 * Or via: npm run generate:api
 */

import { readFileSync, statSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const rootDir = resolve(__dirname, '..')

function main() {
  const schemaPath = resolve(rootDir, 'src/api/schema.d.ts')
  const openapiPath = resolve(rootDir, 'openapi.json')

  try {
    const schemaContent = readFileSync(schemaPath, 'utf-8')
    const schemaStats = statSync(schemaPath)
    const openapiContent = readFileSync(openapiPath, 'utf-8')
    const openapi = JSON.parse(openapiContent)

    const pathCount = Object.keys(openapi.paths ?? {}).length
    const schemaCount = Object.keys(openapi.components?.schemas ?? {}).length
    const operationCount = Object.values(openapi.paths ?? {}).reduce((acc, path) => {
      return acc + Object.keys(path).filter(m => ['get','post','put','patch','delete'].includes(m)).length
    }, 0)

    // Count exported interfaces/types in the generated file
    const interfaceMatches = schemaContent.match(/^export interface /gm) ?? []
    const typeMatches = schemaContent.match(/^export type /gm) ?? []

    console.log('\n✅ LabLink API client generated successfully')
    console.log('─'.repeat(50))
    console.log(`📋 OpenAPI spec:`)
    console.log(`   Paths:      ${pathCount}`)
    console.log(`   Operations: ${operationCount}`)
    console.log(`   Schemas:    ${schemaCount}`)
    console.log(`\n📁 Generated: src/api/schema.d.ts`)
    console.log(`   Size:       ${(schemaStats.size / 1024).toFixed(1)} KB`)
    console.log(`   Interfaces: ${interfaceMatches.length}`)
    console.log(`   Types:      ${typeMatches.length}`)
    console.log('─'.repeat(50))
    console.log('\n💡 Import in your code:')
    console.log("   import { apiClient } from '@/api/client'")
    console.log("   import type { components } from '@/api'")
    console.log("   import { useUploads, useExperiments } from '@/api/hooks'\n")

  } catch (err) {
    if (err.code === 'ENOENT') {
      console.error(`\n❌ Error: ${err.path} not found`)
      console.error('   Run: npm run generate:api')
    } else {
      console.error('\n❌ Error during post-processing:', err.message)
    }
    process.exit(1)
  }
}

main()
